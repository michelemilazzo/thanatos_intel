"""Monitoraggio h24 dei wallet dei case + alert ad ogni cambiamento.

Schedulato (hourly). Per ogni Investigation Case aperto con wallet collegati,
confronta saldo on-chain (mempool.space) e attribuzione (Arkham) con l'ultimo
stato salvato sull'entita; ad ogni variazione di saldo, di attribuzione o di
"misura di sicurezza" (flag exchange/illecito, status entita) registra
un'attivita sul case, crea una Notification in-app e invia un'email di alert.

Stato precedente conservato in osint_raw['_monitor'] della Investigation Entity.
Destinatari override: site_config 'monitor_alert_recipients' (csv).
"""
import json

import frappe
from frappe.utils import now, now_datetime

from thanatos_intel.osint import arkham
from thanatos_intel.osint import blockchain as bc

SATS = 100_000_000
STATE_KEY = "_monitor"


def _load_raw(ent):
    try:
        raw = json.loads(ent.osint_raw) if ent.osint_raw else {}
    except Exception:
        raw = {}
    return raw if isinstance(raw, dict) else {}


def _wallets_of_case(case):
    out, seen = [], set()
    for ce in case.case_entities:
        if ce.entity in seen:
            continue
        if frappe.db.get_value("Investigation Entity", ce.entity, "entity_type") == "Wallet":
            seen.add(ce.entity)
            out.append(ce.entity)
    return out


def _recipients(case):
    rec = []
    inv = case.get("assigned_investigator")
    if inv:
        user = frappe.db.get_value("Investigator", inv, "platform_user")
        if user:
            em = frappe.db.get_value("User", user, "email") or user
            if em and "@" in em:
                rec.append(em)
    extra = frappe.conf.get("monitor_alert_recipients")
    if extra:
        rec += [e.strip() for e in str(extra).split(",") if e.strip()]
    if not rec:
        rec.append("admin@thanatos.agency")
    return list(dict.fromkeys(rec))


def check_wallet(address):
    """Stato corrente di un wallet: saldo + attribuzione."""
    bal = bc._balance(address)
    att = arkham.attribute(address)
    return {
        "balance": bal["balance"], "received": bal["received"], "tx": bal["tx_count"],
        "entity": att.get("entity"), "label": att.get("label"),
        "cashout": bool(att.get("is_cashout")), "illicit": bool(att.get("is_illicit")),
        "ts": now(),
    }


def _diff(prev, cur):
    diffs = []
    if not prev:
        diffs.append(("BASELINE", "stato iniziale registrato (saldo %.8f BTC, %s)"
                      % (cur["balance"] / SATS, cur.get("entity") or "non attribuito")))
        return diffs
    if cur["balance"] != (prev.get("balance") or 0):
        delta = (cur["balance"] - (prev.get("balance") or 0)) / SATS
        diffs.append(("SALDO", "%+.8f BTC (ora %.8f)" % (delta, cur["balance"] / SATS)))
    if (cur.get("entity") or "") != (prev.get("entity") or ""):
        diffs.append(("ATTRIBUZIONE", "%s -> %s" % (prev.get("entity") or "-", cur.get("entity") or "-")))
    for flag, lbl in (("illicit", "ILLECITO"), ("cashout", "EXCHANGE/VASP")):
        if bool(cur.get(flag)) != bool(prev.get(flag)):
            diffs.append(("MISURA DI SICUREZZA",
                          "%s: %s" % (lbl, "ATTIVATO" if cur.get(flag) else "rimosso")))
    return diffs


