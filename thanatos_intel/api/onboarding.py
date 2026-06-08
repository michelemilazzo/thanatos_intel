"""Onboarding API: SetupIntent, KYC/KYB submission.

Endpoints:
- create_setup_intent() → Stripe SetupIntent client_secret per /onboarding/card
- confirm_payment_method(payment_method_id) → salva PM su Investigation Client + advance state
- submit_kyc() / submit_kyb() → finalize step, set status Under Review
- upload_id_front / upload_id_back / upload_selfie / upload_company_doc → file upload helpers
"""
import frappe
from frappe import _


def _current_client():
    """Get current logged-in Investigation Client doc."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Login richiesto"), frappe.PermissionError)
    user = frappe.session.user
    name = frappe.db.get_value("Investigation Client",
                               {"platform_user": user}, "name")
    if not name:
        frappe.throw(_("Profilo cliente mancante. Vai su /signup."))
    return frappe.get_doc("Investigation Client", name)


def _stripe():
    """Lazy Stripe client."""
    try:
        import stripe
    except ImportError:
        frappe.throw(_("Modulo stripe non installato sul backend."))
    key = frappe.conf.get("stripe_secret_key")
    if not key:
        frappe.throw(_("Stripe non configurato (manca stripe_secret_key)."))
    stripe.api_key = key
    return stripe


@frappe.whitelist(methods=["POST"])
def create_setup_intent() -> dict:
    """Crea Stripe Customer (se non esiste) + SetupIntent per il client corrente."""
    c = _current_client()
    stripe = _stripe()

    cust_id = c.stripe_customer_id
    if not cust_id:
        cust = stripe.Customer.create(
            email=c.email,
            name=c.client_name,
            metadata={"investigation_client": c.name, "client_type": c.client_type or ""},
        )
        cust_id = cust.id
        c.db_set("stripe_customer_id", cust_id, commit=True)

    intent = stripe.SetupIntent.create(
        customer=cust_id,
        usage="off_session",
        payment_method_types=["card"],
        metadata={
            "investigation_client": c.name,
            "client_name": c.client_name,
            "purpose": "onboarding_verification",
        },
    )

    return {
        "ok": True,
        "client_secret": intent.client_secret,
        "setup_intent_id": intent.id,
        "customer": cust_id,
    }


@frappe.whitelist(methods=["POST"])
def confirm_payment_method(payment_method_id: str) -> dict:
    """Attach payment method to customer, set as default, mark client verified."""
    c = _current_client()
    stripe = _stripe()
    if not payment_method_id or not payment_method_id.startswith("pm_"):
        return {"ok": False, "error": "payment_method_id invalid"}

    try:
        stripe.PaymentMethod.attach(payment_method_id, customer=c.stripe_customer_id)
        stripe.Customer.modify(
            c.stripe_customer_id,
            invoice_settings={"default_payment_method": payment_method_id},
        )
    except Exception as e:
        return {"ok": False, "error": f"Stripe: {str(e)[:200]}"}

    c.db_set("stripe_payment_method", payment_method_id, commit=False)
    c.db_set("payment_method_added", 1, commit=False)
    # Advance onboarding: Pending Card → Pending KYC/KYB
    next_status = "Pending KYC" if c.client_type == "Individual" else "Pending KYB"
    c.db_set("onboarding_status", next_status, commit=False)
    # KYB applies to all non-Individual; KYC only to Individual
    if c.client_type == "Individual":
        c.db_set("kyc_status", "In Progress", commit=False)
    else:
        c.db_set("kyb_status", "In Progress", commit=False)
    frappe.db.commit()

    # Audit log
    try:
        frappe.get_doc({
            "doctype": "Diplomatic Audit Log",
            "event_type": "onboarding.payment_method_added",
            "new_value": next_status,
            "reason": frappe.as_json({
                "client": c.name,
                "stripe_customer_id": c.stripe_customer_id,
                "payment_method_id": payment_method_id,
            })[:500],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {
        "ok": True,
        "next_status": next_status,
        "next_url": "/onboarding/kyc" if c.client_type == "Individual" else "/onboarding/kyb",
    }


@frappe.whitelist(methods=["POST"])
def submit_kyc() -> dict:
    """Finalize KYC submission: set status Pending Review, create KYC Check."""
    c = _current_client()
    if c.client_type != "Individual":
        return {"ok": False, "error": "KYC valido solo per Cliente privato."}

    files = frappe.get_all("File",
        filters={"attached_to_doctype": "Investigation Client", "attached_to_name": c.name},
        fields=["name", "file_url", "file_name"], limit=20)
    if len(files) < 2:
        return {"ok": False, "error": "Carica almeno documento d'identità e selfie."}

    parts = (c.client_name or "").split()
    kyc = frappe.get_doc({
        "doctype": "KYC Check",
        "client": c.name,
        "first_name": parts[0] if parts else c.client_name,
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
        "status": "In Review",
    })
    kyc.flags.ignore_permissions = True
    kyc.insert(ignore_permissions=True)

    for f in files:
        frappe.db.set_value("File", f.name, {
            "attached_to_doctype": "KYC Check",
            "attached_to_name": kyc.name,
        }, update_modified=False)

    c.db_set("kyc_status", "In Review", commit=False)
    c.db_set("onboarding_status", "Under Review", commit=False)
    c.db_set("onboarding_completed_at", frappe.utils.now_datetime(), commit=False)
    frappe.db.commit()

    try:
        frappe.get_doc({
            "doctype": "Diplomatic Audit Log",
            "event_type": "onboarding.kyc_submitted",
            "new_value": "In Review",
            "reason": frappe.as_json({"client": c.name, "kyc_check": kyc.name, "files": len(files)})[:500],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {"ok": True, "next_url": "/onboarding"}


@frappe.whitelist(methods=["POST"])
def submit_kyb() -> dict:
    """Finalize KYB submission: set status Pending Review, create KYB Check."""
    c = _current_client()
    if c.client_type == "Individual":
        return {"ok": False, "error": "KYB valido solo per Azienda/Studio."}

    files = frappe.get_all("File",
        filters={"attached_to_doctype": "Investigation Client", "attached_to_name": c.name},
        fields=["name", "file_url", "file_name"], limit=20)
    if len(files) < 1:
        return {"ok": False, "error": "Carica almeno la visura camerale."}

    kyb = frappe.get_doc({
        "doctype": "KYB Check",
        "client": c.name,
        "company_name": c.client_name,
        "company_country": c.country,
        "registered_address": c.address,
        "status": "In Review",
    })
    kyb.flags.ignore_permissions = True
    kyb.insert(ignore_permissions=True)

    for f in files:
        frappe.db.set_value("File", f.name, {
            "attached_to_doctype": "KYB Check",
            "attached_to_name": kyb.name,
        }, update_modified=False)

    c.db_set("kyb_status", "In Review", commit=False)
    c.db_set("onboarding_status", "Under Review", commit=False)
    c.db_set("onboarding_completed_at", frappe.utils.now_datetime(), commit=False)
    frappe.db.commit()

    try:
        frappe.get_doc({
            "doctype": "Diplomatic Audit Log",
            "event_type": "onboarding.kyb_submitted",
            "new_value": "In Review",
            "reason": frappe.as_json({"client": c.name, "kyb_check": kyb.name, "files": len(files)})[:500],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {"ok": True, "next_url": "/onboarding"}
