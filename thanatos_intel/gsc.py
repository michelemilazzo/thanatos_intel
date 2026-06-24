"""Google Search Console — posizioni reali nei risultati di ricerca.

Usa il service account condiviso della flotta: /home/frappe/.secrets/search_console.json
(stesso della console admin, modulo admin/backend/search_console.py con auto-provisioning).
Property auto-rilevata dalla lista siti del service account (o forzata via vault
google_search_console.default_property). Se thanatos non risulta tra le proprietà del
service account, serve il provisioning (admin search_console.provision_property) o aggiungere
l'email del service account come utente della proprietà in Search Console.
"""
import datetime
import json
import os
import urllib.parse

import frappe

SCOPE = ["https://www.googleapis.com/auth/webmasters.readonly"]
KEY_FILE = "/home/frappe/.secrets/search_console.json"
VAULT = "/home/frappe/.secrets/integrations.json"


def _vault_gsc():
    try:
        return json.load(open(VAULT))["google_search_console"]["fields"]
    except Exception:
        return {}


def _creds():
    from google.oauth2 import service_account
    if os.path.exists(KEY_FILE):
        return service_account.Credentials.from_service_account_file(KEY_FILE, scopes=SCOPE)
    sa = (_vault_gsc().get("service_account_json") or {}).get("value")
    if sa:
        return service_account.Credentials.from_service_account_info(
            json.loads(sa) if isinstance(sa, str) else sa, scopes=SCOPE)
    return None


def _token(creds):
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    return creds.token


def _list_sites(token):
    import requests
    r = requests.get("https://searchconsole.googleapis.com/webmasters/v3/sites",
                     headers={"Authorization": "Bearer " + token}, timeout=30)
    if r.status_code >= 400:
        return []
    return r.json().get("siteEntry", [])


def _detect_property(token):
    explicit = (_vault_gsc().get("default_property") or {}).get("value")
    if explicit:
        return explicit
    cands = [s.get("siteUrl") for s in _list_sites(token) if "thanatos.agency" in (s.get("siteUrl") or "").lower()]
    if not cands:
        return None
    cands.sort(key=lambda u: 0 if u.startswith("sc-domain:") else 1)
    return cands[0]


def gsc_status():
    has_key = os.path.exists(KEY_FILE) or bool((_vault_gsc().get("service_account_json") or {}).get("value"))
    prop = None
    if has_key:
        try:
            prop = _detect_property(_token(_creds()))
        except Exception:
            prop = None
    return {"configured": bool(has_key), "connected": bool(prop), "property": prop or "sc-domain:thanatos.agency"}


@frappe.whitelist()
def fetch_rankings(days=28, row_limit=250):
    creds = _creds()
    if not creds:
        return {"ok": False, "reason": "Service account GSC non trovato"}
    import requests
    try:
        token = _token(creds)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "gsc token")
        return {"ok": False, "reason": "Credenziali non valide: " + str(e)[:120]}
    prop = _detect_property(token)
    if not prop:
        return {"ok": False, "reason": "thanatos.agency non e' tra le proprieta' del service account (serve provisioning)"}
    end = frappe.utils.getdate() - datetime.timedelta(days=3)  # lag dati GSC
    start = end - datetime.timedelta(days=int(days))
    body = {"startDate": str(start), "endDate": str(end), "dimensions": ["query"], "rowLimit": int(row_limit),
            "orderBy": [{"fieldName": "impressions", "sortOrder": "DESCENDING"}]}
    url = "https://searchconsole.googleapis.com/webmasters/v3/sites/%s/searchAnalytics/query" % urllib.parse.quote(prop, safe="")
    r = requests.post(url, headers={"Authorization": "Bearer " + token}, json=body, timeout=40)
    if r.status_code >= 400:
        frappe.log_error(r.text[:800], "gsc fetch")
        return {"ok": False, "reason": "API %s: %s" % (r.status_code, r.text[:160])}
    rows = r.json().get("rows", [])
    today = str(end)
    n = 0
    existing_kw = set(k.lower() for k in frappe.get_all("SEO Keyword", pluck="keyword"))
    for row in rows:
        q = (row.get("keys") or [""])[0][:140]
        if not q:
            continue
        data = {
            "query": q, "property": prop, "capture_date": today,
            "position": round(float(row.get("position") or 0), 1),
            "impressions": int(row.get("impressions") or 0),
            "clicks": int(row.get("clicks") or 0),
            "ctr": round(float(row.get("ctr") or 0) * 100, 2),
        }
        try:
            name = frappe.db.get_value("Keyword Ranking", {"query": q, "capture_date": today}, "name")
            if name:
                frappe.db.set_value("Keyword Ranking", name, data, update_modified=False)
            else:
                frappe.get_doc(dict(doctype="Keyword Ranking", **data)).insert(ignore_permissions=True)
        except Exception:
            continue
        if data["impressions"] >= 10 and q.lower() not in existing_kw:
            try:
                frappe.get_doc({"doctype": "SEO Keyword", "keyword": q[:140], "origin": "GSC",
                                "is_active": 1, "weight": data["impressions"]}).insert(ignore_permissions=True)
                existing_kw.add(q.lower())
            except Exception:
                pass
        n += 1
    frappe.db.commit()
    try:
        frappe.cache().delete_value("thanatos_seo_keywords")
    except Exception:
        pass
    return {"ok": True, "rows": n, "property": prop}


def latest_rankings(limit=25):
    last = frappe.db.sql("select max(capture_date) c from `tabKeyword Ranking`")
    last = last[0][0] if last else None
    if not last:
        return []
    return frappe.get_all("Keyword Ranking", filters={"capture_date": last},
                          fields=["query", "position", "impressions", "clicks", "ctr"],
                          order_by="impressions desc", limit=int(limit))


def ranking_summary():
    last = frappe.db.sql("select max(capture_date) c from `tabKeyword Ranking`")
    last = last[0][0] if last else None
    if not last:
        return {"date": None, "queries": 0, "avg_position": 0, "clicks": 0, "impressions": 0, "top10": 0}
    r = frappe.db.sql("""select count(*) q, avg(position) p, sum(clicks) c, sum(impressions) i,
        sum(case when position<=10 then 1 else 0 end) t10
        from `tabKeyword Ranking` where capture_date=%s""", (last,), as_dict=True)[0]
    return {"date": str(last), "queries": r.q or 0, "avg_position": round(r.p or 0, 1),
            "clicks": r.c or 0, "impressions": r.i or 0, "top10": r.t10 or 0}
