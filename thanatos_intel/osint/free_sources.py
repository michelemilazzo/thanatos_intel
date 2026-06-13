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
    """Screening sanzioni/PEP/wanted.

    Offline-first: usa la cache locale OpenSanctions (`tabOpenSanctions Cache`,
    rinfrescata ogni 24h da opensanctions_sync.daily_refresh, ~285k entità).
    Fallback all'API OpenSanctions solo se la cache è vuota/assente.
    """
    name = (name or "").strip()
    if not name:
        return {"error": "invalid_name", "source": "opensanctions"}

    # 1) cache locale offline (no rete, no key, dato fresco <24h)
    offline = _screen_offline(name)
    if offline is not None:
        _persist_lookup({"Company": "Company", "CryptoWallet": "Wallet"}.get(schema, "Username"),
                        name, offline)
        return offline

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
    tt = {"Company": "Company", "CryptoWallet": "Wallet"}.get(schema, "Username")
    _persist_lookup(tt, name, result)
    return result


def _screen_offline(name: str):
    """Match contro la cache locale OpenSanctions. None se cache assente/vuota."""
    try:
        if not frappe.db.table_exists("OpenSanctions Cache"):
            return None
        if not frappe.db.sql("SELECT 1 FROM `tabOpenSanctions Cache` LIMIT 1"):
            return None
        from thanatos_intel.thanatos_ddd import opensanctions_sync
        res = opensanctions_sync.lookup(name)
        raw = res.get("matches") or []
        hits = []
        for h in raw[:10]:
            topics = h.get("topics")
            if isinstance(topics, str):
                topics = [t.strip() for t in topics.replace("[", "").replace("]", "")
                          .replace('"', "").split(",") if t.strip()]
            hits.append({
                "id": h.get("id"),
                "caption": h.get("caption") or h.get("name"),
                "score": h.get("score", 0),
                "topics": topics or [],
                "countries": [h.get("nationality")] if h.get("nationality") else [],
                "datasets": ["opensanctions_local"],
            })
        return {"found": bool(hits), "matches": hits, "total": res.get("total", len(hits)),
                "source": "opensanctions", "offline": True}
    except Exception:
        return None


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


# --------------------------------------------------------------------------- #
# Phone — metadata offline (prefisso internazionale → paese), no dipendenze
# --------------------------------------------------------------------------- #
# Prefissi più lunghi prima per il match greedy.
DIAL_CODES = [
    ("1", "US/CA"), ("7", "RU/KZ"), ("20", "EG"), ("27", "ZA"), ("30", "GR"),
    ("31", "NL"), ("32", "BE"), ("33", "FR"), ("34", "ES"), ("36", "HU"),
    ("39", "IT"), ("40", "RO"), ("41", "CH"), ("43", "AT"), ("44", "GB"),
    ("45", "DK"), ("46", "SE"), ("47", "NO"), ("48", "PL"), ("49", "DE"),
    ("51", "PE"), ("52", "MX"), ("53", "CU"), ("54", "AR"), ("55", "BR"),
    ("56", "CL"), ("57", "CO"), ("58", "VE"), ("60", "MY"), ("61", "AU"),
    ("62", "ID"), ("63", "PH"), ("64", "NZ"), ("65", "SG"), ("66", "TH"),
    ("81", "JP"), ("82", "KR"), ("84", "VN"), ("86", "CN"), ("90", "TR"),
    ("91", "IN"), ("92", "PK"), ("93", "AF"), ("94", "LK"), ("95", "MM"),
    ("98", "IR"), ("212", "MA"), ("213", "DZ"), ("216", "TN"), ("218", "LY"),
    ("220", "GM"), ("221", "SN"), ("234", "NG"), ("254", "KE"), ("255", "TZ"),
    ("256", "UG"), ("260", "ZM"), ("263", "ZW"), ("351", "PT"), ("352", "LU"),
    ("353", "IE"), ("354", "IS"), ("355", "AL"), ("356", "MT"), ("357", "CY"),
    ("358", "FI"), ("359", "BG"), ("370", "LT"), ("371", "LV"), ("372", "EE"),
    ("373", "MD"), ("374", "AM"), ("375", "BY"), ("376", "AD"), ("377", "MC"),
    ("378", "SM"), ("380", "UA"), ("381", "RS"), ("382", "ME"), ("385", "HR"),
    ("386", "SI"), ("387", "BA"), ("389", "MK"), ("420", "CZ"), ("421", "SK"),
    ("423", "LI"), ("852", "HK"), ("853", "MO"), ("855", "KH"), ("856", "LA"),
    ("880", "BD"), ("886", "TW"), ("962", "JO"), ("963", "SY"), ("964", "IQ"),
    ("965", "KW"), ("966", "SA"), ("967", "YE"), ("968", "OM"), ("970", "PS"),
    ("971", "AE"), ("972", "IL"), ("973", "BH"), ("974", "QA"), ("975", "BT"),
    ("976", "MN"), ("977", "NP"), ("992", "TJ"), ("993", "TM"), ("994", "AZ"),
    ("995", "GE"), ("996", "KG"), ("998", "UZ"),
]
HIGH_RISK_DIAL = {"IR", "SY", "KP", "RU", "AF", "YE", "LY"}


