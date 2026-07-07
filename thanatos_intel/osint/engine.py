"""
OSINT Engine — Thanatos Intel.

Providers integrati:
- HIBP                — breach lookup email
- AbuseIPDB           — IP reputation
- RDAP                — WHOIS replacement (domain/IP), no key
- OpenCorporates      — aziende globali
- SecurityTrails      — DNS history, subdomains
- IPinfo              — IP geoloc + ASN + company
- VirusTotal v3       — file/URL/domain/IP
- urlscan.io          — URL scan submit + result
- Shodan              — host exposure
- Censys              — internet asset search

Site config keys (set via `bench --site X set-config`):
hibp_api_key, abuseipdb_api_key, opencorporates_api_key,
securitytrails_api_key, ipinfo_token, virustotal_api_key,
urlscan_api_key, shodan_api_key, censys_api_id, censys_api_secret
"""
import hashlib
import json
import re
import socket
from datetime import timedelta
from typing import Optional
from urllib.parse import urlparse

import frappe
import requests
from frappe.utils import now_datetime, get_datetime

HIBP_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2/check"
RDAP_DOMAIN_URL = "https://rdap.org/domain/{domain}"
RDAP_IP_URL = "https://rdap.org/ip/{ip}"
OPENCORP_SEARCH_URL = "https://api.opencorporates.com/v0.4/companies/search"
OPENCORP_COMPANY_URL = "https://api.opencorporates.com/v0.4/companies/{jurisdiction}/{company_number}"
SECURITYTRAILS_DOMAIN_URL = "https://api.securitytrails.com/v1/domain/{domain}"
SECURITYTRAILS_SUBDOMAINS_URL = "https://api.securitytrails.com/v1/domain/{domain}/subdomains"
IPINFO_URL = "https://ipinfo.io/{ip}/json"
VT_FILE_URL = "https://www.virustotal.com/api/v3/files/{hash}"
VT_URL_URL = "https://www.virustotal.com/api/v3/urls/{id}"
VT_DOMAIN_URL = "https://www.virustotal.com/api/v3/domains/{domain}"
VT_IP_URL = "https://www.virustotal.com/api/v3/ip_addresses/{ip}"
URLSCAN_SEARCH_URL = "https://urlscan.io/api/v1/search/"
URLSCAN_SCAN_URL = "https://urlscan.io/api/v1/scan/"
SHODAN_HOST_URL = "https://api.shodan.io/shodan/host/{ip}"
CENSYS_HOSTS_URL = "https://search.censys.io/api/v2/hosts/{ip}"
CENSYS_PLATFORM_URL = "https://api.platform.censys.io/v3/global/asset/host/{ip}"

CACHE_TTL_HOURS = 24
UA = "Thanatos-Intel/1.0"


def _cfg(key: str) -> Optional[str]:
    return frappe.conf.get(key)


