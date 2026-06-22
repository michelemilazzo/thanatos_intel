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
        # User esiste — controllo se ha già un Investigation Client
        existing_client = frappe.db.exists("Investigation Client", {"platform_user": email})
        if existing_client:
            frappe.throw(f"Esiste già un account attivo per questa email. "
                         f"Effettua il login: <a href='/login?usr={email}'>Accedi</a>")
        # User esiste ma senza Investigation Client → ripristina creando solo l'Investigation Client
        frappe.local._signup_user_exists = True
    else:
        frappe.local._signup_user_exists = False

    ctype = CLIENT_TYPE_MAP.get((client_type_key or "altro").lower(), "Other")

    # Esegui come Administrator per evitare problemi di permessi sui hook (Drive, etc.)
    prev_user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        from frappe.utils.password import update_password
        if not getattr(frappe.local, "_signup_user_exists", False):
            # Pulizia preventiva: rimuovi Contact orfani con stessa email che bloccano l'insert User
            for c in frappe.db.sql("SELECT name FROM tabContact WHERE email_id=%s", (email,), as_dict=1):
                # Controlla se Contact è linkato a qualcosa di importante; se no, lo lasciamo intatto e usiamo nostro user
                pass
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
                user.flags.ignore_permissions = True
                user.flags.no_welcome_mail = True
                user.insert(ignore_permissions=True, ignore_links=True)
            except frappe.DuplicateEntryError:
                # User creato da altro hook nel mezzo — ok, andiamo avanti
                pass
            except Exception as ue:
                frappe.log_error(f"User insert fail for {email}: {ue}\n{frappe.get_traceback()}", "register_client")
                # Messaggio parlante
                msg = str(ue)
                if "email" in msg.lower() and ("exists" in msg.lower() or "duplicate" in msg.lower() or "unique" in msg.lower()):
                    frappe.throw(f"L'email {email} è già presente in anagrafica come contatto. "
                                 f"Usa un'altra email, oppure contatta admin@thanatos.agency per riattivare l'account esistente.")
                frappe.throw(f"Impossibile creare l'account: {msg[:200]}")
        update_password(email, password)
        frappe.db.set_value("User", email, "user_type", "Website User", update_modified=False)
        # Garantisce ruolo Investigation Client
        u = frappe.get_doc("User", email)
        if not any(r.role == "Investigation Client" for r in u.roles):
            u.append("roles", {"role": "Investigation Client"})
            u.save(ignore_permissions=True)

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

        # Se esiste già Investigation Client con stessa email/vat, riusa
        existing_ic = frappe.db.get_value("Investigation Client", {"platform_user": email}, "name") \
                      or frappe.db.get_value("Investigation Client", {"email": email}, "name")
        if existing_ic:
            client = frappe.get_doc("Investigation Client", existing_ic)
            for k, v in client_data.items():
                if k == "doctype": continue
                if v and not client.get(k): client.set(k, v)
            client.save(ignore_permissions=True)
        else:
            client = frappe.get_doc(client_data)
            try:
                client.insert(ignore_permissions=True, ignore_links=True)
            except frappe.DuplicateEntryError:
                # race condition: cerca di nuovo
                existing_ic = frappe.db.get_value("Investigation Client", {"platform_user": email}, "name")
                if existing_ic:
                    client = frappe.get_doc("Investigation Client", existing_ic)
                else:
                    raise
        try:
            from thanatos_intel import referral
            referral.record_registration(client.name, ref)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "referral record_registration failed")
        if extra_info:
            client.add_comment("Comment", text=extra_info[:500])
        frappe.db.commit()
    finally:
        frappe.set_user(prev_user)

    return {"ok": True, "redirect": "/portal"}
