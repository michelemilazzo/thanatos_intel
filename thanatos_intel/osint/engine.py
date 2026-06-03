"""
OSINT Engine — Thanatos Intel.

Providers:
- HIBP (Have I Been Pwned): breach lookup per email
- AbuseIPDB: reputation IP
- RDAP (registry): WHOIS replacement per dominio/IP, NESSUNA chiave richiesta

Le chiavi API si configurano in site_config.json:
- hibp_api_key
- abuseipdb_api_key

Tutti i lookup sono salvati come OSINT Lookup DocType con cache TTL configurabile.
Hit caching in cache redis per ridurre cost API.
"""
import json
import socket
from datetime import timedelta
from typing import Optional

import frappe
import requests
from frappe.utils import now_datetime, get_datetime

HIBP_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2/check"
RDAP_DOMAIN_URL = "https://rdap.org/domain/{domain}"
RDAP_IP_URL = "https://rdap.org/ip/{ip}"

CACHE_TTL_HOURS = 24


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
def resolve_and_check(target: str) -> dict:
    """One-shot: rileva tipo (email/ip/domain) e ritorna tutti i lookup rilevanti."""
    target = (target or "").strip()
    if not target:
        return {"error": "empty"}

    out = {"target": target}
    if "@" in target:
        out["type"] = "email"
        out["hibp"] = lookup_email(target)
    elif _is_ip(target):
        out["type"] = "ip"
        out["abuseipdb"] = lookup_ip(target)
    else:
        out["type"] = "domain"
        out["rdap"] = lookup_domain(target)
        try:
            ip = socket.gethostbyname(target)
            out["resolved_ip"] = ip
            out["abuseipdb"] = lookup_ip(ip)
        except Exception:
            pass
    return out


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
