"""KYB via UK Companies House REST API.

Bottone "Verifica KYB" su Investigation Entity (entity_type=Company).
Key in site_config: companies_house_api_key. Arricchisce l'entita, crea
director (Person) e societa collegate (Company), allega report ai case.
"""
import base64
import json

import frappe
import requests
from frappe.utils import now_datetime

BASE = "https://api.company-information.service.gov.uk"


def _auth():
    key = frappe.conf.get("companies_house_api_key")
    if not key:
        frappe.throw("companies_house_api_key non configurata in site_config.")
    return {"Authorization": "Basic " + base64.b64encode((key + ":").encode()).decode(),
            "User-Agent": "thanatos-intel"}


def _api(path):
    r = requests.get(BASE + path, headers=_auth(), timeout=25)
    r.raise_for_status()
    return r.json()


def _company_number(entity):
    """Ricava il company number dall'entita: campo dedicato, o '<...> (UK NNN)' in
    primary_identifier/full_name, altrimenti ricerca per nome."""
    import re
    for src in (entity.primary_identifier or "", entity.full_name or "", entity.notes or ""):
        m = re.search(r"\bUK\s*([A-Z0-9]{6,8})\b", src) or re.search(r"\b(\d{8})\b", src)
        if m:
            return m.group(1)
    # ricerca per nome
    q = requests.utils.quote(entity.primary_identifier or entity.full_name or "")
    res = _api(f"/search/companies?q={q}&items_per_page=1")
    items = res.get("items", [])
    return items[0].get("company_number") if items else None


