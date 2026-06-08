import frappe
from frappe import _

no_cache = 0


def get_context(context):
    context.no_cache = 0
    context.roles = [
        ("Investigator", "Investigatore privato", "Ricevi incarichi nella tua area operativa: indagini, OSINT, sopralluoghi, sorveglianza."),
        ("Agency", "Agenzia investigativa", "Collabora su pratiche complesse o internazionali. Assegnazione per competenza territoriale."),
    ]
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Collabora con Thanatos"
    context.lang = frappe.local.lang or "it"
    return context


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_application(applicant_name, role, email, phone=None, country=None, region=None,
                       license_info=None, message=None):
    applicant_name = (applicant_name or "").strip()
    email = (email or "").strip()
    if not applicant_name or not email or not role:
        frappe.throw(_("Nome, email e ruolo sono obbligatori."))
    if "@" not in email:
        frappe.throw(_("Email non valida."))
    # anti-spam: stessa email candidata di recente
    recent = frappe.db.exists("Affiliate Application", {"email": email, "status": ["in", ["New", "Contacted"]]})
    if recent:
        return {"ok": True, "duplicate": True}
    doc = frappe.get_doc({
        "doctype": "Affiliate Application", "applicant_name": applicant_name, "role": role,
        "email": email, "phone": phone, "country": country if country and frappe.db.exists("Country", country) else None,
        "region": region, "license_info": license_info, "message": message, "status": "New",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": doc.name}
