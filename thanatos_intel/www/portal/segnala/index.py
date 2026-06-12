import io

import frappe
from frappe import _
from frappe.utils import nowdate

no_cache = 1


def _my_client():
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)
    client = frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")
    if not client:
        frappe.throw(_("Il tuo account non è collegato a un profilo cliente."))
    return client


def _own_report(report_name):
    client = _my_client()
    rep = frappe.get_doc("Blacklist Report", report_name)
    if rep.reporter != client:
        frappe.throw(_("Segnalazione non trovata."), frappe.PermissionError)
    return rep, client


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/segnala"
        raise frappe.Redirect
    context.client = frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")
    context.balance = frappe.db.get_value("Investigation Client", context.client, "service_credit") if context.client else 0
    context.bonus = frappe.db.get_single_value("Thanatos Billing Settings", "report_bonus_amount") or 2
    context.my_reports = []
    context.verified = False
    if context.client:
        context.my_reports = frappe.get_all(
            "Blacklist Report", filters={"reporter": context.client},
            fields=["name", "entry_type", "entry_value", "status", "reason",
                    "evidence", "authority_form", "filed_complaint", "complaint_filed_on", "creation"],
            order_by="creation desc", limit=30)
        ob = frappe.db.get_value("Investigation Client", context.client,
                                 ["onboarding_status", "kyc_status", "kyb_status"], as_dict=True) or {}
        context.verified = (ob.get("onboarding_status") in ("Under Review", "Active")
                            or (ob.get("kyc_status") or "") in ("In Review", "Verified", "Approved")
                            or (ob.get("kyb_status") or "") in ("In Review", "Verified", "Approved"))
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Segnala alla blacklist — Thanatos"
    context.lang = frappe.local.lang or "it"
    return context


