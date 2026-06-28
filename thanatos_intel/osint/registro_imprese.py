"""Connettore Registro Imprese (dati camerali) per la due diligence.

Input P.IVA → validazione (checksum + VIES) e, se è configurato un provider API,
visura sintetica (denominazione, forma, stato, capitale, sede, PEC, ATECO,
amministratori, procedure concorsuali). Crea un reperto sul caso.

Provider API (site_config):
  registro_imprese_provider = "openapi"     # company.openapi.com (Bearer token, pay-per-call)
  registro_imprese_token    = "<token>"
Senza provider: ritorna il link diretto a registroimprese.it (accesso SPID del-
l'operatore); il PDF scaricato si carica sul caso e l'ingest lo struttura.
"""
import frappe
from frappe.utils import now_datetime

from thanatos_intel.integrations.company_screen import validate_piva

_OPENAPI = "https://company.openapi.com"
_OPENAPI_SANDBOX = "https://test.company.openapi.com"


def _digits(piva):
    return "".join(c for c in (piva or "") if c.isdigit())


def manual_link(piva):
    return f"https://www.registroimprese.it/search?q={_digits(piva)}"


def _fetch_openapi(piva, token):
    import requests
    base = _OPENAPI_SANDBOX if frappe.conf.get("openapi_sandbox") else _OPENAPI
    try:
        r = requests.get(f"{base}/IT-advanced/{piva}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=40)
        if r.status_code != 200:
            return None, f"openapi HTTP {r.status_code}: {(r.text or '')[:120]}"
        body = r.json() or {}
        data = body.get("data")
        rec = (data[0] if isinstance(data, list) and data else
               (data if isinstance(data, dict) else body))
        return rec, None
    except Exception as e:
        return None, str(e)[:120]


def _norm_company(rec):
    """Normalizza i campi salienti dalla Company API openapi.it (IT-advanced)."""
    g = lambda *keys: next((rec.get(k) for k in keys if rec.get(k)), None)
    # sede
    sede = ""
    addr = (rec.get("address") or {}).get("registeredOffice") or rec.get("address") or {}
    if isinstance(addr, dict):
        sede = ", ".join(x for x in [addr.get("streetName"), addr.get("town"),
                                     addr.get("province"), addr.get("zipCode")] if x)
    elif isinstance(addr, str):
        sede = addr
    # forma
    dlf = rec.get("detailedLegalForm") or {}
    forma = dlf.get("description") if isinstance(dlf, dict) else (dlf or g("legalForm", "forma_giuridica"))
    # bilancio / capitale
    bs = (rec.get("balanceSheets") or {}).get("last") or {}
    capitale = bs.get("shareCapital") or g("shareCapital", "capitale_sociale", "capitale")
    # ateco
    ateco = ""
    ac = rec.get("atecoClassification") or {}
    if isinstance(ac, dict):
        ateco = (ac.get("ateco") or {}).get("code") or ac.get("code") or ""
    ateco = ateco or g("atecoCode", "ateco")
    # soci (shareHolders)
    soci = rec.get("shareHolders") or rec.get("shareholders") or []
    if isinstance(soci, list):
        soci = [(s.get("companyName") or s.get("name") or
                 ((s.get("lastName", "") + " " + s.get("firstName", "")).strip()) or str(s))
                + (f" ({s.get('percentShare')}%)" if s.get("percentShare") else "")
                for s in soci if s][:12]
    # amministratori (se presenti)
    amm = rec.get("managers") or rec.get("administrators") or rec.get("corporateBodies") or []
    if isinstance(amm, list):
        amm = [a.get("name") or ((a.get("lastName", "") + " " + a.get("firstName", "")).strip())
               or str(a) for a in amm if a][:8]
    return {
        "denominazione": g("companyName", "denominazione", "name"),
        "stato": g("activityStatus", "stato", "status"),
        "forma": forma,
        "capitale": capitale,
        "sede": sede,
        "pec": g("pec", "pecEmail"),
        "ateco": ateco,
        "rea": g("reaCode", "rea"),
        "iscrizione": g("registrationDate", "startDate", "data_iscrizione"),
        "soci": soci,
        "amministratori": amm,
        "bilancio": ({"anno": bs.get("year"), "fatturato": bs.get("turnover"),
                      "dipendenti": bs.get("employees"), "pn": bs.get("netWorth")} if bs else {}),
    }


def _flags(company):
    flags = []
    stato = (company.get("stato") or "").lower()
    for bad in ("liquid", "falliment", "concordat", "cessat", "scioglimento", "inattiv"):
        if bad in stato:
            flags.append(f"Stato societario: {company.get('stato')}")
            break
    return flags


def _evidence(case, out):
    lines = [f"Verifica camerale P.IVA {out['piva']}"]
    chk = out["checks"].get("piva_checksum") or {}
    lines.append(f"Checksum P.IVA: {'valido' if chk.get('valid') else 'NON valido'}")
    vies = out["checks"].get("vies") or {}
    lines.append(f"VIES: {vies.get('valid')}" + (f" — {vies.get('name')}" if vies.get('name') else ""))
    c = out.get("company")
    if c:
        lines.append(f"Denominazione: {c.get('denominazione') or '-'}")
        lines.append(f"Stato: {c.get('stato') or '-'} · Forma: {c.get('forma') or '-'} · "
                     f"Capitale: {c.get('capitale') or '-'}")
        lines.append(f"Sede: {c.get('sede') or '-'} · PEC: {c.get('pec') or '-'} · "
                     f"ATECO: {c.get('ateco') or '-'}")
        if c.get("amministratori"):
            lines.append("Amministratori: " + ", ".join(map(str, c["amministratori"])))
        if c.get("soci"):
            lines.append("Soci: " + ", ".join(map(str, c["soci"])))
        b = c.get("bilancio") or {}
        if b.get("fatturato") is not None:
            lines.append(f"Bilancio {b.get('anno')}: fatturato {b.get('fatturato')}, "
                         f"dipendenti {b.get('dipendenti')}, PN {b.get('pn')}")
    else:
        lines.append(f"Visura da scaricare (SPID): {out.get('manual_link')}")
    if out.get("flags"):
        lines.append("Red flag: " + "; ".join(out["flags"]))
    try:
        ev = frappe.get_doc({
            "doctype": "Investigation Evidence", "investigation_case": case,
            "evidence_name": f"Verifica camerale — {(out.get('company') or {}).get('denominazione') or out['piva']}"[:140],
            "evidence_type": "Document", "source": "Registro Imprese",
            "acquisition_date": now_datetime(),
            "custody_status": "Received", "notes": "\n".join(lines)[:1000]})
        ev.flags.ignore_mandatory = True
        ev.insert(ignore_permissions=True)
        frappe.db.commit()
        return ev.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "registro_imprese evidence")
        return None


