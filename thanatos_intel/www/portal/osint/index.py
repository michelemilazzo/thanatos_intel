import frappe


no_cache = 1


def get_context(context):
    context.body_class = 'osint-page'
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/osint"
        raise frappe.Redirect

    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    context.user = user
    context.user_fullname = frappe.db.get_value("User", user, "full_name") or user
    context.can_run_deep = bool(roles & {"Investigator", "Investigation Manager",
                                          "Lawyer", "Accountant", "System Manager"})

    context.recent_jobs = []
    try:
        if frappe.db.exists("DocType", "OSINT Job"):
            from thanatos_intel.permissions import (is_full_access,
                                                     visible_case_names,
                                                     _client_records)
            fields = ["name", "title", "target_type", "target_value",
                      "mode", "status", "risk_score", "risk_band",
                      "summary", "creation"]
            if is_full_access(user):
                jobs = frappe.get_all("OSINT Job", fields=fields,
                                      order_by="creation desc", limit=15)
            else:
                # solo job propri: richiesti da me, o sui miei casi/client
                case_names = visible_case_names(user) or []
                clients = _client_records(user)
                or_filters = [["requested_by", "=", user]]
                if case_names:
                    or_filters.append(["investigation_case", "in", case_names])
                if clients:
                    or_filters.append(["client", "in", clients])
                jobs = frappe.get_all("OSINT Job", fields=fields,
                                      or_filters=or_filters,
                                      order_by="creation desc", limit=15)
            context.recent_jobs = jobs
    except Exception:
        pass

    context.title = "OSINT Console — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
