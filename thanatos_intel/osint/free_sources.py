"""
OSINT free-source connectors — Thanatos Intel.

Connettori per le fonti gratuite del catalogo operatori (/portal/osint/fonti).
Tutti degradano a {stub: True} se manca una chiave opzionale, senza errori.

Site config keys (opzionali):
opensanctions_api_key, etherscan_api_key, viewdns_api_key
"""
import json
import re
from typing import Optional

import frappe
import requests

from thanatos_intel.osint.engine import (UA, _cache_get, _cache_set,
                                         _cfg, _persist_lookup)

OPENSANCTIONS_URL = "https://api.opensanctions.org/search/default"
TRONSCAN_ACCOUNT_URL = "https://apilist.tronscanapi.com/api/accountv2"
ETHERSCAN_URL = "https://api.etherscan.io/api"
BLOCKCHAIN_RAWADDR_URL = "https://blockchain.info/rawaddr/{addr}"
WAYBACK_AVAILABLE_URL = "https://archive.org/wayback/available"
WAYBACK_CDX_URL = "http://web.archive.org/cdx/search/cdx"
VIEWDNS_IPHISTORY_URL = "https://api.viewdns.info/iphistory/"


# --------------------------------------------------------------------------- #
# Sanctions / PEP / wanted — OpenSanctions (aggrega OFAC, UN, EU, Interpol)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def screen_sanctions(name: str, schema: str = "Person") -> dict:
    """Screening sanzioni/PEP/wanted via OpenSanctions. Key opzionale."""
    name = (name or "").strip()
    if not name:
        return {"error": "invalid_name", "source": "opensanctions"}

    cached = _cache_get("opensanctions", f"{schema}:{name}")
    if cached:
        return {**cached, "cached": True}

    headers = {"user-agent": UA}
    api_key = _cfg("opensanctions_api_key")
    if api_key:
        headers["Authorization"] = f"ApiKey {api_key}"

    try:
        r = requests.get(
            OPENSANCTIONS_URL,
            headers=headers,
            params={"q": name, "schema": schema, "limit": 10},
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json() or {}
            results = data.get("results", []) or []
            hits = []
            for h in results:
                props = h.get("properties", {})
                hits.append({
                    "id": h.get("id"),
                    "caption": h.get("caption"),
                    "score": round(h.get("score", 0), 3),
                    "datasets": h.get("datasets", []),
                    "topics": props.get("topics", []),
                    "countries": props.get("country", []),
                })
            result = {"found": bool(hits), "matches": hits,
                      "total": data.get("total", {}).get("value", len(hits)),
                      "source": "opensanctions"}
        elif r.status_code in (401, 403):
            result = {"stub": True, "source": "opensanctions",
                      "message": "OpenSanctions key richiesta o invalida"}
        else:
            result = {"error": f"opensanctions_status_{r.status_code}",
                      "source": "opensanctions"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "opensanctions"}

    _cache_set("opensanctions", f"{schema}:{name}", result)
    _persist_lookup("Company" if schema == "Company" else "Username", name, result)
    return result


# --------------------------------------------------------------------------- #
# Crypto wallet — chain auto-detect + explorer free
# --------------------------------------------------------------------------- #
def detect_chain(addr: str) -> str:
    a = (addr or "").strip()
    if re.fullmatch(r"0x[a-fA-F0-9]{40}", a):
        return "eth"
    if re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]{33}", a):
        return "tron"
    if re.fullmatch(r"(bc1[a-z0-9]{25,90}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})", a):
        return "btc"
    return "unknown"


@frappe.whitelist()
def lookup_wallet(address: str) -> dict:
    """Dispatch wallet → explorer in base alla chain rilevata."""
    chain = detect_chain(address)
    if chain == "eth":
        return lookup_eth_wallet(address)
    if chain == "tron":
        return lookup_tron_wallet(address)
    if chain == "btc":
        return lookup_btc_wallet(address)
    return {"error": "unknown_chain", "source": "wallet", "address": address}


@frappe.whitelist()
def lookup_tron_wallet(address: str) -> dict:
    """TronScan — saldo TRX/USDT TRC-20 e attività. No key."""
    address = (address or "").strip()
    cached = _cache_get("tronscan", address)
    if cached:
        return {**cached, "cached": True}
    try:
        r = requests.get(TRONSCAN_ACCOUNT_URL, headers={"user-agent": UA},
                         params={"address": address}, timeout=12)
        if r.status_code == 200:
            d = r.json() or {}
            tokens = {t.get("tokenAbbr", "?").upper(): t.get("balance")
                      for t in (d.get("withPriceTokens") or [])[:10]}
            result = {
                "chain": "tron",
                "balance_trx": (d.get("balance") or 0) / 1_000_000,
                "tokens": tokens,
                "tx_count": d.get("totalTransactionCount", 0),
                "created": d.get("date_created"),
                "source": "tronscan",
            }
        else:
            result = {"error": f"tronscan_status_{r.status_code}", "source": "tronscan"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "tronscan"}
    _cache_set("tronscan", address, result)
    _persist_lookup("Wallet", address, result)
    return result


