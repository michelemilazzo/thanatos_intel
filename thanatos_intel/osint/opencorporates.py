"""Connettore OpenCorporates — anagrafica societaria cross-border (free+key).

Copre le società NON italiane (Malta, Cipro, UK, EU, offshore) che openapi IT
non vede. Tier gratuito: registrazione su opencorporates.com (no carta) → token in
site_config `opencorporates_api_key`. Senza token ritorna uno stub con istruzioni.

API: https://api.opencorporates.com/v0.4/companies/search
"""
import frappe
from frappe.utils import now_datetime

BASE = "https://api.opencorporates.com/v0.4"
# mappa euristica indicatore → jurisdiction_code OpenCorporates
_JUR = {"MALTA": "mt", "C9": "mt", "CYPRUS": "cy", "CIPRO": "cy", "UK": "gb",
        "GB": "gb", "IRELAND": "ie", "IRLAND": "ie", "LUX": "lu", "ESTONIA": "ee",
        "SPAIN": "es", "SPAGNA": "es", "FRANCE": "fr", "FRANCIA": "fr",
        "GERMAN": "de", "SVIZZER": "ch", "SWISS": "ch", "DELAWARE": "us_de", "USA": "us"}


def _token():
    return frappe.conf.get("opencorporates_api_key")


def _guess_jurisdiction(hint):
    h = (hint or "").upper()
    for k, v in _JUR.items():
        if k in h:
            return v
    return None


@frappe.whitelist()
def lookup(name, jurisdiction=None, investigation_case=None):
    """Cerca una società per denominazione (opz. jurisdiction) → match + dati base."""
    tok = _token()
    if not tok:
        return {"stub": True, "name": name,
                "message": "opencorporates_api_key mancante. Registrati gratis su "
                           "opencorporates.com/api_accounts/new e inserisci il token in site_config."}
    import requests
    jur = jurisdiction or _guess_jurisdiction(name)
    params = {"q": name, "api_token": tok, "per_page": 5}
    if jur:
        params["jurisdiction_code"] = jur
    try:
        r = requests.get(f"{BASE}/companies/search", params=params, timeout=30)
        if r.status_code != 200:
            return {"error": f"opencorporates HTTP {r.status_code}", "name": name}
        comps = (((r.json() or {}).get("results") or {}).get("companies")) or []
    except Exception as e:
        return {"error": str(e)[:160], "name": name}
    out = []
    for c in comps:
        co = c.get("company") or {}
        out.append({"nome": co.get("name"), "numero": co.get("company_number"),
                    "giurisdizione": co.get("jurisdiction_code"), "stato": co.get("current_status"),
                    "tipo": co.get("company_type"), "url": co.get("opencorporates_url"),
                    "creata": co.get("incorporation_date"), "inattiva": co.get("inactive")})
    res = {"name": name, "jurisdiction": jur, "match": len(out), "risultati": out}
    if investigation_case and out:
        lines = [f"OpenCorporates — «{name}»" + (f" [{jur}]" if jur else ""), f"Match: {len(out)}"]
        lines += [f"• {x['nome']} ({x['giurisdizione']} {x['numero']}) — {x['stato'] or '-'}" for x in out]
        try:
            ev = frappe.get_doc({
                "doctype": "Investigation Evidence", "investigation_case": investigation_case,
                "evidence_name": f"OpenCorporates — {name}"[:140], "evidence_type": "Document",
                "source": "OpenCorporates", "acquisition_date": now_datetime(),
                "custody_status": "Received", "notes": "\n".join(lines)[:1000]})
            ev.flags.ignore_mandatory = True
            ev.insert(ignore_permissions=True)
            frappe.db.commit()
            res["evidence"] = ev.name
        except Exception:
            frappe.log_error(frappe.get_traceback(), "opencorporates evidence")
    return res
