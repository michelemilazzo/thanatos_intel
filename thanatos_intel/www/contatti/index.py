"""Contatti — /contatti. Form lead pubblico → doctype Lead (CRM nativo)."""
import frappe

no_cache = 1


def get_context(context):
    context.body_class = "ppu-page"
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    return context


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_contact(full_name, email, message, phone=None, company=None):
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    message = (message or "").strip()
    if not full_name or "@" not in email or not message:
        frappe.throw("Nome, email e messaggio sono obbligatori.")

    prev = frappe.session.user
    frappe.set_user("Administrator")
    try:
        lead = frappe.get_doc({
            "doctype": "Lead",
            "first_name": full_name.split()[0],
            "last_name": " ".join(full_name.split()[1:]),
            "email_id": email,
            "phone": (phone or "")[:30],
            "company_name": (company or "")[:140],
        })
        lead.insert(ignore_permissions=True)
        lead.add_comment("Comment", text=message[:2000])
        frappe.db.commit()
    finally:
        frappe.set_user(prev)
    return {"ok": True}
