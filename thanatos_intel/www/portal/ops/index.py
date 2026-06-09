import frappe
from collections import defaultdict

no_cache = 1

CLOSED_STATUSES = {"Completed", "Closed", "Archived", "completed", "closed", "archived"}


def get_context(context):
    user = frappe.session.user
    if user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/ops"
        raise frappe.Redirect

    roles = set(frappe.get_roles(user))
    is_operator = "Investigator" in roles or "Investigation Manager" in roles or "System Manager" in roles
    if not is_operator:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    from thanatos_intel.pipeline.pipeline import get_pipeline

    cases = frappe.get_all(
        "Investigation Case",
        filters={"status": ["not in", list(CLOSED_STATUSES)]},
        fields=["name", "case_number", "case_title", "status", "case_type", "priority", "client"],
        order_by="creation desc",
        limit=200,
    )

    for c in cases:
        c["case_status"] = c.pop("status", "") or ""

    # Risolvi pipeline_key e client_type in bulk
    case_types_seen = {c["case_type"] for c in cases if c.get("case_type")}
    pipeline_key_map = {}
    for ct in case_types_seen:
        pk = frappe.db.get_value("Case Type", ct, "pipeline_key")
        pipeline_key_map[ct] = pk or ct

    client_ids = {c["client"] for c in cases if c.get("client")}
    client_type_map = {}
    if client_ids:
        for row in frappe.get_all(
            "Investigation Client",
            filters={"name": ["in", list(client_ids)]},
            fields=["name", "client_type"],
        ):
            client_type_map[row["name"]] = row["client_type"]

    # Calcola step corrente per ogni caso
    by_step = defaultdict(list)
    total_pending = 0

    for c in cases:
        try:
            c["pipeline_key"] = pipeline_key_map.get(c.get("case_type") or "", "")
            c["client_type"] = client_type_map.get(c.get("client") or "", "")
            steps = get_pipeline(c)
            current = next((s for s in steps if s["status"] == "current"), None)
            if current:
                c["current_step_label"] = current["label"]
                c["current_step_actor"] = current["actor"]
                c["current_step_key"] = current["key"]
                c["desk_url"] = current.get("desk_url") or f"/app/investigation-case/{c['name']}"
                c["portal_url"] = current.get("portal_url") or ""
                c["step_description"] = current.get("description", "")
                by_step[current["label"]].append(c)
                if current["actor"] == "operator":
                    total_pending += 1
            else:
                c["current_step_label"] = "—"
                c["current_step_actor"] = ""
                c["desk_url"] = f"/app/investigation-case/{c['name']}"
                by_step["Completato / in attesa"].append(c)
        except Exception:
            c["current_step_label"] = "Errore pipeline"
            c["current_step_actor"] = ""
            c["desk_url"] = f"/app/investigation-case/{c['name']}"
            by_step["Errore pipeline"].append(c)

    # Ordine preferito delle colonne
    STEP_ORDER = [
        "Verifica identità (KYB/KYC)",
        "Mandato d'incarico",
        "Firma mandato",
        "Preventivo DDD",
        "Preventivo",
        "Pagamento",
        "Analisi passaporto",
        "Verifica sanzioni",
        "Raccolta evidenze",
        "OSINT / Lookup",
        "Analisi antifrode",
        "Verifica blacklist",
        "Report finale",
        "Report",
        "Pratica chiusa",
        "Chiuso",
        "Completato / in attesa",
        "Errore pipeline",
    ]

    groups = []
    seen = set()
    for label in STEP_ORDER:
        if label in by_step:
            groups.append({"label": label, "cases": by_step[label]})
            seen.add(label)
    for label, cases_list in by_step.items():
        if label not in seen:
            groups.append({"label": label, "cases": cases_list})

    context.groups = groups
    context.total_open = len(cases)
    context.total_pending = total_pending
    context.title = "Centro Operativo — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
