"""Tracciamento on-chain Bitcoin via mempool.space (API pubblica, no key).

Usato dal bottone "Traccia wallet" su Investigation Entity (entity_type=Wallet)
e dal servizio SVC-FI-011. Aggrega controparti, verifica i saldi, crea le
entita per gli hub rilevanti e allega il report ai case collegati.
"""
import json
import time

import frappe
import requests
from frappe.utils import now_datetime

API = "https://mempool.space/api"
SATS = 100_000_000
HUB_TX_THRESHOLD = 100         # tx count oltre cui una controparte e un hub
HUB_BTC_THRESHOLD = 5 * SATS   # o volume totale ricevuto oltre 5 BTC
EXCHANGE_TX = 5000             # oltre = exchange/VASP (omnibus), non hub della rete
EXCHANGE_BTC = 1000 * SATS
MAX_NEW_ENTITIES = 6           # cap entita create per tracciamento (solo uscite, top volume)


def _get(path):
    r = requests.get(API + path, timeout=30, headers={"User-Agent": "thanatos-intel"})
    r.raise_for_status()
    return r.json()


def _all_txs(addr, max_pages=40):
    """Default 40 pagine da 25 tx = fino a ~1000 transazioni per indirizzo.
    Parametrizzabile per estrazioni piu' aggressive quando serve."""
    txs, last = [], None
    for _ in range(max_pages):
        page = _get(f"/address/{addr}/txs/chain" + (f"/{last}" if last else ""))
        if not page:
            break
        txs.extend(page)
        if len(page) < 25:
            break
        last = page[-1]["txid"]
        time.sleep(0.2)
    return txs


def _aggregate(addr, txs):
    inflow, outflow, timeline = {}, {}, []
    for tx in txs:
        ts = tx.get("status", {}).get("block_time", 0)
        in_self = sum(v["prevout"]["value"] for v in tx["vin"]
                      if v.get("prevout", {}).get("scriptpubkey_address") == addr)
        out_self = sum(o["value"] for o in tx["vout"]
                       if o.get("scriptpubkey_address") == addr)
        if in_self:
            for o in tx["vout"]:
                a = o.get("scriptpubkey_address")
                if a and a != addr:
                    outflow[a] = outflow.get(a, 0) + o["value"]
            timeline.append((ts, "OUT", in_self - out_self, tx["txid"]))
        if out_self and not in_self:
            for v in tx["vin"]:
                a = v.get("prevout", {}).get("scriptpubkey_address")
                if a and a != addr:
                    inflow[a] = inflow.get(a, 0) + v["prevout"]["value"]
            timeline.append((ts, "IN", out_self, tx["txid"]))
    timeline.sort()
    return inflow, outflow, timeline


def _balance(addr):
    s = _get(f"/address/{addr}")["chain_stats"]
    return {"balance": s["funded_txo_sum"] - s["spent_txo_sum"],
            "received": s["funded_txo_sum"], "tx_count": s["tx_count"]}