def snapshot_case(case_name, notify=True):
    """Fotografa i wallet del case, salva lo stato e segnala le variazioni."""
    case = frappe.get_doc("Investigation Case", case_name)
    wallets = _wallets_of_case(case)
    changes = []
    for addr in wallets:
        ent = frappe.get_doc("Investigation Entity", addr)
        raw = _load_raw(ent)
        prev = raw.get(STATE_KEY) or {}
        try:
            cur = check_wallet(addr)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "monitor check " + addr)
            continue
        diffs = _diff(prev, cur)
        raw[STATE_KEY] = {k: cur[k] for k in
                          ("balance", "received", "tx", "entity", "label", "cashout", "illicit", "ts")}
        ent.osint_raw = json.dumps(raw, default=str)[:130000]
        ent.last_osint_run = now_datetime()
        ent.save(ignore_permissions=True)
        real = [d for d in diffs if d[0] != "BASELINE"]
        if real:
            changes.append((addr, cur, real))
    if changes and notify:
        _alert(case, changes)
    frappe.db.commit()
    return {"case": case_name, "wallets": len(wallets), "changes": len(changes)}


def _alert(case, changes):
    rows, lines = "", []
    for addr, cur, diffs in changes:
        for kind, detail in diffs:
            color = "#C0392B" if kind in ("MISURA DI SICUREZZA", "SALDO") else "#0D1B3E"
            rows += ("<tr><td style='font-family:monospace;font-size:11px'>%s</td>"
                     "<td><b style='color:%s'>%s</b></td><td>%s</td></tr>" % (addr, color, kind, detail))
            lines.append("%s… %s: %s" % (addr[:16], kind, detail))
    html = (
        "<h2 style='color:#0D1B3E'>Thanatos Intel — ALERT monitoraggio wallet</h2>"
        "<p>Caso <b>%s</b> &middot; %s</p>"
        "<p>Sono state rilevate variazioni sugli indirizzi monitorati h24:</p>"
        "<table border='1' cellpadding='5' style='border-collapse:collapse'>"
        "<tr style='background:#0D1B3E;color:#fff'><th>Indirizzo</th><th>Tipo</th><th>Dettaglio</th></tr>"
        "%s</table>"
        "<p style='font-size:12px;color:#555'>Alert automatico. Gli indirizzi del caso sono sorvegliati "
        "in continuo: ogni cambiamento di saldo, attribuzione o misura di sicurezza genera questa notifica. "
        "Agire con tempestivita se compaiono fondi su un wallet del soggetto.</p>"
        % (case.name, now(), rows))

    case.append("case_activities", dict(
        activity_date=now_datetime(), activity_type="OSINT",
        description="ALERT monitoraggio: " + " | ".join(lines[:6]) + (" …" if len(lines) > 6 else ""),
        operator=frappe.session.user or "Administrator"))
    case.save(ignore_permissions=True)

    rec = _recipients(case)
    try:
        frappe.sendmail(recipients=rec, subject="[Thanatos] Alert wallet — %s" % case.name,
                        message=html, reference_doctype="Investigation Case", reference_name=case.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "monitor alert email")
    for user in rec:
        if frappe.db.exists("User", user):
            try:
                frappe.get_doc({"doctype": "Notification Log", "subject": "Alert wallet — %s" % case.name,
                                "for_user": user, "type": "Alert", "document_type": "Investigation Case",
                                "document_name": case.name,
                                "email_content": "<br>".join(lines[:8])}).insert(ignore_permissions=True)
            except Exception:
                pass


@frappe.whitelist()
def snapshot_case_now(case_name):
    """Esecuzione manuale del monitor su un singolo case (bottone)."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    return snapshot_case(case_name, notify=True)


def run_monitor():
    """Entry schedulata (hourly): monitora tutti i case aperti con wallet."""
    cases = frappe.get_all("Investigation Case",
                           filters={"status": ["not in", ["Closed", "Archived"]]}, pluck="name")
    checked = total_changes = 0
    for name in cases:
        try:
            r = snapshot_case(name)
            if r["wallets"]:
                checked += 1
                total_changes += r["changes"]
        except Exception:
            frappe.log_error(frappe.get_traceback(), "wallet monitor " + name)
    return {"cases_with_wallets": checked, "changes": total_changes}