def _cache_get(provider: str, target: str):
    key = f"osint:{provider}:{target}"
    cached = frappe.cache().get_value(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            return None
    return None


def _cache_set(provider: str, target: str, value: dict):
    key = f"osint:{provider}:{target}"
    frappe.cache().set_value(key, json.dumps(value), expires_in_sec=CACHE_TTL_HOURS * 3600)


@frappe.whitelist()
def lookup_email(email: str) -> dict:
    """HIBP breach check. Returns dict {found, breaches, source, cached}."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"error": "invalid_email"}

    cached = _cache_get("hibp", email)
    if cached:
        return {**cached, "cached": True}

    api_key = _cfg("hibp_api_key")
    if not api_key:
        result = {"found": False, "breaches": [], "source": "hibp",
                  "stub": True, "message": "HIBP API key not configured"}
        _cache_set("hibp", email, result)
        return result

    try:
        r = requests.get(
            HIBP_URL.format(email=email),
            headers={"hibp-api-key": api_key, "user-agent": "Thanatos-Intel/1.0"},
            params={"truncateResponse": "false"},
            timeout=10,
        )
        if r.status_code == 404:
            result = {"found": False, "breaches": [], "source": "hibp"}
        elif r.status_code == 200:
            breaches = r.json() or []
            result = {
                "found": True,
                "breaches": [{"name": b.get("Name"), "date": b.get("BreachDate"),
                              "data_classes": b.get("DataClasses", [])} for b in breaches],
                "source": "hibp",
            }
        else:
            result = {"error": f"hibp_status_{r.status_code}", "source": "hibp"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "hibp"}

    _cache_set("hibp", email, result)
    _persist_lookup("Email", email, result)
    # Auto-promuovi a blacklist se trovato
    if result.get("found"):
        try:
            from thanatos_intel.integrations.blacklist_ingest import upsert_entry
            breaches = result.get("breaches") or []
            reason = f"HIBP: trovato in {len(breaches)} breach(es) - {', '.join(b.get('name','') for b in breaches[:5])}"
            upsert_entry(f"HIBP:{email}", "Email", email, "High", "HIBP", reason,
                         "HaveIBeenPwned", f"https://haveibeenpwned.com/account/{email}")
            frappe.db.commit()
        except Exception:
            pass
    return result


@frappe.whitelist()
def lookup_ip(ip: str) -> dict:
    """AbuseIPDB reputation lookup."""
    ip = (ip or "").strip()
    if not ip:
        return {"error": "invalid_ip"}

    cached = _cache_get("abuseipdb", ip)
    if cached:
        return {**cached, "cached": True}

    api_key = _cfg("abuseipdb_api_key")
    if not api_key:
        result = {"score": None, "source": "abuseipdb", "stub": True,
                  "message": "AbuseIPDB API key not configured"}
        _cache_set("abuseipdb", ip, result)
        return result

    try:
        r = requests.get(
            ABUSEIPDB_URL,
            headers={"Key": api_key, "Accept": "application/json"},
            params={"ipAddress": ip, "maxAgeInDays": 90, "verbose": ""},
            timeout=10,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            result = {
                "score": d.get("abuseConfidenceScore"),
                "country": d.get("countryCode"),
                "usage_type": d.get("usageType"),
                "isp": d.get("isp"),
                "total_reports": d.get("totalReports"),
                "last_reported": d.get("lastReportedAt"),
                "source": "abuseipdb",
            }
        else:
            result = {"error": f"abuseipdb_status_{r.status_code}", "source": "abuseipdb"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "abuseipdb"}

    _cache_set("abuseipdb", ip, result)
    _persist_lookup("IP", ip, result)
    # Auto-promuovi a blacklist se score >= 25
    score = result.get("score") or 0
    if score and score >= 25:
        try:
            from thanatos_intel.integrations.blacklist_ingest import upsert_entry
            risk = "Critical" if score >= 75 else "High"
            reason = f"AbuseIPDB score {score}% - ISP: {result.get('isp','')} - {result.get('total_reports',0)} reports"
            upsert_entry(f"ABUSEIP:{ip}", "IP", ip, risk, "AbuseIPDB", reason,
                         "AbuseIPDB", f"https://www.abuseipdb.com/check/{ip}")
            frappe.db.commit()
        except Exception:
            pass
    return result


@frappe.whitelist()
def lookup_domain(domain: str) -> dict:
    """RDAP domain lookup — no API key required."""
    domain = (domain or "").strip().lower().lstrip("http://").lstrip("https://").split("/")[0]
    if not domain or "." not in domain:
        return {"error": "invalid_domain"}

    cached = _cache_get("rdap_domain", domain)
    if cached:
        return {**cached, "cached": True}

    try:
        r = requests.get(RDAP_DOMAIN_URL.format(domain=domain),
                         headers={"Accept": "application/rdap+json",
                                  "user-agent": "Thanatos-Intel/1.0"},
                         timeout=10)
        if r.status_code == 200:
            d = r.json()
            events = {e.get("eventAction"): e.get("eventDate") for e in (d.get("events") or [])}
            ns = [n.get("ldhName") for n in (d.get("nameservers") or [])]
            entities = []
            for e in (d.get("entities") or []):
                roles = e.get("roles") or []
                entities.append({"handle": e.get("handle"), "roles": roles})
            result = {
                "domain": d.get("ldhName") or domain,
                "registered": events.get("registration"),
                "expires": events.get("expiration"),
                "last_changed": events.get("last changed"),
                "status": d.get("status") or [],
                "nameservers": ns,
                "entities": entities,
                "source": "rdap",
            }
        else:
            result = {"error": f"rdap_status_{r.status_code}", "source": "rdap"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "rdap"}

    _cache_set("rdap_domain", domain, result)
    _persist_lookup("Domain", domain, result)
    return result


@frappe.whitelist()
def resolve_and_check(target: str, deep: int = 0) -> dict:
    """One-shot: rileva tipo e ritorna lookup rilevanti.
    deep=0 quick scan, deep=1 attiva connettori premium (VT/Shodan/Censys/SecurityTrails)."""
    target = (target or "").strip()
    if not target:
        return {"error": "empty"}
    deep = int(deep or 0)

    out = {"target": target}
    kind = _detect_kind(target) if "@" not in target else "email"
    out["type"] = kind

    if kind == "email":
        out["hibp"] = lookup_email(target)
    elif kind == "hash":
        out["virustotal"] = lookup_virustotal(target, kind="hash")
    elif kind == "ip":
        out["abuseipdb"] = lookup_ip(target)
        out["ipinfo"] = lookup_ipinfo(target)
        if deep:
            out["virustotal"] = lookup_virustotal(target, kind="ip")
            out["shodan"] = lookup_shodan(target)
            out["censys"] = lookup_censys(target)
    else:  # domain or url
        domain = _norm_domain(target)
        out["domain"] = domain
        out["rdap"] = lookup_domain(domain)
        out["urlscan"] = lookup_urlscan(domain)
        if deep:
            out["securitytrails"] = lookup_dns_history(domain)
            out["virustotal"] = lookup_virustotal(domain, kind="domain")
        try:
            ip = socket.gethostbyname(domain)
            out["resolved_ip"] = ip
            out["abuseipdb"] = lookup_ip(ip)
            out["ipinfo"] = lookup_ipinfo(ip)
            if deep:
                out["shodan"] = lookup_shodan(ip)
        except Exception:
            pass
    return out


@frappe.whitelist()
def lookup_company(query: str, jurisdiction: str = "") -> dict:
    """OpenCorporates company search/profile."""
    query = (query or "").strip()
    if not query:
        return {"error": "invalid_query"}
    key = f"{query}|{jurisdiction}"
    cached = _cache_get("opencorporates", key)
    if cached:
        return {**cached, "cached": True}
    api_key = _cfg("opencorporates_api_key")
    if not api_key:
        # OpenCorporates ha rimosso il tier free no-key: ogni chiamata API
        # richiede un token. Senza -> stub (nessun 401 rumoroso nel semaforo).
        return {"stub": True, "source": "opencorporates",
                "message": "opencorporates_api_key non configurata"}
    params = {"q": query, "format": "json"}
    if jurisdiction:
        params["jurisdiction_code"] = jurisdiction
    if api_key:
        params["api_token"] = api_key
    try:
        r = requests.get(OPENCORP_SEARCH_URL, params=params,
                         headers={"user-agent": UA}, timeout=15)
        if r.status_code == 200:
            d = r.json().get("results", {})
            companies = []
            for c in (d.get("companies") or [])[:20]:
                co = c.get("company") or {}
                companies.append({
                    "name": co.get("name"),
                    "number": co.get("company_number"),
                    "jurisdiction": co.get("jurisdiction_code"),
                    "incorporation_date": co.get("incorporation_date"),
                    "dissolution_date": co.get("dissolution_date"),
                    "status": co.get("current_status"),
                    "type": co.get("company_type"),
                    "address": co.get("registered_address_in_full"),
                    "opencorporates_url": co.get("opencorporates_url"),
                })
            result = {"query": query, "jurisdiction": jurisdiction,
                      "total": d.get("total_count"), "companies": companies,
                      "source": "opencorporates"}
        else:
            result = {"error": f"opencorporates_status_{r.status_code}",
                      "source": "opencorporates"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "opencorporates"}
    _cache_set("opencorporates", key, result)
    _persist_lookup("Company", query, result)
    return result


@frappe.whitelist()
def lookup_dns_history(domain: str) -> dict:
    """SecurityTrails — historical DNS + subdomains."""
    domain = _norm_domain(domain)
    if not domain:
        return {"error": "invalid_domain"}
    cached = _cache_get("securitytrails", domain)
    if cached:
        return {**cached, "cached": True}
    api_key = _cfg("securitytrails_api_key")
    if not api_key:
        result = {"stub": True, "source": "securitytrails",
                  "message": "SecurityTrails API key not configured"}
        _cache_set("securitytrails", domain, result)
        return result
    try:
        h = {"APIKEY": api_key, "Accept": "application/json", "user-agent": UA}
        r = requests.get(SECURITYTRAILS_DOMAIN_URL.format(domain=domain),
                         headers=h, timeout=15)
        if r.status_code != 200:
            result = {"error": f"securitytrails_status_{r.status_code}",
                      "source": "securitytrails"}
        else:
            d = r.json()
            sub = requests.get(SECURITYTRAILS_SUBDOMAINS_URL.format(domain=domain),
                               headers=h, timeout=15)
            subdomains = (sub.json().get("subdomains") if sub.status_code == 200 else []) or []
            result = {
                "domain": domain,
                "apex": d.get("apex_domain"),
                "current_dns": d.get("current_dns"),
                "alexa_rank": d.get("alexa_rank"),
                "subdomain_count": d.get("subdomain_count"),
                "subdomains": subdomains[:200],
                "source": "securitytrails",
            }
    except Exception as e:
        result = {"error": str(e)[:200], "source": "securitytrails"}
    _cache_set("securitytrails", domain, result)
    _persist_lookup("Domain", domain, result)
    return result


@frappe.whitelist()
def lookup_ipinfo(ip: str) -> dict:
    """IPinfo geoloc + ASN + company."""
    ip = (ip or "").strip()
    if not _is_ip(ip):
        return {"error": "invalid_ip"}
    cached = _cache_get("ipinfo", ip)
    if cached:
        return {**cached, "cached": True}
    token = _cfg("ipinfo_token")
    try:
        params = {"token": token} if token else {}
        r = requests.get(IPINFO_URL.format(ip=ip), params=params,
                         headers={"user-agent": UA}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            result = {
                "ip": d.get("ip"), "hostname": d.get("hostname"),
                "city": d.get("city"), "region": d.get("region"),
                "country": d.get("country"), "loc": d.get("loc"),
                "org": d.get("org"), "asn": (d.get("asn") or {}).get("asn"),
                "company": (d.get("company") or {}).get("name"),
                "privacy": d.get("privacy"), "abuse": d.get("abuse"),
                "source": "ipinfo",
            }
        else:
            result = {"error": f"ipinfo_status_{r.status_code}", "source": "ipinfo"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "ipinfo"}
    _cache_set("ipinfo", ip, result)
    _persist_lookup("IP", ip, result)
    return result


@frappe.whitelist()
def lookup_virustotal(target: str, kind: str = "auto") -> dict:
    """VirusTotal v3 — file hash, url, domain, ip."""
    target = (target or "").strip()
    if not target:
        return {"error": "invalid_target"}
    if kind == "auto":
        kind = _detect_kind(target)
    cached = _cache_get(f"vt_{kind}", target)
    if cached:
        return {**cached, "cached": True}
    api_key = _cfg("virustotal_api_key")
    if not api_key:
        result = {"stub": True, "source": "virustotal", "kind": kind,
                  "message": "VirusTotal API key not configured"}
        _cache_set(f"vt_{kind}", target, result)
        return result
    h = {"x-apikey": api_key, "Accept": "application/json", "user-agent": UA}
    try:
        if kind == "hash":
            url = VT_FILE_URL.format(hash=target)
        elif kind == "url":
            url_id = re.sub(r"=+$", "", _b64(target.encode()).decode().replace("+", "-").replace("/", "_"))
            url = VT_URL_URL.format(id=url_id)
        elif kind == "ip":
            url = VT_IP_URL.format(ip=target)
        else:
            url = VT_DOMAIN_URL.format(domain=_norm_domain(target))
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code == 200:
            attr = (r.json().get("data") or {}).get("attributes") or {}
            stats = attr.get("last_analysis_stats") or {}
            result = {
                "kind": kind, "target": target,
                "malicious": stats.get("malicious", 0),
                "suspicious": stats.get("suspicious", 0),
                "harmless": stats.get("harmless", 0),
                "undetected": stats.get("undetected", 0),
                "reputation": attr.get("reputation"),
                "last_analysis_date": attr.get("last_analysis_date"),
                "tags": attr.get("tags") or [],
                "meaningful_name": attr.get("meaningful_name"),
                "names": (attr.get("names") or [])[:10],
                "source": "virustotal",
            }
        elif r.status_code == 404:
            result = {"kind": kind, "target": target, "not_found": True, "source": "virustotal"}
        else:
            result = {"error": f"virustotal_status_{r.status_code}", "source": "virustotal"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "virustotal"}
    _cache_set(f"vt_{kind}", target, result)
    _persist_lookup(kind.capitalize() if kind != "hash" else "Hash", target, result)
    return result


@frappe.whitelist()
def lookup_urlscan(target: str) -> dict:
    """urlscan.io — cerca scansioni esistenti del dominio/URL."""
    target = (target or "").strip()
    if not target:
        return {"error": "invalid_target"}
    domain = _norm_domain(target)
    cached = _cache_get("urlscan", domain)
    if cached:
        return {**cached, "cached": True}
    try:
        r = requests.get(URLSCAN_SEARCH_URL,
                         params={"q": f"domain:{domain}", "size": 10},
                         headers={"user-agent": UA}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            results = []
            for s in (d.get("results") or [])[:10]:
                task = s.get("task") or {}
                page = s.get("page") or {}
                verdicts = s.get("verdicts", {}).get("overall", {})
                results.append({
                    "url": task.get("url"),
                    "scan_time": task.get("time"),
                    "screenshot": s.get("screenshot"),
                    "result_url": s.get("result"),
                    "ip": page.get("ip"),
                    "country": page.get("country"),
                    "asn_name": page.get("asnname"),
                    "malicious": verdicts.get("malicious"),
                    "score": verdicts.get("score"),
                })
            result = {"domain": domain, "total": d.get("total"),
                      "scans": results, "source": "urlscan"}
        else:
            result = {"error": f"urlscan_status_{r.status_code}", "source": "urlscan"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "urlscan"}
    _cache_set("urlscan", domain, result)
    _persist_lookup("Domain", domain, result)
    return result


@frappe.whitelist()
def submit_urlscan(url: str, visibility: str = "unlisted") -> dict:
    """urlscan.io — submit nuova scansione (richiede API key)."""
    api_key = _cfg("urlscan_api_key")
    if not api_key:
        return {"stub": True, "source": "urlscan",
                "message": "urlscan API key not configured"}
    try:
        r = requests.post(URLSCAN_SCAN_URL,
                          json={"url": url, "visibility": visibility},
                          headers={"API-Key": api_key, "Content-Type": "application/json",
                                   "user-agent": UA}, timeout=20)
        if r.status_code in (200, 201):
            d = r.json()
            return {"submitted": True, "uuid": d.get("uuid"),
                    "result_url": d.get("result"), "api_url": d.get("api"),
                    "source": "urlscan"}
        return {"error": f"urlscan_submit_{r.status_code}", "source": "urlscan",
                "body": r.text[:300]}
    except Exception as e:
        return {"error": str(e)[:200], "source": "urlscan"}


@frappe.whitelist()
def lookup_shodan(ip: str) -> dict:
    """Shodan host info."""
    ip = (ip or "").strip()
    if not _is_ip(ip):
        return {"error": "invalid_ip"}
    cached = _cache_get("shodan", ip)
    if cached:
        return {**cached, "cached": True}
    api_key = _cfg("shodan_api_key")
    if not api_key:
        result = {"stub": True, "source": "shodan",
                  "message": "Shodan API key not configured"}
        _cache_set("shodan", ip, result)
        return result
    try:
        r = requests.get(SHODAN_HOST_URL.format(ip=ip),
                         params={"key": api_key},
                         headers={"user-agent": UA}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            result = {
                "ip": d.get("ip_str"), "org": d.get("org"),
                "isp": d.get("isp"), "asn": d.get("asn"),
                "country": d.get("country_code"), "city": d.get("city"),
                "hostnames": d.get("hostnames") or [],
                "ports": d.get("ports") or [],
                "vulns": list((d.get("vulns") or {}).keys())[:50] if isinstance(d.get("vulns"), dict) else (d.get("vulns") or []),
                "tags": d.get("tags") or [],
                "last_update": d.get("last_update"),
                "services": [{"port": s.get("port"), "product": s.get("product"),
                              "version": s.get("version"),
                              "transport": s.get("transport")}
                             for s in (d.get("data") or [])[:20]],
                "source": "shodan",
            }
        elif r.status_code == 404:
            result = {"ip": ip, "not_found": True, "source": "shodan"}
        else:
            result = {"error": f"shodan_status_{r.status_code}", "source": "shodan"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "shodan"}
    _cache_set("shodan", ip, result)
    _persist_lookup("IP", ip, result)
    return result


@frappe.whitelist()
def lookup_censys(ip: str) -> dict:
    """Censys hosts/v2 lookup."""
    ip = (ip or "").strip()
    if not _is_ip(ip):
        return {"error": "invalid_ip"}
    cached = _cache_get("censys", ip)
    if cached:
        return {**cached, "cached": True}
    pat = _cfg("censys_pat")
    api_id = _cfg("censys_api_id")
    api_secret = _cfg("censys_api_secret")
    if not pat and not (api_id and api_secret):
        result = {"stub": True, "source": "censys",
                  "message": "Censys credentials not configured"}
        _cache_set("censys", ip, result)
        return result
    try:
        if pat:
            # Platform API v3 (Bearer PAT) — search.censys.io v2 e' deprecato
            r = requests.get(CENSYS_PLATFORM_URL.format(ip=ip),
                             headers={"Authorization": f"Bearer {pat}", "user-agent": UA},
                             timeout=15)
            rd = (r.json().get("result") or {}).get("resource") or {} if r.status_code == 200 else {}
        else:
            r = requests.get(CENSYS_HOSTS_URL.format(ip=ip), auth=(api_id, api_secret),
                             headers={"user-agent": UA}, timeout=15)
            rd = (r.json().get("result") or {}) if r.status_code == 200 else {}
        if r.status_code == 200:
            services = rd.get("services") or []
            result = {
                "ip": rd.get("ip"),
                "last_updated_at": rd.get("last_updated_at"),
                "autonomous_system": (rd.get("autonomous_system") or {}).get("name"),
                "country": (rd.get("location") or {}).get("country"),
                "services": [{"port": sv.get("port"),
                              "service_name": sv.get("service_name") or sv.get("protocol"),
                              "transport_protocol": sv.get("transport_protocol")}
                             for sv in services[:30]],
                "source": "censys",
            }
        elif r.status_code == 404:
            result = {"ip": ip, "not_found": True, "source": "censys"}
        else:
            result = {"error": f"censys_status_{r.status_code}", "source": "censys"}
    except Exception as e:
        result = {"error": str(e)[:200], "source": "censys"}
    _cache_set("censys", ip, result)
    _persist_lookup("IP", ip, result)
    return result


def _norm_domain(value: str) -> str:
    v = (value or "").strip().lower()
    if "://" in v:
        v = urlparse(v).hostname or v
    v = v.split("/")[0].strip(".")
    return v if "." in v else ""


def _detect_kind(value: str) -> str:
    v = value.strip()
    if re.fullmatch(r"[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", v):
        return "hash"
    if v.startswith("http://") or v.startswith("https://"):
        return "url"
    if _is_ip(v):
        return "ip"
    return "domain"


def _b64(b: bytes) -> bytes:
    import base64
    return base64.urlsafe_b64encode(b)


def _is_ip(value: str) -> bool:
    try:
        socket.inet_aton(value)
        return value.count(".") == 3
    except Exception:
        return False


def _persist_lookup(target_type: str, target: str, result: dict):
    try:
        if not frappe.db.exists("DocType", "OSINT Lookup"):
            return
        doc = frappe.get_doc({
            "doctype": "OSINT Lookup",
            "target_type": target_type,
            "target_value": target,
            "source": result.get("source"),
            "is_stub": 1 if result.get("stub") else 0,
            "is_error": 1 if result.get("error") else 0,
            "result_json": json.dumps(result, default=str),
            "performed_at": now_datetime(),
            "performed_by": frappe.session.user,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "OSINT persist failed")


# ─── LOOKUP PERSONA / AZIENDA (fonti gratuite multiple) ──────────────────────

@frappe.whitelist()
def lookup_person(name: str, dob: str = "", nationality: str = "") -> dict:
    """
    Lookup completo su una persona fisica da fonti gratuite:
    - OpenSanctions cache (offline, locale)
    - ICIJ Offshore Leaks (API pubblica)
    - GDELT adverse media (ultimi 90gg)
    - Blacklist interna Thanatos

    Fonte dati: OpenSanctions (opensanctions.org), ICIJ (icij.org), GDELT (gdeltproject.org)
    """
    name = (name or "").strip()
    if not name:
        return {"error": "name_required"}

    from thanatos_intel.integrations.blacklist_ingest import (
        search_icij, search_gdelt_adverse_media
    )
    result = {"name": name, "sources": {}}

    # 1. OpenSanctions cache locale
    try:
        from thanatos_intel.thanatos_ddd.opensanctions_sync import lookup as os_lookup
        os_res = os_lookup(name, dob, nationality)
        result["sources"]["opensanctions"] = {
            "matches": os_res.get("matches", [])[:5],
            "total": os_res.get("total", 0),
            "source_name": "OpenSanctions",
            "source_url": "https://www.opensanctions.org",
        }
    except Exception as e:
        result["sources"]["opensanctions"] = {"error": str(e)}

    # 2. ICIJ Offshore Leaks
    try:
        icij = search_icij(name)
        result["sources"]["icij"] = icij
    except Exception as e:
        result["sources"]["icij"] = {"error": str(e)}

    # 3. GDELT adverse media
    try:
        gdelt = search_gdelt_adverse_media(name)
        result["sources"]["gdelt"] = gdelt
    except Exception as e:
        result["sources"]["gdelt"] = {"error": str(e)}

    # 4. Blacklist interna
    bl = frappe.get_all("Blacklist Entry",
                        filters={"entry_value": name, "entry_type": "Person", "is_active": 1},
                        fields=["name", "risk_level", "source", "source_url", "reason", "source_dataset"])
    result["sources"]["internal_blacklist"] = {
        "matches": bl,
        "source_name": "Thanatos Blacklist",
        "source_url": "/app/blacklist-entry",
    }

    result["risk_summary"] = _person_risk_summary(result["sources"])
    _persist_lookup("Person", name, result)
    return result


@frappe.whitelist()
def lookup_company_full(name: str, country: str = "") -> dict:
    """
    Lookup completo su un'azienda da fonti gratuite:
    - OpenCorporates (registri societari globali)
    - GLEIF LEI Registry (identificativi legali)
    - ICIJ Offshore Leaks (strutture offshore)
    - GDELT adverse media
    - Blacklist interna Thanatos

    Fonte dati: OpenCorporates (opencorporates.com), GLEIF (gleif.org),
                ICIJ (icij.org), GDELT (gdeltproject.org)
    """
    name = (name or "").strip()
    if not name:
        return {"error": "name_required"}

    from thanatos_intel.integrations.blacklist_ingest import (
        search_icij, search_gdelt_adverse_media, search_gleif
    )
    result = {"name": name, "country": country, "sources": {}}

    # 1. OpenCorporates
    try:
        oc_result = lookup_company(name, country)
        result["sources"]["opencorporates"] = oc_result
    except Exception as e:
        result["sources"]["opencorporates"] = {"error": str(e)}

    # 2. GLEIF
    try:
        gleif = search_gleif(name)
        result["sources"]["gleif"] = gleif
    except Exception as e:
        result["sources"]["gleif"] = {"error": str(e)}

    # 3. ICIJ Offshore Leaks
    try:
        icij = search_icij(name)
        result["sources"]["icij"] = icij
    except Exception as e:
        result["sources"]["icij"] = {"error": str(e)}

    # 4. GDELT adverse media
    try:
        gdelt = search_gdelt_adverse_media(name)
        result["sources"]["gdelt"] = gdelt
    except Exception as e:
        result["sources"]["gdelt"] = {"error": str(e)}

    # 5. Blacklist interna
    bl = frappe.get_all("Blacklist Entry",
                        filters={"entry_value": name, "entry_type": "Company", "is_active": 1},
                        fields=["name", "risk_level", "source", "source_url", "reason", "source_dataset"])
    result["sources"]["internal_blacklist"] = {
        "matches": bl,
        "source_name": "Thanatos Blacklist",
        "source_url": "/app/blacklist-entry",
    }

    result["risk_summary"] = _company_risk_summary(result["sources"])
    _persist_lookup("Company", name, result)
    return result


def _person_risk_summary(sources: dict) -> dict:
    flags = []
    risk = "Clear"
    os_hits = (sources.get("opensanctions") or {}).get("total", 0)
    if os_hits:
        flags.append(f"OpenSanctions: {os_hits} corrispondenza/e")
        risk = "Critical"
    icij_hits = len((sources.get("icij") or {}).get("results", []))
    if icij_hits:
        flags.append(f"ICIJ Offshore Leaks: {icij_hits} risultato/i")
        risk = max(risk, "High") if risk != "Critical" else risk
    gdelt_count = len((sources.get("gdelt") or {}).get("articles", []))
    if gdelt_count:
        flags.append(f"GDELT: {gdelt_count} articolo/i avverso/i")
        risk = max(risk, "Medium") if risk not in ("Critical", "High") else risk
    bl_hits = len((sources.get("internal_blacklist") or {}).get("matches", []))
    if bl_hits:
        flags.append(f"Blacklist interna: {bl_hits} voce/i")
        risk = "Critical"
    return {"risk": risk, "flags": flags}


def _company_risk_summary(sources: dict) -> dict:
    flags = []
    risk = "Clear"
    icij_hits = len((sources.get("icij") or {}).get("results", []))
    if icij_hits:
        flags.append(f"ICIJ Offshore Leaks: {icij_hits} risultato/i")
        risk = "High"
    gdelt_count = len((sources.get("gdelt") or {}).get("articles", []))
    if gdelt_count:
        flags.append(f"GDELT: {gdelt_count} articolo/i avverso/i")
        risk = max(risk, "Medium") if risk not in ("Critical", "High") else risk
    bl_hits = len((sources.get("internal_blacklist") or {}).get("matches", []))
    if bl_hits:
        flags.append(f"Blacklist interna: {bl_hits} voce/i")
        risk = "Critical"
    gleif = sources.get("gleif") or {}
    for r in (gleif.get("results") or []):
        if r.get("status") not in ("ACTIVE", ""):
            flags.append(f"GLEIF status: {r.get('status')} - LEI {r.get('lei','')}")
    return {"risk": risk, "flags": flags}
