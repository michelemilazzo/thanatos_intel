"""Incarico 'light' di verifica automatizzata wallet.

Mandato pre-impostato, non DDD: il cliente accetta con un click PRIMA del
pagamento; col pagamento del primo step l'accettazione si perfeziona (vale come
sottoscrizione), si genera il PDF e si archivia sul caso/portale.

Stato persistito su Investigation Case (engagement_*). Niente Agency Mandate (DDD).
"""
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.pdf import get_pdf

TEMPLATE = "thanatos_intel/templates/engagement_mandate.html"

def _guard(case_name):
    from thanatos_intel.permissions import is_full_access, visible_case_names
    u = frappe.session.user
    if is_full_access(u):
        return
    if case_name not in (visible_case_names(u) or []):
        frappe.throw(_("Accesso negato."), frappe.PermissionError)


PDF_OPTIONS = {
    "margin-top": "18mm", "margin-bottom": "20mm", "margin-left": "16mm",
    "margin-right": "16mm", "page-size": "A4", "encoding": "UTF-8",
    "enable-local-file-access": "",
}


def _emittente(case):
    """Dati del mandatario dalla Billing Entity di default, con fallback."""
    be = None
    name = frappe.db.get_value("Billing Entity", {}, "name")
    if name:
        be = frappe.get_doc("Billing Entity", name)
    return {
        "emittente": (be.legal_name if be and be.get("legal_name") else "THANATOS INVESTIGAZIONI S.R.L."),
        "emittente_vat": (be.get("vat_number") if be else "") or "",
        "emittente_addr": (be.get("address") if be else "") or "",
        "gov_law": (be.get("governing_law") if be else "") or "Legge applicabile italiana",
        "foro": (be.get("jurisdiction") if be else "") or "il Tribunale competente",
    }


def _ctx(case):
    from thanatos_intel.osint import wallet_monitor as wm
    client_name, client_email = None, None
    if case.get("client"):
        client_name = frappe.db.get_value("Investigation Client", case.client, "client_name") or case.client
        client_email = wm._client_email(case)
    wallets = [ce.entity for ce in (case.get("case_entities") or [])
               if (ce.entity_type or "") == "Wallet" or
               frappe.db.get_value("Investigation Entity", ce.entity, "entity_type") == "Wallet"]
    ctx = {
        "case": case, "frappe": frappe, "now": now_datetime(),
        "client_name": client_name or "—", "client_email": client_email,
        "wallets": wallets, "accepted": bool(case.get("engagement_accepted")),
        "accepted_on": case.get("engagement_accepted_on"),
        "accepted_ip": case.get("engagement_accepted_ip"),
        "perfected_on": case.get("engagement_perfected_on"),
    }
    ctx.update(_emittente(case))
    return ctx


def _render(case):
    return frappe.render_template(TEMPLATE, _ctx(case))


@frappe.whitelist()
def get_engagement(case_name):
    """HTML dell'incarico + stato. Usato dal portale prima del pagamento."""
    _guard(case_name)
    case = frappe.get_doc("Investigation Case", case_name)
    return {
        "html": _render(case),
        "accepted": bool(case.get("engagement_accepted")),
        "perfected": bool(case.get("engagement_perfected_on")),
        "pdf": case.get("engagement_pdf"),
    }


@frappe.whitelist()
def accept_engagement(case_name):
    """Il cliente accetta l'incarico (click). Registra consenso+IP. Non perfeziona
    ancora: il perfezionamento avviene col pagamento del primo step."""
    _guard(case_name)
    case = frappe.get_doc("Investigation Case", case_name)
    if not case.get("engagement_accepted"):
        ip = getattr(frappe.local, "request_ip", None)
        case.db_set("engagement_accepted", 1, update_modified=False)
        case.db_set("engagement_accepted_on", now_datetime(), update_modified=False)
        case.db_set("engagement_accepted_ip", ip or "", update_modified=False)
        case.db_set("engagement_html", _render(case), update_modified=False)
        frappe.db.commit()
    return {"ok": True, "accepted": True}


def perfect_engagement(case_name, payment_ref=None):
    """Chiamata dal webhook al pagamento del primo step: l'accettazione diventa
    sottoscrizione. Genera il PDF e lo archivia sul caso."""
    case = frappe.get_doc("Investigation Case", case_name)
    if case.get("engagement_perfected_on"):
        return case.get("engagement_pdf")
    if not case.get("engagement_accepted"):
        # pagamento senza accettazione esplicita: registra comunque l'accettazione
        case.db_set("engagement_accepted", 1, update_modified=False)
        case.db_set("engagement_accepted_on", now_datetime(), update_modified=False)
    case.db_set("engagement_perfected_on", now_datetime(), update_modified=False)
    frappe.db.commit()
    case.reload()
    file_url = _make_pdf(case)
    case.db_set("engagement_pdf", file_url, update_modified=False)
    case.db_set("engagement_html", _render(case), update_modified=False)
    frappe.db.commit()
    _notify_client(case, file_url)
    return file_url


def _make_pdf(case):
    html = _render(case)
    pdf = get_pdf(html, options=PDF_OPTIONS)
    fname = f"incarico_{case.name}.pdf"
    old = frappe.db.get_value("File", {"attached_to_doctype": "Investigation Case",
                                       "attached_to_name": case.name, "file_name": fname}, "name")
    if old:
        frappe.delete_doc("File", old, ignore_permissions=True, force=True)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "content": pdf, "is_private": 1,
                        "attached_to_doctype": "Investigation Case", "attached_to_name": case.name})
    f.flags.ignore_permissions = True
    f.save(ignore_permissions=True)
    return f.file_url


def _notify_client(case, file_url):
    from thanatos_intel.osint import wallet_monitor as wm
    em = wm._client_email(case)
    if not em:
        return
    try:
        from thanatos_intel.integrations import email_render
        _body = _("Gentile Cliente,<br><br>l'incarico per la pratica <b>{0}</b> è stato "
                  "<b>perfezionato</b> con il pagamento. In allegato il documento firmato, "
                  "disponibile anche nella sua area clienti.").format(case.name)
        frappe.sendmail(
            recipients=[em],
            subject=_("Thanatos — Incarico verifica wallet (perfezionato)"),
            message=email_render.render(_body, title=_("Incarico perfezionato"),
                                        preheader=_("Il suo incarico è attivo"),
                                        cta=(_("Apri la pratica"), "https://thanatos.onekeyco.com/portal/case/%s" % case.name)),
            attachments=[{"fname": f"incarico_{case.name}.pdf",
                          "fcontent": frappe.get_doc("File", {"file_url": file_url}).get_content()}],
            reference_doctype="Investigation Case", reference_name=case.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "engagement notify")


def on_step_paid(case_name, seq=None, payment_ref=None):
    """Hook post-pagamento di uno step: perfeziona l'incarico (primo pagamento) e
    fa avanzare il workflow chiudendo lo step di pagamento."""
    perfect_engagement(case_name, payment_ref=payment_ref)
    from thanatos_intel.workflow import engine
    case = frappe.get_doc("Investigation Case", case_name)
    pay_step = None
    for s in sorted(case.get("case_steps") or [], key=lambda x: x.seq):
        if s.status == "Awaiting Client" and (s.action_type == "pay" or (s.action_type or "") == "pay"):
            if seq is None or s.seq == int(seq):
                pay_step = s
                break
    if pay_step:
        return engine.complete_step(case_name, pay_step.seq, note=f"Pagamento ricevuto ({payment_ref or 'stripe'})")
    return {"ok": True, "no_pay_step": True}
