# -*- coding: utf-8 -*-
"""Retention engine — applica le Retention Rule (GDPR storage limitation).

SICUREZZA (hard-coded, non aggirabile dalle regole):
- DRY-RUN di default: non cancella nulla finché site_config `retention_dry_run`
  resta a 1 (default). Va a 0 solo per esecuzione reale.
- Legal hold: mai toccare record legati a un Investigation Case NON chiuso
  (status ∉ {Closed, Cancelled}); i fascicoli si trattano solo se chiusi.
- Esegue SOLO regole `active` con `target_doctype` valorizzato (le regole
  solo-policy senza target restano documentazione, non agiscono).
- Cap per regola + audit di ogni run (Error Log "Retention run" + logger).
"""
import json
import re
import frappe
from frappe.utils import now_datetime, add_to_date

CLOSED = {"Closed", "Cancelled"}
_UNITS = {
    "day": 1, "days": 1, "giorno": 1, "giorni": 1, "gg": 1,
    "week": 7, "weeks": 7, "settimana": 7, "settimane": 7,
    "month": 30.44, "months": 30.44, "mese": 30.44, "mesi": 30.44,
    "year": 365.25, "years": 365.25, "anno": 365.25, "anni": 365.25,
}


def _parse_period(text):
    """«12 mesi», «10 anni», «90 giorni», «2 years» -> giorni (int) o None."""
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([A-Za-zàèéìòù]+)", str(text).strip())
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    unit = _UNITS.get(m.group(2).lower())
    if not unit:
        return None
    return int(round(n * unit))


def _is_dry_run():
    return bool(int(frappe.conf.get("retention_dry_run", 1)))


def _case_link_field(doctype):
    """Nome del campo Link -> Investigation Case sul doctype, se esiste."""
    try:
        for f in frappe.get_meta(doctype).fields:
            if f.fieldtype == "Link" and f.options == "Investigation Case":
                return f.fieldname
    except Exception:
        pass
    return None


def _case_on_hold(case_name):
    """True se il caso non è chiuso -> legal hold, non toccare i suoi dati."""
    if not case_name:
        return False
    st = frappe.db.get_value("Investigation Case", case_name, "status")
    return (st or "") not in CLOSED


def _candidates(rule, limit):
    dt = rule.get("target_doctype")
    date_field = rule.get("date_field") or "creation"
    days = _parse_period(rule.get("retention_period"))
    if not days:
        return None, "retention_period non interpretabile"
    if not frappe.db.exists("DocType", dt):
        return None, f"DocType «{dt}» inesistente"
    if not frappe.get_meta(dt).has_field(date_field) and date_field not in ("creation", "modified"):
        return None, f"campo data «{date_field}» assente su {dt}"
    cutoff = add_to_date(now_datetime(), days=-days)
    filters = {}
    if rule.get("filter_json"):
        try:
            filters = json.loads(rule["filter_json"])
        except Exception:
            return None, "filter_json non è JSON valido"
    filters[date_field] = ["<=", cutoff]
    # SICUREZZA: un fascicolo si tratta solo se chiuso
    if dt == "Investigation Case":
        filters["status"] = ["in", list(CLOSED)]
    names = frappe.get_all(dt, filters=filters, pluck="name", limit=limit)
    # SICUREZZA: legal hold via link al caso (record legati a casi aperti = intoccabili)
    lf = _case_link_field(dt) if dt != "Investigation Case" else None
    if lf:
        names = [n for n in names
                 if not _case_on_hold(frappe.db.get_value(dt, n, lf))]
    return names, None


def _anonymize(dt, name, fields_text):
    fields = [f.strip() for f in re.split(r"[,\n;]", fields_text or "") if f.strip()]
    meta = frappe.get_meta(dt)
    vals = {f: "[anonimizzato]" for f in fields if meta.has_field(f)}
    if vals:
        frappe.db.set_value(dt, name, vals)


def _erase_attachments(dt, name):
    """Erasa i blob File allegati (es. la scansione del documento KYC = dato
    personale). Usato per l'erasura GDPR quando il record NON si può cancellare
    (catena di custodia)."""
    n = 0
    for _fn in frappe.get_all("File", filters={"attached_to_doctype": dt,
                              "attached_to_name": name}, pluck="name"):
        try:
            frappe.delete_doc("File", _fn, ignore_permissions=True, force=True)
            n += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "retention file erase")
    return n


