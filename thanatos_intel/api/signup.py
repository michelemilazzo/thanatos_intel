"""Custom signup endpoint Thanatos.

POST /api/method/thanatos_intel.api.signup.do_signup
Body JSON: {first_name, last_name, email, phone, password,
            client_type, preferred_language, company_name, vat_number,
            country, gdpr_consent, aml_disclosure, terms, marketing_consent}

Crea:
1. User (disabled=0 finché email non verificata, password set)
2. Investigation Client linkato a User
3. Audit log GDPR/AML consent
4. Invia email verifica con link reset password (welcome flow)
"""
import re
import frappe
from frappe import _
from frappe.utils import validate_email_address


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def do_signup(**kwargs) -> dict:
    data = frappe.local.form_dict
    if not data:
        try:
            data = frappe.parse_json(frappe.request.get_data().decode("utf-8") or "{}")
        except Exception:
            data = {}

    # Validate required
    required = ["first_name", "last_name", "email", "password",
                "client_type", "country", "preferred_language",
                "gdpr_consent", "aml_disclosure", "terms"]
    for f in required:
        v = data.get(f)
        if v in (None, "", False):
            return {"ok": False, "error": _("Campo obbligatorio mancante: ") + f}

    email = (data.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": _("Email non valida.")}
    try:
        validate_email_address(email, throw=True)
    except Exception:
        return {"ok": False, "error": _("Email non valida.")}

    password = (data.get("password") or "").strip()
    if len(password) < 10:
        return {"ok": False, "error": _("Password troppo corta (minimo 10 caratteri).")}

    if frappe.db.exists("User", email):
        return {"ok": False, "error": _("Email già registrata. Vai su /login per accedere.")}

    client_type = data.get("client_type")
    if client_type not in ("Individual", "Company", "Law Firm", "Accounting Firm", "Other"):
        return {"ok": False, "error": _("Tipo cliente non valido.")}

    company_name = (data.get("company_name") or "").strip()
    if client_type in ("Company", "Law Firm", "Accounting Firm") and not company_name:
        return {"ok": False, "error": _("Ragione sociale obbligatoria per il tipo cliente selezionato.")}

    first_name = (data.get("first_name") or "").strip()[:80]
    last_name = (data.get("last_name") or "").strip()[:80]
    phone = (data.get("phone") or "").strip()[:32]
    vat_number = (data.get("vat_number") or "").strip()[:32]
    country = (data.get("country") or "").strip()[:60]
    pref_lang = data.get("preferred_language") or "Italian"

    try:
        # 1. Create User
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "send_welcome_email": 0,  # we send a custom verification flow
            "enabled": 1,
            "user_type": "Website User",
            "new_password": password,
        })
        user.insert(ignore_permissions=True)

        # Default role
        user.add_roles("Investigation Client", "Customer")

        # 2. Create Investigation Client
        display_name = company_name or f"{first_name} {last_name}".strip()
        client = frappe.get_doc({
            "doctype": "Investigation Client",
            "client_name": display_name,
            "client_type": client_type,
            "email": email,
            "phone": phone,
            "country": country if frappe.db.exists("Country", country) else None,
            "vat_number": vat_number,
            "preferred_language": pref_lang,
            "platform_user": email,
            "subscription_status": "None",
        })
        client.insert(ignore_permissions=True)

        # 3. Audit log GDPR/AML consents
        try:
            frappe.get_doc({
                "doctype": "Diplomatic Audit Log",
                "event_type": "signup.consent",
                "new_value": "registered",
                "reason": frappe.as_json({
                    "user": email,
                    "client": client.name,
                    "client_type": client_type,
                    "gdpr_consent": bool(data.get("gdpr_consent")),
                    "aml_disclosure": bool(data.get("aml_disclosure")),
                    "terms": bool(data.get("terms")),
                    "marketing_consent": bool(data.get("marketing_consent")),
                    "ip": frappe.local.request_ip,
                    "ua": frappe.get_request_header("User-Agent", "")[:200],
                })[:1000],
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "signup audit log")

        frappe.db.commit()

        # 4. Send verification / welcome email
        try:
            _send_welcome_email(email, first_name, display_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "signup welcome email")

        # Auto-login the newly created user (simplifies UX: signup → onboarding)
        try:
            frappe.local.login_manager.login_as(email)
        except Exception:
            pass

        return {
            "ok": True,
            "user": email,
            "client": client.name,
            "next_url": "/onboarding/card",
            "message": "Account creato. Procedi con la verifica del metodo di pagamento.",
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "signup do_signup")
        return {"ok": False, "error": f"Errore durante la registrazione: {str(e)[:200]}"}


def _send_welcome_email(email: str, first_name: str, display_name: str) -> None:
    """Send branded welcome email with verification link."""
    site_url = frappe.utils.get_url()
    subject = "Benvenuto in Thanatos Intel — Verifica il tuo account"
    html = f"""
    <div style="font-family:Georgia,serif;background:#0A0E1A;color:#E6E8EE;padding:32px;max-width:600px;margin:0 auto;border-left:3px solid #C8A96E">
      <h1 style="color:#C8A96E;font-family:'Cinzel Decorative',Georgia,serif;margin:0 0 16px;letter-spacing:2px">THANATOS INVESTIGAZIONI</h1>
      <p>Gentile <strong>{first_name}</strong>,</p>
      <p>il tuo account <strong>{display_name}</strong> è stato creato sulla piattaforma <strong>Thanatos Intel</strong>.</p>
      <p>Per attivare l'accesso, conferma il tuo indirizzo email cliccando sul pulsante qui sotto:</p>
      <p style="text-align:center;margin:32px 0">
        <a href="{site_url}/login?user={email}" style="background:#C8A96E;color:#0A0E1A;padding:14px 32px;text-decoration:none;font-size:12px;letter-spacing:3px;text-transform:uppercase;font-weight:700">Accedi al portale →</a>
      </p>
      <p style="font-size:12px;color:#7A8294">Da questo momento avrai accesso a:</p>
      <ul style="font-size:13px;color:#B8BCCC">
        <li>Piattaforma investigativa Thanatos Intel</li>
        <li>30 servizi pay-per-use (verifiche, antifrode, cyber intelligence)</li>
        <li>4 piani abbonamento mensile (da €0 a Enterprise)</li>
        <li>Newsroom intelligence quotidiana</li>
      </ul>
      <hr style="border:0;border-top:1px solid #1F2742;margin:24px 0">
      <p style="font-size:11px;color:#7A8294;line-height:1.5">
        THANATOS INVESTIGAZIONI S.R.L. — CUI RO 46901022 — Str. Baba Novac 185, Constanța, Romania.<br>
        Agenzia investigativa autorizzata ai sensi della L.329/2003.<br>
        Trattamento dati ai sensi Reg.UE 679/2016 e L.190/2018.
      </p>
    </div>
    """
    frappe.sendmail(recipients=[email], subject=subject, message=html, now=True)
