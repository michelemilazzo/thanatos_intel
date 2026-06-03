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
    roles = set(frappe.get_roles(user))
    is_investigator = "Investigator" in roles or "Investigation Manager" in roles

    if not is_investigator:
        client_names = frappe.get_all(
            "Investigation Client",
            filters={"platform_user": user},
            pluck="name",
        )
        owns = frappe.db.exists("Investigation Case",
                                {"name": case_id, "client": ["in", client_names or [""]]})
        if not owns:
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
