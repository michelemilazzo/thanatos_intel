import frappe
from frappe import _


no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal"
        raise frappe.Redirect

    user = frappe.session.user
    roles = set(frappe.get_roles(user))

    is_investigator = "Investigator" in roles or "Investigation Manager" in roles
    is_lawyer = "Law Firm Portal User" in roles
    is_accountant = "Accountant Portal User" in roles
    is_client = "Client Portal User" in roles or not (is_investigator or is_lawyer or is_accountant)

    context.user = user
    context.user_fullname = frappe.db.get_value("User", user, "full_name") or user
    context.is_investigator = is_investigator
    context.is_lawyer = is_lawyer
    context.is_accountant = is_accountant
    context.is_client = is_client
    context.role_label = (
        "Investigator" if is_investigator else
        "Law Firm" if is_lawyer else
        "Accountant" if is_accountant else
        "Client"
    )

    case_fields = ["name", "case_number", "case_title", "status", "case_type",
                   "priority", "creation"]
    if is_investigator:
        cases = frappe.get_all("Investigation Case", fields=case_fields,
                               order_by="creation desc", limit=50)
    else:
        client_names = frappe.get_all("Investigation Client",
                                      filters={"platform_user": user}, pluck="name")
        if client_names:
            cases = frappe.get_all("Investigation Case",
                                   filters={"client": ["in", client_names]},
                                   fields=case_fields, order_by="creation desc", limit=50)
        else:
            cases = []
    for c in cases:
        c["case_status"] = c.pop("status", None)

    for c in cases:
        c["evidence_count"] = frappe.db.count("Investigation Evidence",
                                              {"investigation_case": c["name"]})
        c["report_count"] = frappe.db.count("Investigation Report",
                                            {"investigation_case": c["name"]})
    context.in_progress = sum(1 for c in cases if (c.get("case_status") or "").lower() in ("in progress","investigation"))
    context.closed = sum(1 for c in cases if (c.get("case_status") or "").lower() == "closed")
    context.evidence_total = sum(c.get("evidence_count") or 0 for c in cases)

    context.cases = cases
    context.case_count = len(cases)
    context.title = "Portal — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
