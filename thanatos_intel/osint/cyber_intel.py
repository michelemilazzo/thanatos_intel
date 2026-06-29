"""Connettori Cyber/IP (free+key): VirusTotal, AbuseIPDB, Shodan, IPinfo, urlscan.

Ogni connettore legge la sua key da site_config; senza key ritorna uno stub con
il link di registrazione (gratis). Target: IP / dominio / URL.
Chiavi: virustotal_api_key · abuseipdb_api_key · shodan_api_key · ipinfo_api_key · urlscan_api_key
"""
import re
import frappe
from frappe.utils import now_datetime

REGISTRA = {
    "virustotal": "https://www.virustotal.com/gui/join-us",
    "abuseipdb": "https://www.abuseipdb.com/register",
    "shodan": "https://account.shodan.io/register",
    "ipinfo": "https://ipinfo.io/signup",
    "urlscan": "https://urlscan.io/user/signup",
}


def _key(name):
    return frappe.conf.get(f"{name}_api_key")


def _stub(name):
    return {"stub": True, "fonte": name,
            "message": f"{name}_api_key mancante. Registrati gratis: {REGISTRA.get(name)}"}


def _is_ip(s):
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", (s or "").strip()))


def _evidence(case, title, lines, source):
    if not case:
        return None
    try:
        ev = frappe.get_doc({
            "doctype": "Investigation Evidence", "investigation_case": case,
            "evidence_name": title[:140], "evidence_type": "Document", "source": source,
            "acquisition_date": now_datetime(), "custody_status": "Received",
            "notes": "\n".join(str(x) for x in lines if x)[:1000]})
        ev.flags.ignore_mandatory = True
        ev.insert(ignore_permissions=True)
        frappe.db.commit()
        return ev.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "cyber_intel evidence")
        return None


@frappe.whitelist()
def virustotal(target, investigation_case=None):
    """Reputazione di IP / dominio / URL / hash su VirusTotal (v3)."""
    k = _key("virustotal")
    if not k:
        return _stub("virustotal")
    import requests, base64
    t = (target or "").strip()
    if _is_ip(t):
        path = f"/ip_addresses/{t}"
    elif t.startswith("http"):
        path = "/urls/" + base64.urlsafe_b64encode(t.encode()).decode().strip("=")
    elif re.match(r"^[a-fA-F0-9]{32,64}$", t):
        path = f"/files/{t}"
    else:
        path = f"/domains/{t}"
    try:
        r = requests.get(f"https://www.virustotal.com/api/v3{path}", headers={"x-apikey": k}, timeout=30)
        if r.status_code != 200:
            return {"error": f"virustotal HTTP {r.status_code}", "target": t}
        a = ((r.json() or {}).get("data") or {}).get("attributes") or {}
    except Exception as e:
        return {"error": str(e)[:160], "target": t}
    st = a.get("last_analysis_stats") or {}
    out = {"target": t, "malicious": st.get("malicious", 0), "suspicious": st.get("suspicious", 0),
           "harmless": st.get("harmless", 0), "reputation": a.get("reputation"),
           "country": a.get("country"), "as_owner": a.get("as_owner")}
    lines = [f"VirusTotal — {t}", f"Malicious: {out['malicious']} · Suspicious: {out['suspicious']} · "
             f"Harmless: {out['harmless']} · Reputation: {out['reputation']}",
             f"AS owner: {out['as_owner'] or '-'} · Paese: {out['country'] or '-'}"]
    out["evidence"] = _evidence(investigation_case, f"VirusTotal — {t}", lines, "VirusTotal")
    return out


@frappe.whitelist()
def abuseipdb(ip, investigation_case=None):
    """Reputazione abuse di un IP (AbuseIPDB)."""
    k = _key("abuseipdb")
    if not k:
        return _stub("abuseipdb")
    import requests
    try:
        r = requests.get("https://api.abuseipdb.com/api/v2/check",
                         headers={"Key": k, "Accept": "application/json"},
                         params={"ipAddress": ip, "maxAgeInDays": 90}, timeout=30)
        d = ((r.json() or {}).get("data")) or {}
    except Exception as e:
        return {"error": str(e)[:160], "ip": ip}
    out = {"ip": ip, "abuse_score": d.get("abuseConfidenceScore"), "paese": d.get("countryCode"),
           "isp": d.get("isp"), "dominio": d.get("domain"), "tipo_uso": d.get("usageType"),
           "segnalazioni": d.get("totalReports"), "tor": d.get("isTor")}
    lines = [f"AbuseIPDB — {ip}", f"Abuse score: {out['abuse_score']}% · Segnalazioni: {out['segnalazioni']}",
             f"ISP: {out['isp'] or '-'} · Paese: {out['paese'] or '-'} · Uso: {out['tipo_uso'] or '-'}"]
    out["evidence"] = _evidence(investigation_case, f"AbuseIPDB — {ip}", lines, "AbuseIPDB")
    return out


