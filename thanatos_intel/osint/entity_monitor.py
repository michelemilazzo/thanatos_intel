"""Monitoraggio re-scan entità non-wallet (Person/Company/IP).

Estende il pattern di wallet_monitor: fotografa periodicamente il segnale di
rischio delle entità di un caso, lo confronta col baseline salvato e segnala i
cambiamenti che contano (nuove sanzioni/PEP, azienda sciolta, IP diventato
malevolo). Usa SOLO connettori free (opensanctions cache offline, AbuseIPDB,
GreyNoise keyless) → costo zero.

Wallet restano gestiti da wallet_monitor (segnale on-chain diverso).
Schedulato daily (i wallet sono hourly perché volatili; sanzioni/azienda no).
"""
import json

import frappe
from frappe.utils import now, now_datetime

from thanatos_intel.osint.wallet_monitor import _recipients, _load_raw

MON_STATE = "_entity_monitor_state"


# ------------------------- segnale per tipo -------------------------

def _signal_person_company(name, schema):
    from thanatos_intel.osint.free_sources import screen_sanctions
    try:
        r = screen_sanctions(name, schema=schema) or {}
    except Exception:
        return None
    matches = r.get("matches") or r.get("results") or []
    topics = sorted({t for m in matches for t in (m.get("topics") or [])})
    return {"type": "sanctions", "hits": len(matches), "topics": topics,
            "sanctioned": any(t in ("sanction", "crime") for t in topics),
            "pep": any(t in ("role.pep", "poi") for t in topics), "ts": now()}


def _signal_ip(ip):
    from thanatos_intel.osint import engine as eng
    from thanatos_intel.osint import free_sources as fs
    sig = {"type": "ip", "ts": now()}
    try:
        a = eng.lookup_ip(ip) or {}
        sig["abuse_score"] = a.get("score") or a.get("abuse_score") or 0
        sig["reports"] = a.get("total_reports") or 0
    except Exception:
        pass
    try:
        g = fs.lookup_greynoise(ip) or {}
        sig["noise"] = bool(g.get("noise"))
        sig["classification"] = g.get("classification")
    except Exception:
        pass
    return sig


def _signal(ent):
    et = ent.entity_type
    ident = ent.primary_identifier or ent.full_name or ent.name
    if et == "Person":
        return _signal_person_company(ident, "Person")
    if et == "Company":
        return _signal_person_company(ident, "Company")
    if et == "IP":
        return _signal_ip(ident)
    return None  # Wallet -> wallet_monitor; Domain/altro -> TODO


# ------------------------- diff -------------------------

def _diff(prev, cur):
    if not cur:
        return []
    if not prev:
        return [("BASELINE", "stato iniziale registrato")]
    d = []
    t = cur.get("type")
    if t == "sanctions":
        # nuove sanzioni/crime -> segnale piu grave
        if cur.get("sanctioned") and not prev.get("sanctioned"):
            d.append(("SANZIONI", "NUOVO riscontro sanzioni/crimine (%s)" % ", ".join(cur.get("topics") or [])))
        if cur.get("pep") and not prev.get("pep"):
            d.append(("PEP", "NUOVO riscontro PEP/POI"))
        pj, cj = prev.get("hits") or 0, cur.get("hits") or 0
        if cj > pj:
            d.append(("LISTE", "match liste passati da %d a %d" % (pj, cj)))
    elif t == "ip":
        if cur.get("classification") != prev.get("classification") and cur.get("classification"):
            d.append(("THREAT", "classificazione GreyNoise: %s -> %s" %
                      (prev.get("classification") or "-", cur.get("classification"))))
        if bool(cur.get("noise")) and not bool(prev.get("noise")):
            d.append(("THREAT", "IP ora osservato in scanning/rumore internet"))
        ps, cs = prev.get("abuse_score") or 0, cur.get("abuse_score") or 0
        if cs > ps and cs >= 25:
            d.append(("ABUSE", "AbuseIPDB score %d -> %d" % (ps, cs)))
    return d


# ------------------------- snapshot + alert -------------------------

