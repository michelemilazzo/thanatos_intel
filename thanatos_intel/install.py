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
    _ensure_case_billing_fields()


def after_migrate():
    ensure_pdf_settings()
    _ensure_case_billing_fields()


def _ensure_case_billing_fields():
    from thanatos_intel.billing.case_billing import ensure_case_billing_fields
    ensure_case_billing_fields()


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