@frappe.whitelist()
def lookup_phone(number: str) -> dict:
    """Metadata offline da numero E.164: paese, validità base, flag rischio."""
    raw = (number or "").strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):          # prefisso internazionale 00 → +
        digits = "+" + digits[2:]
    e164 = digits if digits.startswith("+") else ("+" + digits if digits else "")
    core = e164.lstrip("+")
    country = ""
    cc = ""
    for code, ctry in sorted(DIAL_CODES, key=lambda x: -len(x[0])):
        if core.startswith(code):
            country, cc = ctry, code
            break
    national = core[len(cc):] if cc else core
    valid = bool(country) and 6 <= len(national) <= 13
    result = {
        "input": raw, "e164": e164, "country": country or "unknown",
        "country_code": ("+" + cc) if cc else "",
        "national_number": national, "valid": valid,
        "high_risk_country": any(c in HIGH_RISK_DIAL for c in country.split("/")),
        "source": "phone_meta",
    }
    _persist_lookup("Phone", e164 or raw, result)
    return result


# --------------------------------------------------------------------------- #
# Aereo — OpenSky aircraft database (ICAO24 hex o registrazione), no key
# --------------------------------------------------------------------------- #
OPENSKY_META_URL = "https://opensky-network.org/api/metadata/aircraft/icao24/{hex}"


@frappe.whitelist()
def lookup_flight(query: str) -> dict:
    """OpenSky — anagrafica aeromobile da ICAO24 hex. No key."""
    q = (query or "").strip().lower().replace(" ", "")
    if not re.fullmatch(r"[0-9a-f]{6}", q):
        return {"error": "expect_icao24_hex", "hint": "6 hex (es. 3c6444)",
                "source": "opensky"}
    cached = _cache_get("opensky", q)
    if cached:
        return {**cached, "cached": True}
    try:
        r = requests.get(OPENSKY_META_URL.format(hex=q),
                         headers={"user-agent": UA}, timeout=12)
        if r.status_code == 200:
            d = r.json() or {}
            result = {"icao24": q, "registration": d.get("registration"),
                      "manufacturer": d.get("manufacturerName"),
                      "model": d.get("model"), "operator": d.get("operator"),
                      "owner": d.get("owner"), "country": d.get("country"),
                      "built": d.get("built"), "source": "opensky"}
        elif r.status_code == 404:
            result = {"found": False, "icao24": q, "source": "opensky"}
        else:
            result = {"error": f"opensky_status_{r.status_code}", "source": "opensky"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "opensky"}
    _cache_set("opensky", q, result)
    _persist_lookup("Username", q, result)
    return result


# --------------------------------------------------------------------------- #
# Navale — screening nave contro sanzioni (schema Vessel), offline+API
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def lookup_vessel(query: str) -> dict:
    """Screening nave (nome o IMO) contro liste sanzioni — schema Vessel."""
    res = screen_sanctions(query, schema="Vessel")
    res["target"] = "vessel"
    return res


