"""Sanctions/PEP/Adverse Media screening via OpenSanctions public API.
Endpoint: https://api.opensanctions.org/match/sanctions  (no key per ricerche piccole).
Fallback: scrive Sanctions Screening con outcome Review se l'API non risponde."""
import json
import frappe
import requests
from frappe.utils import now_datetime

OS_BASE = "https://api.opensanctions.org"


def _post(path, payload, timeout=20):
    try:
        r = requests.post(f"{OS_BASE}{path}", json=payload, timeout=timeout,
                          headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        frappe.log_error(f"OpenSanctions error: {e}", "DddScreening")
        return None


@frappe.whitelist()
def screen_applicant(ddd_case: str):
    """Esegue screening completo (sanctions+PEP+watchlist) sull'applicant del case."""
    case = frappe.get_doc("Diplomatic Eligibility Case", ddd_case)
    if not case.applicant:
        frappe.throw("Case senza applicant")
    app = frappe.get_doc("Applicant Profile", case.applicant)

    query = {
        "queries": {
            "q1": {
                "schema": "Person",
                "properties": {
                    "name": [app.full_legal_name],
                    "birthDate": [str(app.dob)] if app.dob else [],
                    "nationality": [app.nationality or ""],
                }
            }
        }
    }
    out = []
    # 0. Local OpenSanctions cache (offline, instant)
    try:
        from thanatos_intel.thanatos_ddd.opensanctions_sync import lookup as _local
        local = _local(app.full_legal_name, str(app.dob or ""), app.nationality or "")
        if local["matches"]:
            scr = frappe.get_doc({
                "doctype": "Sanctions Screening",
                "ddd_case": ddd_case,
                "subject_name": app.full_legal_name,
                "screening_type": "Sanctions",
                "source": "OpenSanctions (local cache)",
                "matches_found": len(local["matches"]),
                "outcome": "Hit",
                "raw_payload": json.dumps(local["matches"][:5], indent=2, default=str)[:8000],
                "screened_on": now_datetime(),
            })
            scr.insert(ignore_permissions=True)
            out.append({"type": "Sanctions (local)", "matches": len(local["matches"]),
                        "outcome": scr.outcome, "name": scr.name})
    except Exception as e:
        frappe.log_error(str(e), "DddLocalScreening")
    for stype in ("sanctions", "peps"):
        res = _post(f"/match/{'default' if stype=='sanctions' else 'peps'}", query)
        results = ((res or {}).get("responses", {}).get("q1", {}).get("results")) or []
        scr = frappe.get_doc({
            "doctype": "Sanctions Screening",
            "ddd_case": ddd_case,
            "subject_name": app.full_legal_name,
            "screening_type": "PEP" if stype == "peps" else "Sanctions",
            "source": "OpenSanctions",
            "matches_found": len(results),
            "outcome": "Hit" if results else "Clear" if res else "Review",
            "raw_payload": json.dumps(results[:5], indent=2, default=str)[:8000],
            "screened_on": now_datetime(),
        })
        scr.insert(ignore_permissions=True)
        out.append({"type": scr.screening_type, "matches": len(results),
                    "outcome": scr.outcome, "name": scr.name})
    frappe.db.commit()
    return {"applicant": app.full_legal_name, "results": out}
