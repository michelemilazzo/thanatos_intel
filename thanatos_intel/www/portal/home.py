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
    # Servizi speciali riservati: abilitati per-cliente lato operatore (console wc),
    # letti server-side dall'API wallet-saas. Mai rompere il portale se l'API e' giu'.
    context.special_services = []
    try:
        _sp_tok = frappe.conf.get('thanatos_special_token')
        if is_client and _sp_tok:
            import requests
            _sp_r = requests.get('https://wallet.onekeyco.com/api/portal/special',
                                 params={'client': user, 'k': _sp_tok}, timeout=4)
            if _sp_r.ok:
                context.special_services = (_sp_r.json() or {}).get('services', []) or []
    except Exception:
        context.special_services = []
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
        _steps = frappe.get_all("Case Step Instance",
                                filters={"parenttype": "Investigation Case", "parent": c["name"]},
                                fields=["step_label", "status", "client_visible"], order_by="seq asc")
        _tot = len(_steps)
        _done = sum(1 for x in _steps if x.status in ("Done", "Skipped"))
        _cur = next((x for x in _steps if x.status in ("In Progress", "Awaiting Client")), None)
        c["step_total"] = _tot
        c["step_done"] = _done
        c["step_pct"] = int(_done * 100 / _tot) if _tot else 0
        c["current_step"] = _cur.step_label if _cur else ""
        c["awaiting_client"] = 1 if (_cur and _cur.status == "Awaiting Client" and _cur.client_visible) else 0
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

    # Pending actions dalla pipeline
    from thanatos_intel.pipeline.pipeline import get_pipeline
    pending_client_actions = []
    pending_operator_actions = []
    for c in cases:
        if (c.get("case_status") or "").lower() in ("completed", "closed", "archived"):
            continue
        try:
            pipeline_key = frappe.db.get_value("Case Type", c.get("case_type"), "pipeline_key") or ""
            case_dict = dict(c)
            case_dict["pipeline_key"] = pipeline_key
            if not case_dict.get("case_status"):
                case_dict["case_status"] = ""
            if c.get("case_type") and not case_dict.get("client_type"):
                client_val = frappe.db.get_value("Investigation Case", c["name"], "client")
                if client_val:
                    case_dict["client_type"] = frappe.db.get_value(
                        "Investigation Client", client_val, "client_type") or ""
            steps = get_pipeline(case_dict)
            for step in steps:
                if step["status"] != "current":
                    continue
                if step["actor"] == "client":
                    pending_client_actions.append({
                        "case_name": c["name"],
                        "case_title": c.get("case_title") or c["name"],
                        "step_label": step["label"],
                        "step_description": step["description"],
                        "portal_url": step.get("portal_url") or f"/portal/case/{c['name']}",
                    })
                elif step["actor"] == "operator":
                    pending_operator_actions.append({
                        "case_name": c["name"],
                        "case_title": c.get("case_title") or c["name"],
                        "step_label": step["label"],
                        "step_description": step["description"],
                        "desk_url": step.get("desk_url") or f"/app/investigation-case/{c['name']}",
                    })
        except Exception:
            pass

    context.pending_client_actions = pending_client_actions
    context.pending_operator_actions = pending_operator_actions

    try:
        from thanatos_intel.permissions import is_full_access, visible_case_names
        if is_full_access(frappe.session.user):
            context.spid_pending = frappe.db.count("SPID Document Request", {"status": "Richiesto"})
        else:
            _n = visible_case_names(frappe.session.user) or []
            context.spid_pending = frappe.db.count(
                "SPID Document Request",
                {"status": "Richiesto", "investigation_case": ["in", _n]}) if _n else 0
        try:
            from thanatos_intel.integrations.mmos_sign_bridge import my_pending_mandates
            context.spid_pending += len(my_pending_mandates(frappe.session.user))
        except Exception:
            pass
    except Exception:
        context.spid_pending = 0
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
    """Billing reale dal cliente: Usage Events (paid/pending) + abbonamento Stripe."""
    out = {"proformas": [], "invoices": [], "proforma_open": 0, "invoice_unpaid": 0}
    client_name = frappe.db.get_value("Investigation Client", {"platform_user": user}, "name")
    if not client_name:
        return out

    # Usage Events pagati → mostrali come "fatture"
    try:
        paid_ues = frappe.get_all("Usage Event",
            filters={"client": client_name, "status": ["in", ["Paid", "Invoiced"]]},
            fields=["name", "service", "total", "currency", "paid_at", "creation"],
            order_by="creation desc", limit=8)
        for ue in paid_ues:
            out["invoices"].append({
                "name": ue.name,
                "posting_date": ue.paid_at or ue.creation,
                "grand_total": float(ue.total or 0),
                "outstanding_amount": 0,
                "currency": ue.currency or "EUR",
                "status": "Paid",
                "_label": ue.service or "Servizio",
            })
    except Exception:
        pass

    # Abbonamento attivo → mostra come riga separata
    try:
        subs = frappe.get_all("Stripe Subscription",
            filters={"investigation_client": client_name,
                     "status": ["in", ["active", "trialing"]]},
            fields=["name", "subscription_plan", "amount", "currency",
                    "current_period_end", "status"],
            limit=1)
        for s in subs:
            out["invoices"].append({
                "name": s.name,
                "posting_date": s.current_period_end,
                "grand_total": float(s.amount or 0),
                "outstanding_amount": 0,
                "currency": (s.currency or "EUR").upper(),
                "status": s.status,
                "_label": f"Abbonamento {s.subscription_plan or ''}",
            })
    except Exception:
        pass

    # Usage Events pending → "da saldare" (proformas)
    try:
        pending_ues = frappe.get_all("Usage Event",
            filters={"client": client_name, "status": "Pending"},
            fields=["name", "service", "total", "currency", "creation"],
            order_by="creation desc", limit=5)
        for ue in pending_ues:
            out["proformas"].append({
                "name": ue.name,
                "transaction_date": ue.creation,
                "grand_total": float(ue.total or 0),
                "currency": ue.currency or "EUR",
                "status": "Pending",
                "_label": ue.service or "Servizio",
            })
        out["proforma_open"] = len(out["proformas"])
        out["invoice_unpaid"] = len(out["proformas"])
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
