"""Architetto AI del caso Thanatos.

Dato il bisogno (testo libero) di un cliente, l'AI progetta il percorso su misura:
step, documenti, servizi del catalogo, gap di capacità (cosa NON copriamo ->
app Frappe già pronte), preventivo. Può materializzare un Investigation Case.
Riusa il gateway MMOS AI (ai.doc_ingest._gateway).
"""
import json
import re
import frappe
from frappe.utils import now_datetime

_SYS = (
    "Sei l'Architetto AI di Thanatos Intel, agenzia investigativa europea (sede RO, "
    "GDPR/Legea 329-2003). Dato il bisogno di un cliente progetti il percorso su misura. "
    "Rispondi SOLO con un oggetto JSON valido, nessun testo fuori dal JSON, con schema:\n"
    "{\"case_title\": str, \"summary\": str, "
    "\"steps\": [{\"label\": str, \"actor\": \"operatore\"|\"cliente\", \"action\": str, \"service_code\": str|null}], "
    "\"documents\": [str], \"services\": [str], "
    "\"capability_gaps\": [{\"need\": str, \"suggested_frappe_app\": str, \"note\": str}], "
    "\"quote\": [{\"item\": str, \"amount_eur\": number}], \"next_action\": str}\n"
    "REGOLE: usa SOLO i service_code forniti nel catalogo. Se serve una capacità software che "
    "non abbiamo, NON inventarla: mettila in capability_gaps e suggerisci un'app Frappe ESISTENTE "
    "(es. Raven=chat/messaggistica, Helpdesk=ticket, Gameplan=collaborazione, Drive=file). "
    "Prezzi indicativi in EUR. Italiano."
)


def _resp_text(resp):
    # usa l'estrattore già provato di ai_concierge (formato gateway corretto)
    try:
        from thanatos_intel.workflow.ai_concierge import _resp_text as _ac
        t = _ac(resp)
        if t:
            return t
    except Exception:
        pass
    if not resp:
        return ""
    for k in ("text", "response", "content", "message", "answer", "output"):
        v = resp.get(k) if isinstance(resp, dict) else None
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _parse_json(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    raw = m.group(0) if m else text
    try:
        return json.loads(raw)
    except Exception:
        return None


def _catalog():
    rows = frappe.get_all("Service Catalog", filters={"is_active": 1},
                          fields=["service_code", "service_name", "category", "price", "price_min", "currency"],
                          order_by="category asc", limit=0)
    return rows


@frappe.whitelist()
def plan_from_request(request, client=None):
    from thanatos_intel.ai.doc_ingest import _gateway
    if not (request or "").strip():
        return {"ok": False, "error": "Descrivi il bisogno del cliente."}
    services = _catalog()
    apps = frappe.get_installed_apps()
    catalog = "\n".join(
        f"{s.service_code} | {s.category} | {s.service_name} | "
        f"{s.price_min or s.price or '?'} {s.currency or 'EUR'}" for s in services)
    msg = (f"Bisogno del cliente:\n{request}\n\n"
           f"App Frappe già installate: {', '.join(apps)}\n\n"
           f"Catalogo servizi (service_code | categoria | nome | prezzo):\n{catalog}\n\n"
           "Progetta il percorso su misura. Rispondi SOLO JSON.")
    resp = _gateway(msg, system=_SYS, task_type="chat")
    text = _resp_text(resp)
    plan = _parse_json(text)
    # metering best-effort
    try:
        usage = (resp or {}).get("usage") or {}
        if usage.get("tokens_in") or usage.get("tokens_out"):
            from thanatos_intel.billing.ai_meter import record_usage
            record_usage(client=client, model=(resp or {}).get("model", "default"),
                         tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
                         reference="case-architect")
    except Exception:
        pass
    if not plan:
        return {"ok": False, "error": "AI non disponibile o risposta non valida.", "raw": text[:400]}
    return {"ok": True, "plan": plan}


@frappe.whitelist()
def create_case_from_plan(plan, client=None):
    """Materializza il piano AI in un Investigation Case reale con i suoi step."""
    if isinstance(plan, str):
        plan = json.loads(plan)
    roles = set(frappe.get_roles())
    if not (roles & {"System Manager", "Investigation Manager", "Investigator",
                     "Thanatos Investigator", "Thanatos Supervisor", "Thanatos Director"}):
        frappe.throw("Riservato agli operatori.")
    case = frappe.new_doc("Investigation Case")
    case.case_title = (plan.get("case_title") or "Caso AI")[:140]
    case.summary = (plan.get("summary") or "")[:1000]
    if client and frappe.db.exists("Investigation Client", client):
        case.client = client
    case.status = "Draft"
    seq = 0
    for st in (plan.get("steps") or []):
        seq += 1
        actor_client = (st.get("actor") == "cliente")
        case.append("case_steps", {
            "seq": seq,
            "step_label": (st.get("label") or f"Step {seq}")[:140],
            "mode": "GATE",
            "status": "Pending",
            "action_type": (st.get("action") or "")[:140],
            "service_code": st.get("service_code") if st.get("service_code") and
            frappe.db.exists("Service Catalog", st.get("service_code")) else None,
            "client_visible": 1 if actor_client else 0,
        })
    case.insert(ignore_permissions=True)
    # nota AI con piano completo in bacheca attività
    case.append("case_activities", {
        "activity_date": now_datetime(), "activity_type": "Report",
        "description": ("🤖 Architetto AI — piano generato. Documenti: "
                        + ", ".join(plan.get("documents") or []))[:500],
        "operator": frappe.session.user})
    case.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "case": case.name}