@frappe.whitelist(methods=["POST"])
def submit_report(entry_type, entry_value, reason, evidence=None):
    client = _my_client()
    entry_value = (entry_value or "").strip()
    if not entry_value or not (reason or "").strip():
        frappe.throw(_("Valore e motivo sono obbligatori."))
    doc = frappe.get_doc({
        "doctype": "Blacklist Report", "reporter": client, "entry_type": entry_type,
        "entry_value": entry_value, "reason": reason, "status": "In Review",
        "evidence": (evidence or "").strip() or None,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": doc.name}


def _authority_pdf(rep, client_doc):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    ss = getSampleStyleSheet()
    H = ParagraphStyle("H", parent=ss["Title"], fontSize=14, textColor=colors.HexColor("#0D1B3E"), spaceAfter=4)
    SUB = ParagraphStyle("S", parent=ss["Normal"], fontSize=9.5, textColor=colors.HexColor("#5A5A5A"), spaceAfter=12)
    B = ParagraphStyle("B", parent=ss["Normal"], fontSize=10.5, leading=15, spaceAfter=8)
    LBL = ParagraphStyle("L", parent=ss["Normal"], fontSize=10.5, leading=15, spaceAfter=2, textColor=colors.HexColor("#0D1B3E"))
    NOTE = ParagraphStyle("N", parent=ss["Normal"], fontName="Times-Italic", fontSize=8.6, textColor=colors.HexColor("#5A5A5A"),
                          leading=12, borderColor=colors.HexColor("#C8A96E"), borderWidth=0.5, borderPadding=8,
                          backColor=colors.HexColor("#F8F6F0"), spaceBefore=14)

    def g(v, blank="________________"):
        return (str(v).strip() if v else "") or blank

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=22 * mm, bottomMargin=20 * mm)
    S = []
    S.append(Paragraph("ATTO DI DENUNCIA-QUERELA", H))
    S.append(Paragraph("Spett.le Polizia Postale e delle Comunicazioni &mdash; Procura della Repubblica competente", SUB))

    S.append(Paragraph("<b>Il/la sottoscritto/a (denunciante)</b>", LBL))
    S.append(Paragraph(
        "Nome e cognome / ragione sociale: <b>%s</b><br/>"
        "Email: %s &nbsp;&nbsp; Telefono: %s<br/>"
        "Indirizzo: %s &nbsp; Paese: %s<br/>"
        "Codice fiscale / P.IVA: %s<br/>"
        "Documento d'identità n.: ________________ rilasciato da ________________ il ____/____/______"
        % (g(client_doc.client_name), g(client_doc.email), g(client_doc.phone),
           g(client_doc.address), g(client_doc.country), g(client_doc.vat_number)), B))

    S.append(Paragraph("<b>ESPONE QUANTO SEGUE</b>", LBL))
    S.append(Paragraph(
        "Di essere venuto/a a conoscenza di fatti che possono costituire reato, riconducibili al seguente "
        "soggetto/identificativo: <b>%s: %s</b>." % (rep.entry_type, rep.entry_value), B))
    S.append(Paragraph("Descrizione dei fatti: %s" % g(rep.reason, "________________________________________"), B))
    S.append(Paragraph(
        "Data/periodo dei fatti: ____/____/______ &nbsp;&nbsp; Importo del danno subito (se quantificabile): "
        "&euro; ________________", B))

    S.append(Paragraph("<b>CHIEDE</b>", LBL))
    S.append(Paragraph(
        "che l'Autorità competente voglia procedere all'accertamento dei fatti e all'individuazione dei "
        "responsabili, e si dichiara sin d'ora <b>persona offesa</b>, presentando formale "
        "<b>denuncia-querela</b> e riservandosi la costituzione di parte civile.", B))

    S.append(Paragraph("<b>Allegati</b>: documentazione probatoria in proprio possesso (screenshot, email, "
                       "ricevute, estratti, corrispondenza).", B))
    S.append(Spacer(1, 10))
    S.append(Paragraph("Luogo e data: ____________________, ____/____/______", B))
    S.append(Paragraph("Firma del denunciante: ____________________________", B))

    S.append(Paragraph(
        "Modulo precompilato automaticamente da Thanatos Intel sulla base della segnalazione %s a fini di "
        "supporto. NON sostituisce una consulenza legale: verificare e integrare i dati (documento, codice "
        "fiscale, data, importo), firmarlo e depositarlo presso l'Autorità. Documento generato il %s."
        % (rep.name, nowdate()), NOTE))
    doc.build(S)
    return buf.getvalue()


@frappe.whitelist()
def generate_authority_form(report_name):
    """Genera (o rigenera) il modulo denuncia precompilato per le autorità e lo allega
    alla segnalazione. Ritorna il file_url per il download."""
    rep, client = _own_report(report_name)
    client_doc = frappe.get_doc("Investigation Client", client)
    content = _authority_pdf(rep, client_doc)
    fname = "Modulo-denuncia-%s.pdf" % rep.name
    old = frappe.db.get_value("File", {"attached_to_doctype": "Blacklist Report",
                                       "attached_to_name": rep.name, "file_name": fname}, "name")
    if old:
        frappe.delete_doc("File", old, ignore_permissions=True, force=True)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1, "content": content,
                        "attached_to_doctype": "Blacklist Report", "attached_to_name": rep.name})
    f.save(ignore_permissions=True)
    rep.db_set("authority_form", f.file_url, commit=True)
    return {"ok": True, "file_url": f.file_url}


@frappe.whitelist(methods=["POST"])
def attach_filed_complaint(report_name, file_url, filed_on=None):
    """Allega la denuncia effettivamente depositata (dopo registrazione verificata)."""
    rep, client = _own_report(report_name)
    if not file_url:
        frappe.throw(_("Nessun file."))
    rep.db_set("filed_complaint", file_url, commit=False)
    rep.db_set("complaint_filed_on", filed_on or nowdate(), commit=True)
    return {"ok": True}
