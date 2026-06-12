import frappe

no_cache = 1

CLIENT_TYPE_MAP = {
    "privato":      "Individual",
    "avvocato":     "Law Firm",
    "commercialista": "Accounting Firm",
    "azienda":      "Company",
    "immobiliare":  "Company",
    "banca":        "Company",
    "finanziaria":  "Company",
    "altro":        "Other",
}


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
def register_client(full_name, email, password, phone=None,
                    client_type_key=None, vat_number=None, extra_info=None,
                    ref=None, service=None):
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

    ctype = CLIENT_TYPE_MAP.get((client_type_key or "altro").lower(), "Other")

    # Esegui come Administrator per evitare problemi di permessi sui hook (Drive, etc.)
    prev_user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": full_name.split()[0],
            "last_name": " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else "",
            "user_type": "Website User",
            "send_welcome_email": 0,
            "roles": [{"role": "Investigation Client"}],
        })
        user.insert(ignore_permissions=True)
        from frappe.utils.password import update_password
        update_password(email, password)
        # il hook Drive può promuovere a System User: reimposta Website User
        frappe.db.set_value("User", email, "user_type", "Website User", update_modified=False)

        client_data = {
            "doctype": "Investigation Client",
            "client_name": full_name,
            "email": email,
            "phone": phone or "",
            "client_type": ctype,
            "platform_user": email,
            "status": "Active",
            "kyc_status": "Not Started",
            "kyb_status": "Not Started",
        }
        if vat_number:
            client_data["vat_number"] = vat_number
        # attribuzione referral: ?ref=<codice> dal QR preventivo o link collaboratore
        ref = (ref or "").strip()
        if ref:
            client_data["attribution_source"] = "Referral Link"
            client_data["referral_code"] = ref[:140]
        else:
            client_data["attribution_source"] = "Direct Website"
        if service:
            # nessun campo dedicato: lo aggiungiamo a extra_info per l'operatore
            extra_info = f"Servizio richiesto: {service[:140]}" + (f" | {extra_info}" if extra_info else "")

        client = frappe.get_doc(client_data)
        client.insert(ignore_permissions=True)
        if extra_info:
            client.add_comment("Comment", text=extra_info[:500])
        frappe.db.commit()
    finally:
        frappe.set_user(prev_user)

    return {"ok": True, "redirect": "/portal"}