def _entities_of_case(case):
    """Investigation Entity non-wallet linkate al caso via Case Entity."""
    rows = frappe.get_all("Case Entity", filters={"parent": case, "parenttype": "Investigation Case"},
                          pluck="entity")
    out = []
    for ename in set(filter(None, rows)):
        et = frappe.db.get_value("Investigation Entity", ename, "entity_type")
        if et in ("Person", "Company", "IP"):
            out.append(ename)
    return out


def snapshot_case_entities(case_name, notify=True):
    case = frappe.get_doc("Investigation Case", case_name)
    changes = []
    for ename in _entities_of_case(case_name):
        ent = frappe.get_doc("Investigation Entity", ename)
        raw = _load_raw(ent)
        prev = raw.get(MON_STATE) or {}
        cur = _signal(ent)
        if not cur:
            continue
        diffs = _diff(prev, cur)
        raw[MON_STATE] = cur
        frappe.db.set_value("Investigation Entity", ename, {
            "osint_raw": json.dumps(raw, default=str)[:130000],
            "last_osint_run": now_datetime(),
        }, update_modified=True)
        real = [x for x in diffs if x[0] != "BASELINE"]
        if real:
            changes.append((ename, ent.entity_type, real))
    if changes and notify:
        _alert(case, changes)
    frappe.db.commit()
    return {"case": case_name, "entities": len(_entities_of_case(case_name)), "changes": len(changes)}


def _alert(case, changes):
    rows, lines = "", []
    for ename, etype, diffs in changes:
        label = frappe.db.get_value("Investigation Entity", ename, "primary_identifier") or ename
        for kind, detail in diffs:
            color = "#C0392B" if kind in ("SANZIONI", "PEP", "THREAT") else "#0D1B3E"
            rows += ("<tr><td>%s <small>(%s)</small></td>"
                     "<td><b style='color:%s'>%s</b></td><td>%s</td></tr>"
                     % (label, etype, color, kind, detail))
            lines.append("%s %s: %s" % (label[:24], kind, detail))
    html = (
        "<h2 style='color:#0D1B3E'>Thanatos Intel — ALERT monitoraggio entità</h2>"
        "<p>Caso <b>%s</b> &middot; %s</p>"
        "<p>Variazioni di rischio sulle entità sorvegliate:</p>"
        "<table cellpadding='6' style='border-collapse:collapse;width:100%%;border:1px solid #e3e6ea;font-size:13px'>"
        "<tr style='background:#0D1B3E;color:#fff'><th>Entità</th><th>Tipo</th><th>Dettaglio</th></tr>%s</table>"
        "<p style='font-size:12px;color:#555'>Alert automatico. Le entità del caso sono ricontrollate "
        "periodicamente su sanzioni/PEP e threat intel: agire se compaiono nuovi riscontri.</p>"
        % (case.name, now(), rows))
    case.reload()
    case.append("case_activities", dict(
        activity_date=now_datetime(), activity_type="OSINT",
        description="ALERT monitoraggio entità: " + " | ".join(lines[:6]) + (" …" if len(lines) > 6 else ""),
        operator=frappe.session.user or "Administrator"))
    case.save(ignore_permissions=True)
    rec = _recipients(case)
    try:
        from thanatos_intel.integrations import email_render
        frappe.sendmail(recipients=rec, subject="[Thanatos] Alert entità — %s" % case.name,
                        message=email_render.render(html, preheader="Variazioni sulle entità monitorate",
                                                    cta=("Apri la pratica", "https://thanatos.agency/portal/case/%s" % case.name)),
                        reference_doctype="Investigation Case", reference_name=case.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "entity monitor alert email")


@frappe.whitelist()
def snapshot_case_entities_now(case_name):
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    return snapshot_case_entities(case_name, notify=True)


def run_entity_monitor():
    """Schedulata daily: entità non-wallet dei casi aperti."""
    cases = frappe.get_all("Investigation Case",
                           filters={"status": ["not in", ["Closed", "Archived"]]}, pluck="name")
    checked = total = 0
    for name in cases:
        try:
            r = snapshot_case_entities(name)
            if r["entities"]:
                checked += 1
                total += r["changes"]
        except Exception:
            frappe.log_error(frappe.get_traceback(), "entity monitor " + name)
    frappe.logger("entity_monitor").info(f"[{now()}] cases={checked} changes={total}")
    return {"cases_with_entities": checked, "changes": total}