@frappe.whitelist()
def kyb_lookup(entity_name: str) -> dict:
    """Esegue il KYB completo su una entita Company e arricchisce il grafo."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    entity = frappe.get_doc("Investigation Entity", entity_name)
    cn = _company_number(entity)
    if not cn:
        frappe.throw("Company number non trovato per " + entity_name)

    company = _api(f"/company/{cn}")
    officers = _api(f"/company/{cn}/officers").get("items", [])
    try:
        psc = _api(f"/company/{cn}/persons-with-significant-control").get("items", [])
    except Exception:
        psc = []

    name = company.get("company_name")
    status = company.get("company_status")
    acc = company.get("accounts") or {}
    office = company.get("registered_office_address") or {}
    office_str = ", ".join(filter(None, [office.get("address_line_1"), office.get("locality"),
                                         office.get("postal_code"), office.get("country")]))

    entity.full_name = f"{name} (UK {cn})"
    entity.last_osint_run = now_datetime()
    summary = (f"KYB Companies House: {name} ({cn}), status {status}, costituita "
               f"{company.get('date_of_creation')}, sede {office_str}. "
               f"Bilanci {'OVERDUE' if acc.get('overdue') else 'ok'} (next {acc.get('next_due')}). "
               f"{len(officers)} officer, {len(psc)} PSC.")
    if "KYB Companies House" not in (entity.notes or ""):
        entity.notes = (entity.notes or "") + " | " + summary
    if acc.get("overdue") and not any(ri.indicator_type == "Accounts overdue" for ri in entity.risk_indicators):
        entity.append("risk_indicators", dict(indicator_type="Accounts overdue",
                      value="bilanci non depositati", source="UK Companies House", points=25, verified=1))
    entity.osint_raw = json.dumps({"company": company, "officers": officers, "psc": psc}, default=str)[:140000]
    entity.save(ignore_permissions=True)

    psc_names = {p.get("name", "").lower() for p in psc}
    created_persons, linked_companies = [], []

    for off in officers:
        oname = off.get("name")
        if not oname:
            continue
        if not frappe.db.exists("Investigation Entity", oname):
            dob = off.get("date_of_birth") or {}
            note = (f"Director di {name} ({cn}), nominato {off.get('appointed_on')}"
                    f"{', dimesso ' + off['resigned_on'] if off.get('resigned_on') else ''}. "
                    f"Nato {dob.get('month','?')}/{dob.get('year','?')}, {off.get('nationality')}, "
                    f"res. {off.get('country_of_residence')}.")
            is_psc = oname.lower() in psc_names
            p = frappe.get_doc({"doctype": "Investigation Entity", "entity_type": "Person",
                                "primary_identifier": oname, "full_name": oname, "notes": note})
            p.append("risk_indicators", dict(
                indicator_type="Beneficial owner" if is_psc else "Company officer",
                value=("PSC " if is_psc else "") + "director " + name,
                source="UK Companies House", points=45 if is_psc else 20, verified=1))
            p.insert(ignore_permissions=True)
            created_persons.append(oname)
        # altre cariche dell'officer -> societa collegate
        link = (off.get("links", {}) or {}).get("officer", {}).get("appointments")
        if link:
            try:
                apps = _api(link).get("items", [])
            except Exception:
                apps = []
            for a in apps:
                at = a.get("appointed_to", {}) or {}
                conum, coname = at.get("company_number"), at.get("company_name")
                if not conum or conum == cn:
                    continue
                ident = f"{coname} (UK {conum})"
                if not frappe.db.exists("Investigation Entity", ident):
                    frappe.get_doc({"doctype": "Investigation Entity", "entity_type": "Company",
                        "primary_identifier": ident, "full_name": ident,
                        "notes": f"Collegata via director comune ({oname}). Status {at.get('company_status')}."
                        }).insert(ignore_permissions=True)
                    linked_companies.append(ident)

    # allega ai case che contengono questa entita
    cases = frappe.get_all("Case Entity", filters={"entity": entity_name,
                           "parenttype": "Investigation Case"}, pluck="parent")
    for case_name in set(cases):
        case = frappe.get_doc("Investigation Case", case_name)
        case.append("case_activities", dict(activity_date=now_datetime(), activity_type="OSINT",
            description=f"KYB {name} ({cn}): {len(officers)} officer, {len(psc)} PSC, "
                        f"{len(created_persons)} persone e {len(linked_companies)} societa collegate create. "
                        f"Bilanci {'overdue' if acc.get('overdue') else 'ok'}.",
            operator=frappe.session.user))
        case.save(ignore_permissions=True)

    frappe.db.commit()
    return {"company": name, "number": cn, "status": status,
            "accounts_overdue": bool(acc.get("overdue")),
            "officers": len(officers), "psc": len(psc),
            "persons_created": len(created_persons), "linked_companies": len(linked_companies)}


def search_by_name(query: str) -> dict:
    """Ricerca aziende UK per nome libero — connettore free_auto per public_scan/free_sources.

    Non richiede Investigation Entity: prende una stringa (nome/parole chiave) e ritorna
    fino a 5 match con company_number, status, tipo, indirizzo, data. Nessuna scrittura
    su DB. Ritorna {"found": bool, "total": int, "matches": [...]}.
    """
    if not query or len(query.strip()) < 3:
        return {"found": False, "total": 0, "matches": [], "error": "query troppo corta"}
    if not frappe.conf.get("companies_house_api_key"):
        return {"found": False, "total": 0, "matches": [], "stub": True,
                "error": "companies_house_api_key non configurata"}
    try:
        q = requests.utils.quote(query.strip())
        res = _api(f"/search/companies?q={q}&items_per_page=5")
    except Exception as e:
        return {"found": False, "total": 0, "matches": [], "error": str(e)[:200]}

    items = res.get("items", [])
    matches = []
    for it in items:
        addr = it.get("address") or {}
        addr_str = ", ".join(filter(None, [
            addr.get("address_line_1"), addr.get("locality"),
            addr.get("postal_code"), addr.get("country"),
        ]))
        matches.append({
            "name": it.get("title") or it.get("company_name"),
            "company_number": it.get("company_number"),
            "status": it.get("company_status"),
            "type": it.get("company_type"),
            "created": it.get("date_of_creation"),
            "address": addr_str,
            "topics": ["registered_uk"] + (["dissolved"] if it.get("company_status") == "dissolved" else []),
        })
    return {"found": bool(matches), "total": res.get("total_results", len(matches)), "matches": matches}
