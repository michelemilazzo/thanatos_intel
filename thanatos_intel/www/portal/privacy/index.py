import json
import frappe
from frappe import _
from frappe.utils import now_datetime

no_cache = 1

CONSENT_PURPOSES = [
    {"key": "marketing", "label": "Comunicazioni marketing e newsletter",
     "desc": "Offerte, novità e contenuti promozionali via email."},
    {"key": "profiling", "label": "Profilazione per offerte personalizzate",
     "desc": "Analisi delle tue preferenze per proporti servizi pertinenti."},
    {"key": "partner_sharing", "label": "Condivisione con partner selezionati",
     "desc": "Comunicazione dei dati a partner commerciali selezionati."},
]


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/privacy"
        raise frappe.Redirect

    from thanatos_intel.workflow.api import _client_for_user
    cl = _client_for_user(frappe.session.user)
    context.title = "Privacy & GDPR — Thanatos"
    context.client = cl
    context.deletion_pending = False
    context.consent_purposes = CONSENT_PURPOSES
    context.consents = {}
    if cl:
        context.deletion_pending = bool(
            frappe.db.get_value("Investigation Client", cl.name, "deletion_requested_at"))
        for pp in CONSENT_PURPOSES:
            rec = frappe.db.get_value(
                "Consent Record", {"client": cl.name, "purpose": pp["key"]},
                ["given_on", "withdrawn_on"], as_dict=True)
            context.consents[pp["key"]] = bool(rec and rec.given_on and not rec.withdrawn_on)
    return context


@frappe.whitelist(methods=["POST"])
def request_data_export():
    """Genera un JSON con tutti i dati personali del cliente e lo invia via email."""
    from thanatos_intel.workflow.api import _client_for_user
    cl = _client_for_user(frappe.session.user)
    if not cl:
        frappe.throw(_("Profilo cliente non trovato."), frappe.PermissionError)

    client = frappe.get_doc("Investigation Client", cl.name)
    cases = frappe.get_all("Investigation Case",
                           filters={"client": cl.name},
                           fields=["name", "case_title", "status", "creation"])
    usage_events = frappe.get_all("Usage Event",
                                  filters={"client": cl.name},
                                  fields=["name", "service", "total", "currency",
                                          "status", "creation"])
    reports = frappe.get_all("Blacklist Report",
                             filters={"reporter": cl.name},
                             fields=["name", "entry_type", "entry_value",
                                     "status", "creation"])

    export = {
        "exported_at": str(now_datetime()),
        "client": {
            "name": client.client_name,
            "email": client.email,
            "phone": client.phone,
            "country": client.country,
            "vat_number": client.vat_number,
            "subscription_plan": client.subscription_plan,
            "created": str(client.creation),
        },
        "cases": [dict(c) for c in cases],
        "usage_events": [dict(u) for u in usage_events],
        "blacklist_reports": [dict(r) for r in reports],
    }

    export_json = json.dumps(export, ensure_ascii=False, indent=2, default=str)

    frappe.sendmail(
        recipients=[frappe.session.user],
        subject="I tuoi dati Thanatos Intel — Export GDPR",
        message=(
            f"<p>Ciao {client.client_name},</p>"
            f"<p>In allegato trovi l'export di tutti i tuoi dati personali "
            f"presenti su Thanatos Intel.</p>"
            f"<pre style='font-size:11px;background:#f5f5f5;padding:12px'>"
            f"{frappe.utils.escape_html(export_json[:8000])}"
            f"{'...(troncato)' if len(export_json) > 8000 else ''}</pre>"
            f"<p>Per la copia completa o per qualsiasi domanda: "
            f"<a href='mailto:privacy@thanatos.agency'>privacy@thanatos.agency</a></p>"
        ),
        now=True,
    )
    return {"ok": True, "email": frappe.session.user}


@frappe.whitelist(methods=["POST"])
def request_account_deletion():
    """Registra la richiesta di cancellazione account (GDPR Art. 17).
    Non cancella immediatamente — un operatore verifica e procede entro 30 giorni."""
    from thanatos_intel.workflow.api import _client_for_user
    cl = _client_for_user(frappe.session.user)
    if not cl:
        frappe.throw(_("Profilo cliente non trovato."), frappe.PermissionError)

    already = frappe.db.get_value("Investigation Client", cl.name, "deletion_requested_at")
    if already:
        return {"ok": True, "already": True, "requested_at": str(already)}

    frappe.db.set_value("Investigation Client", cl.name,
                        "deletion_requested_at", now_datetime(),
                        update_modified=False)
    frappe.db.commit()

    frappe.sendmail(
        recipients=["admin@thanatos.agency"],
        subject=f"[GDPR] Richiesta cancellazione — {cl.name}",
        message=(
            f"<p>Il cliente <b>{cl.name}</b> ({frappe.session.user}) ha richiesto "
            f"la cancellazione del proprio account in data {now_datetime()}.</p>"
            f"<p>Ai sensi dell'Art. 17 GDPR, procedere entro 30 giorni.</p>"
            f"<p><a href='/app/investigation-client/{cl.name}'>Apri scheda cliente</a></p>"
        ),
        now=False,
    )

    frappe.sendmail(
        recipients=[frappe.session.user],
        subject="Richiesta cancellazione ricevuta — Thanatos Intel",
        message=(
            f"<p>Abbiamo ricevuto la tua richiesta di cancellazione account.</p>"
            f"<p>Procederemo entro 30 giorni ai sensi del Regolamento GDPR (Art. 17). "
            f"Riceverai una conferma a questa email.</p>"
            f"<p>Per domande: "
            f"<a href='mailto:privacy@thanatos.agency'>privacy@thanatos.agency</a></p>"
        ),
        now=False,
    )

    return {"ok": True, "requested_at": str(now_datetime())}


@frappe.whitelist(methods=["POST"])
def set_consent(purpose, granted):
    """Registra/revoca un consenso (GDPR Art. 7) tramite Consent Record."""
    from thanatos_intel.workflow.api import _client_for_user
    cl = _client_for_user(frappe.session.user)
    if not cl:
        frappe.throw(_("Profilo cliente non trovato."), frappe.PermissionError)
    valid = {p["key"] for p in CONSENT_PURPOSES}
    if purpose not in valid:
        frappe.throw(_("Finalità non valida."))
    granted = str(granted) in ("1", "true", "True", "on")

    name = frappe.db.get_value("Consent Record", {"client": cl.name, "purpose": purpose}, "name")
    if name:
        doc = frappe.get_doc("Consent Record", name)
    else:
        doc = frappe.new_doc("Consent Record")
        doc.client = cl.name
        doc.purpose = purpose
        doc.legal_basis = "Consenso"
        doc.data_subject = cl.client_name or frappe.session.user
        doc.email = frappe.session.user
        doc.channel = "portale"
    if granted:
        doc.given_on = now_datetime()
        doc.withdrawn_on = None
    else:
        doc.withdrawn_on = now_datetime()
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "purpose": purpose, "granted": granted}
