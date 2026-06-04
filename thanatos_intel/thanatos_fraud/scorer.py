"""Risk Rule evaluator + entity score rollup.

Riceve un Entity name + dati arricchiti (dict osint aggregato) e:
1. Match watchlist/blacklist
2. Esegue Risk Rule abilitate (eval del selector_expression con namespace ristretto)
3. Aggiorna Entity.risk_score
4. Crea Fraud Alert per match Critical/High
"""
import json

import frappe
from frappe.utils import now_datetime

SAFE_BUILTINS = {"len": len, "any": any, "all": all, "min": min, "max": max,
                 "sum": sum, "int": int, "float": float, "str": str,
                 "abs": abs, "bool": bool, "isinstance": isinstance}


@frappe.whitelist()
def evaluate_entity(entity: str, enriched_json: str = None) -> dict:
    """Esegue tutte le Risk Rule attive contro l'entity e ritorna lo score."""
    ent = frappe.get_doc("Entity", entity)
    data = {}
    if enriched_json:
        try:
            data = json.loads(enriched_json) if isinstance(enriched_json, str) else enriched_json
        except Exception:
            data = {}
    e = {
        "type": ent.entity_type, "value": ent.primary_value,
        "label": ent.label, "country": ent.country,
        "tags": (ent.tags or "").split(","),
        "blacklisted": int(ent.blacklisted or 0),
        "monitored": int(ent.monitored or 0),
        **data,
    }

    score = 0
    matches = []
    rules = frappe.get_all("Risk Rule",
        filters={"enabled": 1, "applies_to": ["in", [ent.entity_type, "Entity"]]},
        fields=["name", "rule_name", "score_delta", "severity",
                "selector_expression", "match_message", "category"])

    for r in rules:
        expr = (r.get("selector_expression") or "").strip()
        if not expr:
            continue
        try:
            ok = bool(eval(expr, {"__builtins__": SAFE_BUILTINS}, {"e": e}))
        except Exception as exc:
            frappe.log_error(f"Rule {r['name']} error: {exc}", "Risk Rule eval")
            ok = False
        if ok:
            score += int(r["score_delta"] or 0)
            matches.append({"rule": r["name"], "name": r["rule_name"],
                            "delta": r["score_delta"], "severity": r["severity"],
                            "message": r.get("match_message") or ""})

    # Watchlist hit
    wl_hits = frappe.get_all("Watchlist Entry",
        filters={"value": ent.primary_value, "value_type": ent.entity_type},
        fields=["name", "list_type", "severity", "reason"])
    for w in wl_hits:
        bump = {"Critical": 40, "High": 25, "Medium": 12, "Low": 5}.get(w["severity"], 8)
        score += bump
        matches.append({"watchlist": w["name"], "list": w["list_type"],
                        "severity": w["severity"], "delta": bump,
                        "message": w.get("reason") or ""})

    score = max(0, min(100, score))
    ent.risk_score = score
    ent.last_seen = now_datetime()
    ent.save(ignore_permissions=True)

    # Create alerts for critical matches
    for m in matches:
        if m.get("severity") in ("Critical", "High"):
            try:
                frappe.get_doc({
                    "doctype": "Fraud Alert",
                    "title": f"{m.get('name') or m.get('list', 'Watchlist')} → {ent.label}",
                    "severity": m["severity"],
                    "status": "Open",
                    "created_at": now_datetime(),
                    "entity": ent.name,
                    "rule": m.get("rule"),
                    "details": m.get("message"),
                    "evidence_json": json.dumps(m, default=str),
                }).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Fraud Alert create")

    frappe.db.commit()
    return {"entity": ent.name, "risk_score": score,
            "risk_band": ent.risk_band, "matches": matches}
