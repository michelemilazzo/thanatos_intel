"""Sollecito completamento dati onboarding.

Rileva i campi profilo mancanti su Investigation Client e invia al cliente
un'email (IT/EN) con l'elenco e il link al form portale `/modifica-profilo`.
Job giornaliero throttlato + invio on-demand dalla scheda.
"""
import frappe
from frappe.utils import now_datetime, get_url, get_datetime

REQUIRED_COMMON = [
    ("phone", "Telefono / Phone"),
    ("res_address_line1", "Residenza — Via e civico"),
    ("res_city", "Residenza — Città"),
    ("res_postal_code", "Residenza — CAP"),
    ("res_country", "Residenza — Paese"),
]
REQUIRED_INDIVIDUAL = [("codice_fiscale", "Codice Fiscale")]
REQUIRED_COMPANY = [("vat_number", "VAT / CUI")]

REMINDER_THROTTLE_DAYS = 3
ELIGIBLE_STATUS = ["Active", "Under Review", "Completed", "Active - No Card",
                   "Pending Documents", "Onboarding"]


def missing_fields(c):
    """Lista (label) dei campi profilo mancanti per il cliente."""
    req = list(REQUIRED_COMMON)
    req += REQUIRED_COMPANY if (c.get("client_type") == "Company") else REQUIRED_INDIVIDUAL
    out = []
    for fn, label in req:
        val = c.get(fn)
        if not (val and str(val).strip()):
            out.append(label)
    return out


def _email_html(client_name, missing, url, lang):
    items = "".join(f"<li>{frappe.utils.escape_html(m)}</li>" for m in missing)
    if lang.startswith("en"):
        return (f"<p>Dear {frappe.utils.escape_html(client_name)},</p>"
                "<p>To complete your onboarding with Thanatos Intelligence we still need a few details:</p>"
                f"<ul>{items}</ul>"
                f"<p><a href='{url}' style='background:#1a1a2e;color:#fff;padding:10px 20px;"
                "border-radius:4px;text-decoration:none;display:inline-block;'>Complete my profile</a></p>"
                "<p>It only takes a minute. Thank you.</p>")
    return (f"<p>Gentile {frappe.utils.escape_html(client_name)},</p>"
            "<p>Per completare l'attivazione con Thanatos Intelligence ci mancano ancora alcuni dati:</p>"
            f"<ul>{items}</ul>"
            f"<p><a href='{url}' style='background:#1a1a2e;color:#fff;padding:10px 20px;"
            "border-radius:4px;text-decoration:none;display:inline-block;'>Completa il mio profilo</a></p>"
            "<p>Bastano un paio di minuti. Grazie.</p>")


@frappe.whitelist()
def send_completion_request(client):
    """Invia (o ri-invia) il sollecito di completamento al cliente."""
    c = frappe.get_doc("Investigation Client", client)
    if not c.email:
        return {"ok": False, "reason": "cliente senza email"}
    miss = missing_fields(c)
    if not miss:
        return {"ok": False, "reason": "profilo già completo"}
    url = get_url("/modifica-profilo")
    lang = (c.get("preferred_language") or "it").lower()
    subject = ("Completa i tuoi dati — Thanatos Intel" if lang.startswith("it")
               else "Complete your details — Thanatos Intel")
    frappe.sendmail(
        recipients=[c.email],
        subject=subject,
        message=_email_html(c.client_name, miss, url, lang),
        reference_doctype="Investigation Client",
        reference_name=c.name,
    )
    c.db_set("last_completion_reminder", now_datetime())
    return {"ok": True, "missing": miss, "sent_to": c.email}


def daily_completion_reminder():
    """Job giornaliero: sollecita i clienti con profilo incompleto (throttle 3gg)."""
    rows = frappe.get_all(
        "Investigation Client",
        filters={"email": ["is", "set"], "onboarding_status": ["in", ELIGIBLE_STATUS]},
        pluck="name",
    )
    for name in rows:
        try:
            c = frappe.get_doc("Investigation Client", name)
            if not missing_fields(c):
                continue
            last = c.get("last_completion_reminder")
            if last and (now_datetime() - get_datetime(last)).days < REMINDER_THROTTLE_DAYS:
                continue
            send_completion_request(name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"completion_reminder {name}")
