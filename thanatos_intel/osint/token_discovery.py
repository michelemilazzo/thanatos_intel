"""Scoperta dei token (fungibili) presenti su un wallet, per il servizio di
verifica automatizzata a step.

Fonti pubbliche senza API key:
- EVM (indirizzi 0x…): Blockscout v2 (eth.blockscout.com e istanze per-catena).
- TRON (indirizzi T…): TronGrid (api.trongrid.io) — saldi TRC20.
- BTC (bc1/1/3…): nessun token, lista vuota.

Override base per-catena via site_config 'blockscout_bases' (dict chain->url).
"""
import json
import re

import frappe
import requests

UA = {"User-Agent": "thanatos-intel"}
TIMEOUT = 25

# Istanze Blockscout note (keyless). Estendibili da site_config.
BLOCKSCOUT = {
    "ethereum": "https://eth.blockscout.com",
    "base": "https://base.blockscout.com",
    "optimism": "https://optimism.blockscout.com",
    "gnosis": "https://gnosis.blockscout.com",
    "polygon": "https://polygon.blockscout.com",
}

# Token TRC20 più comuni (TronGrid dà contract->saldo, non simbolo).
TRON_KNOWN = {
    "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": ("USDT", 6),
    "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8": ("USDC", 6),
    "TUpMhErZL2fhh4sVNULAbNKLokS4GjC1F4": ("TUSD", 18),
}

_EVM = re.compile(r"^0x[a-fA-F0-9]{40}$")
_TRON = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")


def detect_chain(address):
    if _EVM.match(address or ""):
        return "evm"
    if _TRON.match(address or ""):
        return "tron"
    return "btc"


def _bases():
    b = dict(BLOCKSCOUT)
    extra = frappe.conf.get("blockscout_bases")
    if isinstance(extra, dict):
        b.update(extra)
    return b


def _human(raw, decimals):
    try:
        return float(raw) / (10 ** int(decimals or 0))
    except Exception:
        return None


def _evm_tokens(address, chain="ethereum"):
    base = _bases().get(chain, BLOCKSCOUT["ethereum"])
    url = "%s/api/v2/addresses/%s/tokens?type=ERC-20" % (base, address)
    out = []
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        for it in (r.json().get("items") or []):
            t = it.get("token") or {}
            dec = t.get("decimals")
            out.append({
                "chain": chain, "contract": t.get("address_hash") or t.get("address"),
                "symbol": t.get("symbol") or "?", "name": t.get("name") or "",
                "decimals": dec, "balance": _human(it.get("value"), dec),
            })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "token discovery evm %s" % address)
    return out


def _tron_tokens(address):
    url = "https://api.trongrid.io/v1/accounts/%s" % address
    out = []
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        data = (r.json().get("data") or [{}])[0]
        for entry in (data.get("trc20") or []):
            for contract, raw in entry.items():
                sym, dec = TRON_KNOWN.get(contract, ("?", 6))
                out.append({
                    "chain": "tron", "contract": contract, "symbol": sym, "name": "",
                    "decimals": dec, "balance": _human(raw, dec),
                })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "token discovery tron %s" % address)
    return out


def discover_tokens(address):
    """Lista dei token fungibili presenti sull'indirizzo (best-effort, fonti pubbliche)."""
    chain = detect_chain(address)
    if chain == "tron":
        toks = _tron_tokens(address)
    elif chain == "evm":
        toks = _evm_tokens(address, "ethereum")
    else:
        toks = []
    # solo saldi > 0, ordinati per simbolo
    toks = [t for t in toks if (t.get("balance") or 0) > 0]
    toks.sort(key=lambda t: (t.get("symbol") or "z"))
    for t in toks:
        t["key"] = "%s:%s" % (t["chain"], (t["contract"] or "").lower())
        t["address"] = address
    return toks


def _wallets_of_case(case):
    out = []
    for ce in (case.get("case_entities") or []):
        if (ce.entity_type or "") == "Wallet" or \
           frappe.db.get_value("Investigation Entity", ce.entity, "entity_type") == "Wallet":
            out.append(ce.entity)
    return list(dict.fromkeys(out))


