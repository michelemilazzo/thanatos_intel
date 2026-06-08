import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user != "Guest":
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect
    context.title = "Registrati — Thanatos Agency"
    context.no_cache = 1
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    return context


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_client(full_name, email, password, phone=None, company=None):
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    if not full_name or not email or not password:
        frappe.throw("Nome, email e password sono obbligatori.")
    if "@" not in email:
        frappe.throw("Email non valida.")
    if len(password) < 8:
        frappe.throw("La password deve essere di almeno 8 caratteri.")
    if frappe.db.exists("User", email):
        frappe.throw("Esiste già un account con questa email.")

    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": full_name.split()[0],
        "last_name": " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else "",
        "user_type": "Website User",
        "send_welcome_email": 0,
        "roles": [{"role": "Investigation Client"}],
    })
    user.flags.ignore_permissions = True
    user.insert(ignore_permissions=True)
    user.update_password(password)

    # Crea Investigation Client collegato
    client = frappe.get_doc({
        "doctype": "Investigation Client",
        "client_name": full_name,
        "email": email,
        "phone": phone,
        "company_name": company,
        "platform_user": email,
        "status": "Active",
        "kyc_status": "Not Started",
        "kyb_status": "Not Started",
    })
    client.flags.ignore_permissions = True
    client.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "redirect": "/portal"}
