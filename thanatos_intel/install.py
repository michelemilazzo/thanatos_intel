import frappe


THANATOS_ROLES = [
    "Thanatos Investigator",
    "Thanatos Analyst",
    "Thanatos Supervisor",
    "Thanatos Intake Officer",
    "Thanatos Compliance Officer",
    "Thanatos Legal Officer",
    "Thanatos Director",
    "Thanatos Auditor",
    "Thanatos Applicant Portal User",
]


def after_install():
    create_roles()
    ensure_pdf_settings()
    _setup_pipeline()


def after_migrate():
    ensure_pdf_settings()
    _setup_pipeline()
    _seed_workflow()
    _register_kyc_provider()
    _ensure_client_address_fields()
    try:
        from thanatos_intel.patches.appointment_outcome import apply as _ao; _ao()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ensure_appointment_outcome")
    try:
        from thanatos_intel.patches.crypto_recovery_scam_blacklist import apply as _crs; _crs()
    except Exception:
        pass
    try:
        from thanatos_intel.patches.contact_fields import apply as _cf; _cf()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ensure_contact_fields")
    try:
        from thanatos_intel.patches.fix_deprecated_status import apply as _fds; _fds()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "fix_deprecated_status")
    try:
        from thanatos_intel.patches.soggetto_links import apply as _sl; _sl()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "soggetto_links")
    try:
        from thanatos_intel.patches.file_client_visibility import apply as _fcv; _fcv()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "file_client_visibility")


def _ensure_client_address_fields():
    try:
        from thanatos_intel.patches.client_address_fields import apply
        apply()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ensure_client_address_fields")


def _register_kyc_provider():
    """Aggancia il KYC Thanatos (Vault) a mmos_sign come provider (idempotente)."""
    if "mmos_sign" not in frappe.get_installed_apps():
        return
    try:
        meta = frappe.get_meta("Signing Settings")
        if meta.has_field("kyc_provider"):
            path = "thanatos_intel.kyc.ThanatosKycProvider"
            if frappe.db.get_single_value("Signing Settings", "kyc_provider") != path:
                frappe.db.set_single_value("Signing Settings", "kyc_provider", path)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "register_kyc_provider")


def _seed_workflow():
    from thanatos_intel.workflow.seed import seed_workflow
    seed_workflow()


def _setup_pipeline():
    from thanatos_intel.billing.case_billing import ensure_case_billing_fields
    from thanatos_intel.billing.crm_pipeline import setup_pipeline
    ensure_case_billing_fields()
    setup_pipeline()


def create_roles():
    for role_name in THANATOS_ROLES:
        if not frappe.db.exists("Role", role_name):
            role = frappe.get_doc({
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
            })
            role.insert(ignore_permissions=True)
    frappe.db.commit()


def ensure_pdf_settings():
    """PDF stampe: letter head inline (repeat_header_footer=0) e A4.
    Con repeat_header_footer=1 il letter head finisce nella header-zone ad
    altezza fissa di wkhtmltopdf e logo+intestazione vengono tagliati."""
    ps = frappe.get_single("Print Settings")
    changed = False
    if ps.repeat_header_footer:
        ps.repeat_header_footer = 0
        changed = True
    if ps.pdf_page_size != "A4":
        ps.pdf_page_size = "A4"
        changed = True
    if changed:
        ps.save(ignore_permissions=True)
        frappe.db.commit()