@frappe.whitelist()
def discover_case_tokens(case_name):
    """Token presenti sui wallet della pratica, per la selezione nel portale."""
    from thanatos_intel.workflow.engagement import _guard
    _guard(case_name)
    case = frappe.get_doc("Investigation Case", case_name)
    tokens, seen = [], set()
    for addr in _wallets_of_case(case):
        for t in discover_tokens(addr):
            if t["key"] in seen:
                continue
            seen.add(t["key"])
            tokens.append(t)
    bp = case.get("blueprint")
    unit = frappe.db.get_value("Service Blueprint", bp, "token_unit_price") if bp else 0
    return {"tokens": tokens, "unit_price": float(unit or 0), "currency": "EUR",
            "count": len(tokens)}


# ---- verifica a pagamento dei token selezionati ----

def _chain_for_arkham(chain):
    return "tron" if chain == "tron" else "ethereum"


def verify_tokens(case_name):
    """Esegue la verifica (attribuzione Arkham best-effort) sui token selezionati e
    salvati in token_selection_json, produce un report e lo allega al caso."""
    case = frappe.get_doc("Investigation Case", case_name)
    try:
        sel = json.loads(case.get("token_selection_json") or "[]")
    except Exception:
        sel = []
    if not sel:
        return {"ok": True, "verified": 0}

    from thanatos_intel.osint import arkham
    rows = []
    for t in sel:
        contract = t.get("contract")
        att = {}
        try:
            att = arkham.attribute(contract, chain=_chain_for_arkham(t.get("chain"))) or {}
        except Exception:
            frappe.log_error(frappe.get_traceback(), "token verify arkham %s" % contract)
        flags = []
        if att.get("is_illicit"):
            flags.append("ILLECITO")
        if att.get("is_cashout"):
            flags.append("EXCHANGE/VASP")
        rows.append({
            "symbol": t.get("symbol") or "?", "chain": t.get("chain"),
            "contract": contract, "balance": t.get("balance"),
            "entity": att.get("entity") or "-", "label": att.get("label") or "-",
            "flags": ", ".join(flags) or "—",
        })

    html = _token_report_html(case, rows)
    fname = "verifica_token_%s_%s.html" % (case.name, frappe.utils.nowdate().replace("-", ""))
    old = frappe.db.get_value("File", {"attached_to_doctype": "Investigation Case",
                                       "attached_to_name": case.name, "file_name": fname}, "name")
    if old:
        frappe.delete_doc("File", old, ignore_permissions=True, force=True)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "content": html, "is_private": 1,
                        "attached_to_doctype": "Investigation Case", "attached_to_name": case.name})
    f.flags.ignore_permissions = True
    f.save(ignore_permissions=True)

    case.append("case_activities", {
        "activity_date": frappe.utils.now_datetime(), "activity_type": "OSINT",
        "description": "Verifica token: %d token verificati. Report allegato." % len(rows),
        "operator": frappe.session.user or "Administrator",
    })
    case.db_set("token_selection_json", "", update_modified=False)
    case.save(ignore_permissions=True)
    frappe.db.commit()
    try:
        from thanatos_intel.workflow.engagement import _notify_client
        _notify_client(case, f.file_url)
    except Exception:
        pass
    return {"ok": True, "verified": len(rows), "report": f.file_url}


def _token_report_html(case, rows):
    body = ""
    for r in rows:
        color = "#C0392B" if r["flags"] not in ("—", "") else "#0D1B3E"
        body += ("<tr><td><b>%s</b></td><td>%s</td><td style='font-family:monospace;font-size:11px'>%s</td>"
                 "<td>%s</td><td>%s</td><td style='color:%s'><b>%s</b></td></tr>" % (
                     r["symbol"], r["chain"], r["contract"], r["balance"], r["entity"], color, r["flags"]))
    return (
        "<h2 style='color:#0D1B3E'>Thanatos Intel — Verifica Token</h2>"
        "<p>Pratica <b>%s</b> · %s</p>"
        "<table border='1' cellpadding='5' style='border-collapse:collapse'>"
        "<tr style='background:#0D1B3E;color:#fff'><th>Token</th><th>Catena</th><th>Contratto</th>"
        "<th>Saldo</th><th>Attribuzione</th><th>Flag</th></tr>%s</table>"
        "<p style='font-size:11px;color:#666'>Attribuzione via Arkham Intelligence. "
        "I flag exchange/VASP indicano punti di recupero (richiedere KYC del titolare via autorità).</p>"
        % (case.name, frappe.utils.now(), body))
