"""Verifica societaria/persone multi-strumento (pipeline ISO).

Per ogni parte di un caso:
  - aziende: checksum P.IVA italiana + VIES (intra-UE) + screening sanzioni/PEP
  - persone: screening sanzioni/PEP (OpenSanctions locale, ~290k entità)
Sintetizza un livello di rischio e registra gli esiti come Risk Indicator
sull'entità + nota sul caso. Gap noti (non automatizzabili gratis): visura
camerale live / Registro Imprese, cassetto fiscale AdE (richiede delega cliente).
"""
import frappe
from frappe.utils import now_datetime


def validate_piva(piva):
    """Checksum partita IVA italiana (11 cifre, algoritmo Luhn-variant ufficiale)."""
    p = "".join(c for c in (piva or "") if c.isdigit())
    if len(p) != 11:
        return {"valid": False, "reason": f"lunghezza {len(p)} != 11", "piva": p}
    s = 0
    for i in range(10):
        d = int(p[i])
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    chk = (10 - (s % 10)) % 10
    return {"valid": chk == int(p[10]), "piva": p, "expected": chk, "got": int(p[10])}


@frappe.whitelist()
def screen_company(name, piva=None, country="IT"):
    out = {"name": name, "piva": piva, "checks": {}, "flags": []}
    digits = "".join(c for c in (piva or "") if c.isdigit())
    if digits:
        chk = validate_piva(digits)
        out["checks"]["piva_checksum"] = chk
        if not chk.get("valid"):
            out["flags"].append("P.IVA: checksum NON valido")
        try:
            from thanatos_intel.integrations import vies_lookup
            v = vies_lookup.lookup((country or "IT") + digits)
            out["checks"]["vies"] = {"valid": v.get("valid"), "name": v.get("name")}
            if v.get("valid") is False:
                out["flags"].append("P.IVA non registrata VIES (intra-UE)")
        except Exception as e:
            out["checks"]["vies"] = {"error": str(e)[:120]}
    try:
        from thanatos_intel.osint import free_sources
        sc = free_sources.screen_sanctions(name, schema="Company")
        out["checks"]["sanctions"] = {"found": sc.get("found"), "total": sc.get("total"),
                                      "source": sc.get("source")}
        if sc.get("found"):
            out["flags"].append("MATCH liste sanzioni/PEP")
    except Exception as e:
        out["checks"]["sanctions"] = {"error": str(e)[:120]}
    crit = any(("checksum" in f or "sanzioni" in f) for f in out["flags"])
    out["risk_level"] = "Alto" if crit else ("Medio" if out["flags"] else "Basso")
    return out


@frappe.whitelist()
def screen_person(name):
    out = {"name": name, "checks": {}, "flags": []}
    try:
        from thanatos_intel.osint import free_sources
        sc = free_sources.screen_sanctions(name, schema="Person")
        out["checks"]["sanctions"] = {"found": sc.get("found"), "total": sc.get("total"),
                                      "source": sc.get("source")}
        if sc.get("found"):
            out["flags"].append("MATCH liste sanzioni/PEP")
    except Exception as e:
        out["checks"]["sanctions"] = {"error": str(e)[:120]}
    out["risk_level"] = "Alto" if out["flags"] else "Basso"
    return out


_RISK_MAP = {"Basso": "Basso", "Medio": "Medio", "Alto": "Alto"}


def _set_entity_risk(entity, res):
    lvl = _RISK_MAP.get(res.get("risk_level"), "Basso")
    note = "; ".join(res.get("flags") or []) or "Nessun flag"
    upd = {"risk_level": lvl, "status": "Watchlist" if lvl == "Alto" else None}
    upd = {k: v for k, v in upd.items() if v is not None}
    frappe.db.set_value("Investigation Entity", entity, upd)
    # Risk Indicator (child su Investigation Entity)
    try:
        ent = frappe.get_doc("Investigation Entity", entity)
        fns = {f.fieldname for f in frappe.get_meta("Risk Indicator").fields}
        row = {}
        if "value" in fns:
            row["value"] = ("Screening: " + note)[:140]
        if "source" in fns:
            row["source"] = "Auto screening (VIES/checksum/sanzioni)"
        if "points" in fns:
            row["points"] = {"Alto": 80, "Medio": 40, "Basso": 0}.get(lvl, 0)
        if "indicator_type" in fns:
            row["indicator_type"] = "Compliance"
        if row and "risk_indicators" in {df.fieldname for df in ent.meta.get_table_fields()}:
            ent.append("risk_indicators", row)
            ent.flags.ignore_mandatory = True
            ent.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "screen set_entity_risk")
    frappe.db.commit()


@frappe.whitelist()
def screen_case_parties(case):
    """Esegue lo screening su tutte le parti (entità) del caso e registra gli esiti.
    Ritorna il riepilogo + nota in case_activities."""
    c = frappe.get_doc("Investigation Case", case)
    summary = []
    for ce in (c.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity,
                                 ["full_name", "entity_type", "primary_identifier"], as_dict=True)
        if not et:
            continue
        piva = None
        pid = et.primary_identifier or ""
        # se l'identificatore contiene cifre da P.IVA
        digs = "".join(x for x in pid if x.isdigit())
        if len(digs) == 11:
            piva = digs
        if et.entity_type == "Company":
            res = screen_company(et.full_name, piva=piva)
        else:
            res = screen_person(et.full_name)
        _set_entity_risk(ce.entity, res)
        summary.append({"name": et.full_name, "type": et.entity_type,
                        "risk": res.get("risk_level"), "flags": res.get("flags")})
    # nota sul caso (concisa: conteggi + solo le parti con flag)
    try:
        hi = [s for s in summary if s["risk"] in ("Alto", "Medio")]
        n_alto = sum(1 for s in summary if s["risk"] == "Alto")
        n_medio = sum(1 for s in summary if s["risk"] == "Medio")
        lines = ["🔎 Screening automatico parti (VIES + checksum P.IVA + sanzioni/PEP locale)",
                 f"Parti: {len(summary)} · Alto {n_alto} · Medio {n_medio} · "
                 f"Basso {len(summary) - n_alto - n_medio}"]
        if hi:
            lines.append("Da attenzionare:")
            for s in hi[:20]:
                lines.append(f"• [{s['risk']}] {s['name']} ({s['type']}): {'; '.join(s['flags'])}")
        c.append("case_activities", {"activity_date": now_datetime(),
                                     "activity_type": "Report",
                                     "description": "\n".join(lines)[:1000],
                                     "operator": frappe.session.user})
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "screen case activity")
    return {"ok": True, "parties": summary}