@frappe.whitelist()
def lookup_eth_wallet(address: str) -> dict:
    """Etherscan — saldo ETH e tx count. Key opzionale."""
    address = (address or "").strip()
    cached = _cache_get("etherscan", address)
    if cached:
        return {**cached, "cached": True}
    api_key = _cfg("etherscan_api_key")
    if not api_key:
        result = {"stub": True, "source": "etherscan", "chain": "eth",
                  "message": "etherscan_api_key non configurata"}
        _cache_set("etherscan", address, result)
        return result
    try:
        bal = requests.get(ETHERSCAN_URL, headers={"user-agent": UA}, params={
            "module": "account", "action": "balance", "address": address,
            "tag": "latest", "apikey": api_key}, timeout=12).json()
        txc = requests.get(ETHERSCAN_URL, headers={"user-agent": UA}, params={
            "module": "proxy", "action": "eth_getTransactionCount",
            "address": address, "tag": "latest", "apikey": api_key}, timeout=12).json()
        wei = int(bal.get("result") or 0)
        nonce = int((txc.get("result") or "0x0"), 16)
        result = {"chain": "eth", "balance_eth": wei / 1e18,
                  "tx_count": nonce, "source": "etherscan"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "etherscan"}
    _cache_set("etherscan", address, result)
    _persist_lookup("Wallet", address, result)
    return result


@frappe.whitelist()
def lookup_btc_wallet(address: str) -> dict:
    """Blockchain.info — saldo BTC e n. transazioni. No key."""
    address = (address or "").strip()
    cached = _cache_get("blockchain_btc", address)
    if cached:
        return {**cached, "cached": True}
    try:
        r = requests.get(BLOCKCHAIN_RAWADDR_URL.format(addr=address),
                         headers={"user-agent": UA}, params={"limit": 0}, timeout=12)
        if r.status_code == 200:
            d = r.json() or {}
            result = {"chain": "btc",
                      "balance_btc": (d.get("final_balance") or 0) / 1e8,
                      "total_received_btc": (d.get("total_received") or 0) / 1e8,
                      "tx_count": d.get("n_tx", 0), "source": "blockchain.info"}
        else:
            result = {"error": f"blockchain_status_{r.status_code}",
                      "source": "blockchain.info"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "blockchain.info"}
    _cache_set("blockchain_btc", address, result)
    _persist_lookup("Wallet", address, result)
    return result


# --------------------------------------------------------------------------- #
# Web archive — Wayback Machine (no key)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def lookup_wayback(target: str) -> dict:
    """Wayback Machine — primo/ultimo snapshot e conteggio. No key."""
    target = (target or "").strip()
    cached = _cache_get("wayback", target)
    if cached:
        return {**cached, "cached": True}
    try:
        avail = requests.get(WAYBACK_AVAILABLE_URL, headers={"user-agent": UA},
                            params={"url": target}, timeout=12).json()
        snap = (avail.get("archived_snapshots") or {}).get("closest") or {}
        cdx = requests.get(WAYBACK_CDX_URL, headers={"user-agent": UA}, params={
            "url": target, "output": "json", "limit": 1,
            "fl": "timestamp", "collapse": "timestamp:4"}, timeout=12)
        first_ts = ""
        try:
            rows = cdx.json()
            if len(rows) > 1:
                first_ts = rows[1][0]
        except Exception:
            pass
        result = {"archived": bool(snap), "closest": snap.get("timestamp"),
                  "first_snapshot": first_ts,
                  "closest_url": snap.get("url"), "source": "wayback"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "wayback"}
    _cache_set("wayback", target, result)
    return result


# --------------------------------------------------------------------------- #
# ViewDNS — IP history (free key)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def lookup_viewdns_iphistory(domain: str) -> dict:
    """ViewDNS — storico IP del dominio. Key gratuita richiesta."""
    domain = (domain or "").strip().lower()
    cached = _cache_get("viewdns", domain)
    if cached:
        return {**cached, "cached": True}
    api_key = _cfg("viewdns_api_key")
    if not api_key:
        result = {"stub": True, "source": "viewdns",
                  "message": "viewdns_api_key non configurata"}
        _cache_set("viewdns", domain, result)
        return result
    try:
        r = requests.get(VIEWDNS_IPHISTORY_URL, headers={"user-agent": UA}, params={
            "domain": domain, "apikey": api_key, "output": "json"}, timeout=12)
        d = (r.json() or {}).get("response", {})
        records = [{"ip": x.get("ip"), "location": x.get("location"),
                    "owner": x.get("owner"), "last_seen": x.get("lastseen")}
                   for x in (d.get("records") or [])]
        result = {"records": records, "count": len(records), "source": "viewdns"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "viewdns"}
    _cache_set("viewdns", domain, result)
    return result


# --------------------------------------------------------------------------- #
# Username — multi-platform check, no key (Sherlock-lite)
# --------------------------------------------------------------------------- #
USERNAME_SITES = {
    "GitHub": "https://github.com/{u}",
    "GitLab": "https://gitlab.com/{u}",
    "Reddit": "https://www.reddit.com/user/{u}/about.json",
    "Telegram": "https://t.me/{u}",
    "Keybase": "https://keybase.io/{u}",
    "Instagram": "https://www.instagram.com/{u}/",
}


@frappe.whitelist()
def lookup_username(username: str) -> dict:
    """Verifica presenza username su piattaforme pubbliche. No key."""
    username = (username or "").strip().lstrip("@")
    if not username or not re.fullmatch(r"[A-Za-z0-9_.\-]{2,40}", username):
        return {"error": "invalid_username", "source": "username"}
    cached = _cache_get("username", username)
    if cached:
        return {**cached, "cached": True}
    found = []
    for site, tpl in USERNAME_SITES.items():
        url = tpl.format(u=username)
        try:
            resp = requests.get(url, headers={"user-agent": UA},
                               timeout=8, allow_redirects=False)
            if resp.status_code == 200:
                found.append({"site": site, "url": url})
        except Exception:
            continue
    result = {"found": bool(found), "profiles": found,
              "checked": len(USERNAME_SITES), "source": "username"}
    _cache_set("username", username, result)
    _persist_lookup("Username", username, result)
    return result