@frappe.whitelist()
def shodan_host(ip, investigation_case=None):
    """Servizi/porte esposti e vulnerabilità di un IP (Shodan)."""
    k = _key("shodan")
    if not k:
        return _stub("shodan")
    import requests
    try:
        r = requests.get(f"https://api.shodan.io/shodan/host/{ip}", params={"key": k}, timeout=30)
        if r.status_code != 200:
            return {"error": f"shodan HTTP {r.status_code}", "ip": ip}
        d = r.json() or {}
    except Exception as e:
        return {"error": str(e)[:160], "ip": ip}
    out = {"ip": ip, "org": d.get("org"), "isp": d.get("isp"), "paese": d.get("country_name"),
           "porte": d.get("ports") or [], "hostnames": d.get("hostnames") or [],
           "vulns": list(d.get("vulns") or [])[:20]}
    lines = [f"Shodan — {ip}", f"Org: {out['org'] or '-'} · Paese: {out['paese'] or '-'}",
             f"Porte: {', '.join(map(str, out['porte'])) or '-'}",
             f"Hostnames: {', '.join(out['hostnames']) or '-'}",
             f"Vulnerabilità: {', '.join(out['vulns']) or 'nessuna nota'}"]
    out["evidence"] = _evidence(investigation_case, f"Shodan — {ip}", lines, "Shodan")
    return out


@frappe.whitelist()
def ipinfo(ip, investigation_case=None):
    """Geolocalizzazione e ASN/owner di un IP (IPinfo)."""
    k = _key("ipinfo")
    if not k:
        return _stub("ipinfo")
    import requests
    try:
        r = requests.get(f"https://ipinfo.io/{ip}", params={"token": k}, timeout=30)
        d = r.json() or {}
    except Exception as e:
        return {"error": str(e)[:160], "ip": ip}
    out = {"ip": ip, "org": d.get("org"), "citta": d.get("city"), "regione": d.get("region"),
           "paese": d.get("country"), "loc": d.get("loc"), "hostname": d.get("hostname")}
    lines = [f"IPinfo — {ip}", f"Org/ASN: {out['org'] or '-'}",
             f"Località: {out['citta'] or '-'}, {out['regione'] or '-'} ({out['paese'] or '-'}) · {out['loc'] or '-'}",
             f"Hostname: {out['hostname'] or '-'}"]
    out["evidence"] = _evidence(investigation_case, f"IPinfo — {ip}", lines, "IPinfo")
    return out


@frappe.whitelist()
def urlscan(target, investigation_case=None):
    """Storico scansioni di un dominio/URL (urlscan.io). La ricerca è gratuita."""
    import requests
    q = (target or "").strip().replace("https://", "").replace("http://", "").split("/")[0]
    headers = {}
    if _key("urlscan"):
        headers["API-Key"] = _key("urlscan")
    try:
        r = requests.get("https://urlscan.io/api/v1/search/", params={"q": f'page.domain:"{q}"'},
                         headers=headers, timeout=30)
        if r.status_code != 200:
            return {"error": f"urlscan HTTP {r.status_code}", "target": q}
        results = ((r.json() or {}).get("results")) or []
    except Exception as e:
        return {"error": str(e)[:160], "target": q}
    out = {"target": q, "scansioni": len(results), "ultime": []}
    for it in results[:8]:
        page = it.get("page") or {}
        out["ultime"].append({"url": page.get("url"), "ip": page.get("ip"),
                              "paese": page.get("country"), "server": page.get("server"),
                              "data": (it.get("task") or {}).get("time")})
    lines = [f"urlscan.io — {q}", f"Scansioni trovate: {out['scansioni']}"]
    lines += [f"• {u['url']} → IP {u['ip']} ({u['paese']}) {u['server'] or ''}" for u in out["ultime"]]
    out["evidence"] = _evidence(investigation_case, f"urlscan — {q}", lines, "urlscan.io")
    return out