@frappe.whitelist()
def verifica_impresa(piva, investigation_case=None):
    digits = _digits(piva)
    out = {"piva": digits, "checks": {}, "flags": [], "source": None}
    if len(digits) != 11:
        out["flags"].append("P.IVA non valida (lunghezza)")
        return out
    out["checks"]["piva_checksum"] = validate_piva(digits)
    if not out["checks"]["piva_checksum"].get("valid"):
        out["flags"].append("P.IVA: checksum NON valido")
    try:
        from thanatos_intel.integrations import vies_lookup
        v = vies_lookup.lookup("IT" + digits)
        out["checks"]["vies"] = {"valid": v.get("valid"), "name": v.get("name")}
    except Exception as e:
        out["checks"]["vies"] = {"error": str(e)[:100]}

    prov = frappe.conf.get("registro_imprese_provider")
    token = frappe.conf.get("registro_imprese_token")
    if prov == "openapi" and token:
        company, err = _fetch_openapi(digits, token)
        if company:
            out["source"] = "openapi"
            out["company"] = _norm_company(company)
            out["flags"].extend(_flags(out["company"]))
        else:
            out["provider_error"] = err
    if not out.get("company"):
        out["manual_link"] = manual_link(digits)

    if investigation_case:
        out["evidence"] = _evidence(investigation_case, out)
    return out


@frappe.whitelist()
def verifica_parti_caso(case):
    """Esegue la verifica camerale su tutte le entità-azienda del caso con P.IVA nota.
    Le P.IVA si ricavano dai reperti/visure se presenti, altrimenti vanno indicate."""
    # mappa nota P.IVA per le aziende del caso (estendibile)
    known = {}
    c = frappe.get_doc("Investigation Case", case)
    done = []
    for ce in (c.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity,
                                 ["full_name", "entity_type", "primary_identifier"], as_dict=True)
        if not et or et.entity_type != "Company":
            continue
        digs = _digits(et.primary_identifier)
        piva = digs if len(digs) == 11 else known.get((et.full_name or "").upper())
        if not piva:
            continue
        r = verifica_impresa(piva, investigation_case=case)
        done.append({"name": et.full_name, "piva": piva, "flags": r.get("flags")})
    return {"ok": True, "verificate": done}
