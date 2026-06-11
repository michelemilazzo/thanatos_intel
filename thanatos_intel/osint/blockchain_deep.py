"""Tracciamento profondo dei fondi BTC (value-weighted haircut).

Segue il flusso in uscita multi-hop fino ai nodi terminali, classificandoli in
exchange/custodia, wallet fermi (holding) e peel/dead-end, con gli importi.
Pesante: gira come job in background e scrive l'esito sul case + entita.
"""
import time

import frappe
import requests

SATS = 100_000_000
MAX_DEPTH = 5
TOP_K = 4
MIN_BTC = 0.05
MAX_NODES = 220
MEMPOOL = "https://mempool.space/api"
WE = "https://www.walletexplorer.com/api/1"


def _get(url, timeout=30):
    r = requests.get(url, headers={"User-Agent": "thanatos-intel"}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _balance(addr, cache):
    if addr in cache:
        return cache[addr]
    try:
        s = _get(f"{MEMPOOL}/address/{addr}")["chain_stats"]
        v = {"balance": s["funded_txo_sum"] - s["spent_txo_sum"], "received": s["funded_txo_sum"], "tx": s["tx_count"]}
    except Exception:
        v = {"balance": 0, "received": 0, "tx": 0}
    cache[addr] = v
    time.sleep(0.12)
    return v


def _label(addr, cache):
    if addr in cache:
        return cache[addr]
    import re
    lbl = None
    try:
        j = _get(f"{WE}/address?address={addr}&from=0&count=1&caller=thanatos")
        l = j.get("label")
        if l and not re.fullmatch(r"[0-9a-f]{12,16}", l):
            lbl = l
    except Exception:
        pass
    cache[addr] = lbl
    time.sleep(1.0)
    return lbl


def _out_edges(addr):
    edges, last = {}, None
    for _ in range(2):
        try:
            page = _get(f"{MEMPOOL}/address/{addr}/txs/chain" + (f"/{last}" if last else ""))
        except Exception:
            break
        if not page:
            break
        for tx in page:
            spends = sum(v["prevout"]["value"] for v in tx["vin"]
                         if v.get("prevout", {}).get("scriptpubkey_address") == addr)
            if not spends:
                continue
            for o in tx["vout"]:
                a = o.get("scriptpubkey_address")
                if a and a != addr:
                    edges[a] = edges.get(a, 0) + o["value"]
        if len(page) < 25:
            break
        last = page[-1]["txid"]
        time.sleep(0.15)
    return edges


def _classify(t):
    if t["label"] or t["balance"] > 100 * SATS or t["received"] > 1000 * SATS or t["tx"] > 500:
        return "EXCHANGE"
    if t["balance"] > 0.05 * SATS:
        return "HOLDING"
    return "PEEL"


def trace_core(root):
    bcache, lcache = {}, {}
    seed = _balance(root, bcache)["received"]
    queue = [(root, seed, 0)]
    visited, terminals, nodes = set(), {}, 0
    while queue and nodes < MAX_NODES:
        addr, taint, depth = queue.pop(0)
        if addr in visited:
            if addr in terminals:
                terminals[addr]["taint"] += taint
            continue
        visited.add(addr)
        nodes += 1
        if depth >= 1:
            lbl = _label(addr, lcache)
            bal = _balance(addr, bcache)
            t = {"taint": 0, "balance": bal["balance"], "received": bal["received"],
                 "tx": bal["tx"], "label": lbl, "depth": depth}
            klass = _classify(t)
            if klass in ("EXCHANGE", "HOLDING") or depth >= MAX_DEPTH:
                t["type"] = klass
                terminals.setdefault(addr, t)
                terminals[addr]["taint"] += taint
                continue
        edges = _out_edges(addr)
        total = sum(edges.values()) or 1
        for a, v in sorted(edges.items(), key=lambda x: -x[1])[:TOP_K]:
            ct = taint * (v / total)
            if ct >= MIN_BTC * SATS and a not in visited:
                queue.append((a, ct, depth + 1))
    return nodes, terminals


def _run(address, case_name, user):
    nodes, terminals = trace_core(address)
    ex = {a: t for a, t in terminals.items() if t["type"] == "EXCHANGE"}
    hold = {a: t for a, t in terminals.items() if t["type"] == "HOLDING"}
    tot = sum(t["taint"] for t in terminals.values()) or 1
    ex_t = sum(t["taint"] for t in ex.values())
    ho_t = sum(t["taint"] for t in hold.values())

    # entita per i wallet HOLDING (potenzialmente congelabili)
    for a, t in hold.items():
        if not frappe.db.exists("Investigation Entity", a):
            doc = frappe.get_doc({"doctype": "Investigation Entity", "entity_type": "Wallet",
                "primary_identifier": a, "notes": "Wallet che TRATTIENE fondi (%.4f BTC) sul percorso da %s — potenzialmente congelabile." % (t["balance"]/SATS, address[:12])})
            doc.append("risk_indicators", dict(indicator_type="Holding stolen funds",
                value="%.4f BTC fermi" % (t["balance"]/SATS), source="mempool.space", points=40, verified=1))
            doc.insert(ignore_permissions=True)

    if case_name:
        case = frappe.get_doc("Investigation Case", case_name)
        case.append("case_activities", dict(activity_date=frappe.utils.now_datetime(), activity_type="OSINT",
            description="Tracciamento profondo %s: %d nodi, %d terminali exchange (%.1f%% flusso), %d wallet fermi (%.1f%%). %s" % (
                address[:14], nodes, len(ex), ex_t/tot*100, len(hold), ho_t/tot*100,
                "Wallet holding creati come entita." if hold else "Nessun wallet trattiene importi significativi."),
            operator="Administrator"))
        case.save(ignore_permissions=True)
    frappe.db.commit()

    if user:
        frappe.publish_realtime("msgprint", {"message":
            "Tracciamento profondo completato: %d nodi, %d exchange terminali, %d wallet fermi." % (nodes, len(ex), len(hold)),
            "title": "Blockchain", "indicator": "green"}, user=user)


@frappe.whitelist()
def trace_funds(address, case_name=None):
    """Avvia il tracciamento profondo in background (richiede minuti)."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    if not case_name:
        cs = frappe.get_all("Case Entity", filters={"entity": address, "parenttype": "Investigation Case"}, pluck="parent")
        case_name = cs[0] if cs else None
    frappe.enqueue("thanatos_intel.osint.blockchain_deep._run", queue="long", timeout=1800,
                   address=address, case_name=case_name, user=frappe.session.user)
    return {"started": True, "case": case_name}
