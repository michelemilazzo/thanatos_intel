import frappe
from frappe import _

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal"
        raise frappe.Redirect

    case_id = frappe.form_dict.get("name") or _from_path()
    if not case_id:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    user = frappe.session.user
    from thanatos_intel.permissions import is_full_access, visible_case_names
    is_investigator = is_full_access(user)

    if not is_full_access(user):
        names = visible_case_names(user) or []
        if case_id not in names:
            frappe.throw(_("Accesso negato a questo caso."), frappe.PermissionError)

    case = frappe.get_doc("Investigation Case", case_id)
    evidences = frappe.get_all(
        "Investigation Evidence",
        filters={"investigation_case": case.name},
        fields=["name", "evidence_name", "evidence_type", "custody_status",
                "hash_value", "acquisition_date", "attached_file"],
        order_by="acquisition_date desc",
    )
    reports = frappe.get_all(
        "Investigation Report",
        filters={"investigation_case": case.name},
        fields=["name", "report_title", "report_status", "report_date",
                "pdf_file", "pdf_hash"],
        order_by="creation desc",
    )

    context.case = case
    context.evidences = evidences
    context.reports = reports
    context.is_investigator = is_investigator
    context.title = f"{case.case_number or case.name} — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context


def _from_path():
    try:
        path = frappe.local.request.path.rstrip("/")
        parts = path.split("/")
        if len(parts) >= 4 and parts[-2] == "case":
            return parts[-1]
    except Exception:
        pass
    return None