# --------------------------------------------------------------------------- #
# CourtListener — procedimenti giudiziari USA (mirror gratuito di PACER), no key
# --------------------------------------------------------------------------- #
COURTLISTENER_URL = "https://www.courtlistener.com/api/rest/v4/search/"


@frappe.whitelist()
def lookup_courtlistener(query: str) -> dict:
    """CourtListener — ricerca full-text procedimenti federali USA. No key."""
    query = (query or "").strip()
    if not query:
        return {"error": "invalid_query", "source": "courtlistener"}
    cached = _cache_get("courtlistener", query)
    if cached:
        return {**cached, "cached": True}
    try:
        r = requests.get(COURTLISTENER_URL, headers={"user-agent": UA},
                         params={"q": query, "type": "r"}, timeout=12)
        if r.status_code == 200:
            d = r.json() or {}
            hits = [{"case": x.get("caseName"), "court": x.get("court"),
                     "date": x.get("dateFiled"),
                     "url": "https://www.courtlistener.com" + (x.get("absolute_url") or "")}
                    for x in (d.get("results") or [])[:10]]
            result = {"found": bool(hits), "count": d.get("count", len(hits)),
                      "cases": hits, "source": "courtlistener"}
        else:
            result = {"error": f"courtlistener_status_{r.status_code}",
                      "source": "courtlistener"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "courtlistener"}
    _cache_set("courtlistener", query, result)
    _persist_lookup("Company", query, result)
    return result


# --------------------------------------------------------------------------- #
# CommonCrawl — URL indicizzati di un dominio (index API), no key
# --------------------------------------------------------------------------- #
COMMONCRAWL_INDEX = "https://index.commoncrawl.org/CC-MAIN-2024-51-index"


@frappe.whitelist()
def lookup_commoncrawl(domain: str) -> dict:
    """CommonCrawl — URL pubblici indicizzati per il dominio. No key."""
    d = _norm_host(domain)
    if not d:
        return {"error": "invalid_domain", "source": "commoncrawl"}
    cached = _cache_get("commoncrawl", d)
    if cached:
        return {**cached, "cached": True}
    try:
        r = requests.get(COMMONCRAWL_INDEX, headers={"user-agent": UA},
                         params={"url": f"*.{d}", "output": "json", "limit": 50},
                         timeout=20)
        urls = []
        if r.status_code == 200:
            for line in r.text.splitlines():
                try:
                    urls.append(json.loads(line).get("url"))
                except Exception:
                    continue
        result = {"found": bool(urls), "count": len(urls),
                  "sample_urls": [u for u in urls if u][:25], "source": "commoncrawl"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "commoncrawl"}
    _cache_set("commoncrawl", d, result)
    return result


# --------------------------------------------------------------------------- #
# Wikidata — entità (azienda/persona) da nome, no key
# --------------------------------------------------------------------------- #
WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"


@frappe.whitelist()
def lookup_wikidata(query: str) -> dict:
    """Wikidata — entità collegate al nome (id, descrizione). No key."""
    query = (query or "").strip()
    if not query:
        return {"error": "invalid_query", "source": "wikidata"}
    cached = _cache_get("wikidata", query)
    if cached:
        return {**cached, "cached": True}
    try:
        r = requests.get(WIKIDATA_SEARCH, headers={"user-agent": UA}, params={
            "action": "wbsearchentities", "search": query, "language": "en",
            "format": "json", "limit": 7}, timeout=12)
        ents = [{"id": e.get("id"), "label": e.get("label"),
                 "description": e.get("description"),
                 "url": e.get("concepturi")}
                for e in ((r.json() or {}).get("search") or [])]
        result = {"found": bool(ents), "entities": ents, "source": "wikidata"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "wikidata"}
    _cache_set("wikidata", query, result)
    return result


def _norm_host(value: str) -> str:
    v = (value or "").strip().lower()
    if "://" in v:
        from urllib.parse import urlparse
        v = urlparse(v).hostname or v
    v = v.split("/")[0].strip(".")
    return v if "." in v else ""

