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

    from thanatos_intel.permissions import is_full_access, visible_case_names
    case_fields = ["name", "case_number", "case_title", "status", "case_type",
                   "priority", "creation"]
    if is_full_access(user):
        # Administrator / Investigation Manager / System Manager → tutto
        cases = frappe.get_all("Investigation Case", fields=case_fields,
                               order_by="creation desc", limit=50)
    else:
        # ognuno vede solo i propri casi (assegnati, owner, o dei propri client)
        names = visible_case_names(user) or []
        if names:
            cases = frappe.get_all("Investigation Case",
                                   filters={"name": ["in", names]},
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
    context.recent_activity = _recent_activity(cases, is_full_access(user))

    # Vista cliente: documenti (report scaricabili) + billing (proforme/fatture)
    if is_client:
        context.client_documents = _client_documents(cases)
        bill = _client_billing(user)
        context.proformas = bill["proformas"]
        context.invoices = bill["invoices"]
        context.proforma_open = bill["proforma_open"]
        context.invoice_unpaid = bill["invoice_unpaid"]
        context.documents_total = len(context.client_documents)
    else:
        context.client_documents = []
        context.proformas = []
        context.invoices = []
        context.proforma_open = 0
        context.invoice_unpaid = 0
        context.documents_total = 0

    context.title = "Portal — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context


def _client_documents(cases):
    """Report finalizzati/scaricabili dei casi del cliente."""
    case_names = [c["name"] for c in cases] if cases else []
    if not case_names:
        return []
    docs = []
    try:
        for r in frappe.get_all(
            "Investigation Report",
            filters={"investigation_case": ["in", case_names]},
            fields=["name", "report_title", "report_status", "report_date",
                    "pdf_file", "investigation_case"],
            order_by="report_date desc, creation desc", limit=12):
            if not r.pdf_file:
                continue
            docs.append({
                "title": r.report_title or r.name,
                "case": r.investigation_case,
                "status": r.report_status,
                "date": r.report_date,
                "url": r.pdf_file,
            })
    except Exception:
        pass
    return docs


def _client_billing(user):
    """Proforme (Quotation) e fatture (Sales Invoice) del cliente."""
    out = {"proformas": [], "invoices": [], "proforma_open": 0, "invoice_unpaid": 0}
    customer = frappe.db.get_value("Investigation Client", {"platform_user": user}, "erp_customer_id")
    if not customer:
        return out
    try:
        out["proformas"] = frappe.get_all(
            "Quotation",
            filters={"party_name": customer, "quotation_to": "Customer"},
            fields=["name", "transaction_date", "grand_total", "currency", "status"],
            order_by="transaction_date desc", limit=8) or []
        out["proforma_open"] = sum(1 for q in out["proformas"]
                                   if (q.get("status") or "") in ("Draft", "Open", "Submitted"))
    except Exception:
        pass
    try:
        out["invoices"] = frappe.get_all(
            "Sales Invoice",
            filters={"customer": customer},
            fields=["name", "posting_date", "grand_total", "outstanding_amount",
                    "currency", "status"],
            order_by="posting_date desc", limit=8) or []
        out["invoice_unpaid"] = sum(1 for i in out["invoices"]
                                    if (i.get("outstanding_amount") or 0) > 0)
    except Exception:
        pass
    return out


def _recent_activity(cases, is_investigator):
    items = []
    case_names = [c["name"] for c in cases] if cases else []
    flt_ev = {} if is_investigator else ({"investigation_case": ["in", case_names]} if case_names else None)
    if flt_ev is not None:
        try:
            for e in frappe.get_all("Investigation Evidence", filters=flt_ev,
                                    fields=["name", "evidence_title", "creation"],
                                    order_by="creation desc", limit=5):
                items.append({"kind": "Evidence",
                              "label": e.evidence_title or e.name, "when": e.creation})
        except Exception:
            pass
        try:
            for r in frappe.get_all("Investigation Report", filters=flt_ev,
                                    fields=["name", "report_title", "creation"],
                                    order_by="creation desc", limit=5):
                items.append({"kind": "Report",
                              "label": r.report_title or r.name, "when": r.creation})
        except Exception:
            pass
    if case_names:
        try:
            for o in frappe.get_all("OSINT Lookup",
                                    filters={"investigation_case": ["in", case_names]},
                                    fields=["name", "lookup_type", "target", "creation"],
                                    order_by="creation desc", limit=5):
                items.append({"kind": "OSINT",
                              "label": f"{o.lookup_type}: {o.target}", "when": o.creation})
        except Exception:
            pass
    items.sort(key=lambda x: x["when"] or "", reverse=True)
    return items[:8]
