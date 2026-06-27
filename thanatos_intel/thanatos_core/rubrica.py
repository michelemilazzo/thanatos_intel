"""Rubrica clienti Thanatos — lista ricercabile + scheda 360° con timeline
unificata (casi, appuntamenti, chiamate, comunicazioni, fatture, credito).
Pagina desk /app/thanatos-rubrica. Ogni blocco è best-effort.
"""
import frappe
from frappe.utils import flt


def _all(dt, **kw):
    try:
        return frappe.get_all(dt, **kw)
    except Exception:
        return []


@frappe.whitelist()
def clients_list(search="", client_type="", onboarding="", limit=400):
    filters = {}
    if client_type:
        filters["client_type"] = client_type
    if onboarding:
        filters["onboarding_status"] = onboarding
    or_filters = None
    if search:
        s = "%" + search.strip() + "%"
        or_filters = [{"client_name": ["like", s]}, {"email": ["like", s]},
                      {"phone": ["like", s]}, {"vat_number": ["like", s]},
                      {"codice_fiscale": ["like", s]}]
    return _all("Investigation Client", filters=filters, or_filters=or_filters,
                fields=["name", "client_name", "client_type", "email", "phone", "country",
                        "onboarding_status", "kyc_status", "kyb_status", "subscription_status",
                        "total_cases", "total_spent", "service_credit", "modified"],
                order_by="modified desc", limit=limit)


@frappe.whitelist()
def client_detail(client):
    c = frappe.get_doc("Investigation Client", client)
    tl = []

    cases = _all("Investigation Case", filters={"client": client},
                 fields=["name", "case_title", "status", "priority", "opening_date", "payment_status", "assigned_investigator"],
                 order_by="opening_date desc")
    case_names = [x.name for x in cases]

    def _full_name(u):
        if not u:
            return ""
        return frappe.db.get_value("User", u, "full_name") or u

    for x in cases:
        gestore = _full_name(x.assigned_investigator)
        title = x.case_title or x.name
        if gestore:
            title += f" · gestore: {gestore}"
        tl.append({"when": str(x.opening_date or ""), "icon": "📂", "kind": "Caso",
                   "title": title, "tag": x.status, "dt": "Investigation Case", "ref": x.name})

    for a in _all("Investigation Appointment", filters={"linked_client": client},
                  fields=["name", "title", "appointment_type", "appointment_date", "status", "outcome"],
                  order_by="appointment_date desc", limit=50):
        _tag = a.status + ((" · esito: " + a.outcome) if a.get("outcome") else "")
        tl.append({"when": str(a.appointment_date or ""), "icon": "📅", "kind": a.appointment_type or "Appuntamento",
                   "title": a.title or a.name, "tag": _tag, "dt": "Investigation Appointment", "ref": a.name})

    for cl in _all("Call Log", filters={"linked_client": client},
                   fields=["name", "called_at", "direction", "caller_name", "outcome"],
                   order_by="called_at desc", limit=50):
        tl.append({"when": str(cl.called_at or "")[:16], "icon": "📞",
                   "kind": "Chiamata " + (cl.direction or ""), "title": cl.caller_name or cl.name,
                   "tag": cl.outcome or "", "dt": "Call Log", "ref": cl.name})

    if case_names:
        for cm in _all("Communication Log", filters={"investigation_case": ["in", case_names]},
                       fields=["name", "channel", "direction", "occurred_at", "counterparty_name", "investigation_case"],
                       order_by="occurred_at desc", limit=80):
            tl.append({"when": str(cm.occurred_at or "")[:16], "icon": "✉️",
                       "kind": (cm.channel or "Msg") + " " + (cm.direction or ""),
                       "title": cm.counterparty_name or cm.investigation_case,
                       "tag": "", "dt": "Communication Log", "ref": cm.name})

    invoices = []
    if c.get("customer"):
        invoices = _all("Sales Invoice", filters={"customer": c.customer},
                        fields=["name", "posting_date", "grand_total", "status", "outstanding_amount"],
                        order_by="posting_date desc", limit=50)
        for i in invoices:
            tl.append({"when": str(i.posting_date or ""), "icon": "💳", "kind": "Fattura",
                       "title": i.name + " · €" + str(int(flt(i.grand_total))), "tag": i.status,
                       "dt": "Sales Invoice", "ref": i.name})

    for cr in _all("Credit Ledger", filters={"client": client},
                   fields=["name", "kind", "amount", "balance_after", "creation", "notes"],
                   order_by="creation desc", limit=50):
        tl.append({"when": str(cr.creation or "")[:16], "icon": "🪙",
                   "kind": "Credito " + (cr.kind or ""),
                   "title": (cr.notes or "") + " (€" + str(int(flt(cr.amount))) + ")",
                   "tag": "", "dt": "Credit Ledger", "ref": cr.name})

    tl.sort(key=lambda x: x["when"] or "", reverse=True)
    outstanding = sum(flt(i.outstanding_amount) for i in invoices)

    info = {f: c.get(f) for f in [
        "name", "client_name", "client_type", "email", "phone", "country", "vat_number",
        "codice_fiscale", "address", "onboarding_status", "kyc_status", "kyb_status",
        "subscription_status", "subscription_plan", "total_cases", "total_spent",
        "service_credit", "customer", "platform_user", "my_referral_code", "referred_by",
        "attribution_source", "sales_partner", "preferred_language"]}

    return {
        "info": info,
        "cases": cases,
        "timeline": tl[:150],
        "stats": {"cases": len(cases), "invoices": len(invoices),
                  "outstanding": outstanding,
                  "spent": flt(c.get("total_spent")), "credit": flt(c.get("service_credit"))},
    }


@frappe.whitelist()
def find_duplicates():
    """Segnala possibili duplicati per email/phone/vat uguali."""
    dups = []
    for field in ("email", "phone", "vat_number"):
        rows = frappe.db.sql(f"""
            select {field} v, count(*) n, group_concat(name) names
            from `tabInvestigation Client`
            where ifnull({field},'')!='' group by {field} having n>1 limit 20""", as_dict=True)
        for r in rows:
            dups.append({"field": field, "value": r.v, "count": r.n, "names": (r.names or "").split(",")})
    return dups