def _archive_status(dt, name):
    """Marca il record come archiviato se ha un campo status/custody idoneo."""
    m = frappe.get_meta(dt)
    if m.has_field("custody_status"):
        frappe.db.set_value(dt, name, "custody_status", "Archived")
        return True
    if m.has_field("status"):
        opts = (next((f.options for f in m.fields if f.fieldname == "status"), "") or "").split("\n")
        arch = next((o for o in opts if o.strip() in ("Archiviato", "Archived", "Closed")), None)
        if arch:
            frappe.db.set_value(dt, name, "status", arch.strip())
            return True
    return False


def _apply(rule, name):
    dt = rule["target_doctype"]
    action = rule.get("action")
    erase_att = int(rule.get("erase_attachments") or 0)
    if action == "Cancella":
        # erasura completa: allegati + record. NB: alcuni doctype vietano il
        # delete (es. Investigation Evidence, catena di custodia Legea 135/2010)
        # -> in quel caso delete_doc solleva e il record va gestito con Anonimizza.
        _erase_attachments(dt, name)
        frappe.delete_doc(dt, name, ignore_permissions=True)
    elif action == "Anonimizza":
        # dato personale erasato ma record conservato (compatibile con la catena
        # di custodia): blanka i campi PII + erasa gli allegati (se richiesto) +
        # marca archiviato.
        _anonymize(dt, name, rule.get("anonymize_fields"))
        if erase_att:
            _erase_attachments(dt, name)
        _archive_status(dt, name)
    elif action == "Archivia":
        if erase_att:
            _erase_attachments(dt, name)
        _archive_status(dt, name)


def _audit(report, dry):
    summ = "; ".join(
        f"{x.get('rule')}={x.get('acted', x.get('skipped') or x.get('error') or 0)}"
        for x in report)
    try:
        frappe.logger("retention").info(f"dry={dry} :: {summ}")
    except Exception:
        pass
    try:
        frappe.log_error(json.dumps(report, default=str)[:4000],
                         f"Retention run ({'DRY-RUN' if dry else 'LIVE'})")
    except Exception:
        pass


@frappe.whitelist()
def run_retention(dry_run=None, limit_per_rule=2000, rule=None):
    """Applica le Retention Rule attive. dry_run None -> usa site_config
    (default 1 = simulazione). Ritorna il report per regola."""
    frappe.only_for(("System Manager", "Investigation Manager"))
    dry = _is_dry_run() if dry_run is None else bool(int(dry_run))
    filt = {"name": rule} if rule else {"active": 1}
    rules = frappe.get_all(
        "Retention Rule", filters=filt,
        fields=["name", "record_type", "target_doctype", "date_field",
                "retention_period", "action", "filter_json", "anonymize_fields"])
    report = []
    for r in rules:
        if not r.get("target_doctype"):
            report.append({"rule": r["name"], "skipped": "solo-policy (nessun target_doctype)"})
            continue
        names, err = _candidates(r, int(limit_per_rule))
        if err:
            report.append({"rule": r["name"], "error": err})
            continue
        acted = 0
        if not dry:
            for n in names:
                try:
                    _apply(r, n)
                    acted += 1
                except Exception:
                    frappe.log_error(frappe.get_traceback(), f"retention {r['name']} {n}")
            frappe.db.set_value("Retention Rule", r["name"],
                                {"last_run": now_datetime(), "last_count": acted})
            frappe.db.commit()
        report.append({
            "rule": r["name"], "doctype": r["target_doctype"], "action": r.get("action"),
            "candidates": len(names), "acted": acted if not dry else 0,
            "would_purge": len(names) if dry else None, "dry_run": dry})
    _audit(report, dry)
    return {"dry_run": dry, "rules": report}


def scheduled_retention():
    """Entry point giornaliero (scheduler). Rispetta il dry-run di site_config."""
    dry = _is_dry_run()
    filt = {"active": 1}
    rules = frappe.get_all(
        "Retention Rule", filters=filt,
        fields=["name", "record_type", "target_doctype", "date_field",
                "retention_period", "action", "filter_json", "anonymize_fields"])
    report = []
    for r in rules:
        if not r.get("target_doctype"):
            report.append({"rule": r["name"], "skipped": "solo-policy"})
            continue
        names, err = _candidates(r, 2000)
        if err:
            report.append({"rule": r["name"], "error": err})
            continue
        acted = 0
        if not dry:
            for n in names:
                try:
                    _apply(r, n)
                    acted += 1
                except Exception:
                    frappe.log_error(frappe.get_traceback(), f"retention {r['name']} {n}")
            frappe.db.set_value("Retention Rule", r["name"],
                                {"last_run": now_datetime(), "last_count": acted})
            frappe.db.commit()
        report.append({"rule": r["name"], "candidates": len(names),
                       "acted": acted, "dry_run": dry})
    _audit(report, dry)
    return report