def _fmt_date(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%d/%m/%Y") if ts else "?"


def _report_html(result):
    def rows(items):
        return "".join(
            f"<tr><td><code>{a}</code></td><td align=right>{v / SATS:.4f}</td>"
            f"<td align=right>{(b or {}).get('balance', 0) / SATS:.4f}</td>"
            f"<td align=right>{(b or {}).get('received', 0) / SATS:.2f}</td>"
            f"<td align=right>{(b or {}).get('tx_count', '?')}</td></tr>"
            for a, v, b in items)
    head = ("<tr><th>Indirizzo</th><th>BTC col target</th><th>Saldo attuale</th>"
            "<th>Ricevuto totale</th><th># tx</th></tr>")
    return f"""
<h2>Tracciamento blockchain — <code>{result["target"]}</code></h2>
<p>Generato {result["generated"]} via mempool.space &middot; {result["tx_count"]} tx
&middot; attivita {_fmt_date(result["first_seen"])} → {_fmt_date(result["last_seen"])}
&middot; saldo attuale {result["balance"] / SATS:.8f} BTC
&middot; transitati {result["received"] / SATS:.8f} BTC</p>
<h3>Uscite (top {len(result["top_outflow"])})</h3>
<table border="1" cellpadding="3">{head}{rows(result["top_outflow"])}</table>
<h3>Entrate (top {len(result["top_inflow"])})</h3>
<table border="1" cellpadding="3">{head}{rows(result["top_inflow"])}</table>
"""


@frappe.whitelist()
def trace_wallet(address: str, top_n: int = 15, max_pages: int = 40) -> dict:
    """Traccia un wallet BTC: controparti, saldi, hub, report sui case collegati.
    max_pages controlla il numero di pagine di TX (25 tx/pagina, 40=~1000 TX)."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    address = address.strip()
    top_n = min(int(top_n), 20)
    max_pages = max(1, min(int(max_pages), 200))

    stats = _balance(address)
    txs = _all_txs(address, max_pages=max_pages)
    inflow, outflow, timeline = _aggregate(address, txs)
    top_out = sorted(outflow.items(), key=lambda x: -x[1])[:top_n]
    top_in = sorted(inflow.items(), key=lambda x: -x[1])[:top_n]

    balances = {}
    for a, _ in top_out + top_in:
        if a not in balances:
            try:
                balances[a] = _balance(a)
            except Exception:
                balances[a] = None
            time.sleep(0.15)

    result = {
        "target": address, "generated": frappe.utils.now(),
        "tx_count": len(txs), "balance": stats["balance"], "received": stats["received"],
        "first_seen": timeline[0][0] if timeline else 0,
        "last_seen": timeline[-1][0] if timeline else 0,
        "top_outflow": [(a, v, balances.get(a)) for a, v in top_out],
        "top_inflow": [(a, v, balances.get(a)) for a, v in top_in],
    }

    # entita target: osint_raw + indicatori pattern
    hubs = []
    if frappe.db.exists("Investigation Entity", address):
        ent = frappe.get_doc("Investigation Entity", address)
        ent.last_osint_run = now_datetime()
        ent.osint_raw = json.dumps(result, default=str)
        existing_ind = {r.indicator_type for r in ent.risk_indicators}
        if stats["balance"] == 0 and stats["received"] > 0 and "Pass-through wallet" not in existing_ind:
            ent.append("risk_indicators", dict(
                indicator_type="Pass-through wallet",
                value=f"{stats['received'] / SATS:.4f} BTC transitati, saldo 0",
                source="mempool.space", points=60, verified=1))
        ent.save(ignore_permissions=True)

    # solo controparti in USCITA (dove vanno i fondi), top per volume, cap
    candidates = [(a, v, b) for a, v, b in result["top_outflow"] if b and a != address]
    candidates.sort(key=lambda x: -x[1])
    for a, v, b in candidates[:MAX_NEW_ENTITIES]:
        is_exchange = b["tx_count"] >= EXCHANGE_TX or b["received"] >= EXCHANGE_BTC
        is_hub = b["tx_count"] >= HUB_TX_THRESHOLD or b["received"] >= HUB_BTC_THRESHOLD
        if not (is_exchange or is_hub) or frappe.db.exists("Investigation Entity", a):
            continue
        if is_exchange:
            kind, pts = "Exchange/VASP endpoint", 40
            note = (f"ENDPOINT cash-out (exchange/VASP, omnibus) dal tracciamento di {address}: "
                    f"{b['tx_count']} tx, {b['received'] / SATS:.0f} BTC cumulativi. "
                    f"PUNTO DI RECUPERO: identificare il servizio e richiedere KYC via autorita.")
        else:
            kind, pts = "Consolidation hub", 55
            note = (f"Hub intermedio dal tracciamento di {address}: "
                    f"{b['received'] / SATS:.2f} BTC ricevuti, {b['tx_count']} tx, "
                    f"saldo {b['balance'] / SATS:.4f}.")
        doc = frappe.get_doc({"doctype": "Investigation Entity", "entity_type": "Wallet",
                              "primary_identifier": a, "notes": note})
        doc.append("risk_indicators", dict(
            indicator_type=kind, value=f"{b['received'] / SATS:.2f} BTC, {b['tx_count']} tx",
            source="mempool.space", points=pts, verified=1))
        doc.insert(ignore_permissions=True)
        hubs.append(a)
        try:
            from thanatos_intel.osint import arkham
            arkham.enrich_entity(a, chain="bitcoin")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "arkham hub label")

    # case collegati: entita hub, attivita, allegati
    cases = frappe.get_all("Case Entity", filters={
        "entity": address, "parenttype": "Investigation Case"}, pluck="parent")
    html = _report_html(result)
    raw = json.dumps(result, default=str)
    stamp = frappe.utils.nowdate().replace("-", "")
    for case_name in set(cases):
        case = frappe.get_doc("Investigation Case", case_name)
        have = {r.entity for r in case.case_entities}
        for a in hubs:
            if a not in have:
                case.append("case_entities", dict(
                    entity=a, role_in_case="Related",
                    notes=f"Hub da tracciamento {address[:12]}…"))
        case.append("case_activities", dict(
            activity_date=now_datetime(), activity_type="OSINT",
            description=(f"Tracciamento on-chain {address}: {len(txs)} tx, "
                         f"{len(balances)} controparti verificate, {len(hubs)} nuovi hub. "
                         f"Ultimo movimento {_fmt_date(result['last_seen'])}."),
            operator=frappe.session.user))
        case.save(ignore_permissions=True)
        for fname, content in [(f"trace_{address[:12]}_{stamp}.html", html),
                               (f"trace_{address[:12]}_{stamp}.json", raw)]:
            if not frappe.db.exists("File", {"attached_to_doctype": "Investigation Case",
                                             "attached_to_name": case_name, "file_name": fname}):
                frappe.get_doc({"doctype": "File", "file_name": fname, "content": content,
                                "attached_to_doctype": "Investigation Case",
                                "attached_to_name": case_name,
                                "is_private": 1}).insert(ignore_permissions=True)

    frappe.db.commit()
    return {"tx_count": len(txs), "counterparties": len(balances),
            "hubs_created": len(hubs), "cases_updated": len(set(cases)),
            "balance_btc": stats["balance"] / SATS,
            "last_seen": _fmt_date(result["last_seen"])}
