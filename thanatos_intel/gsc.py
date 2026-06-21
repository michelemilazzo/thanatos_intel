"""Google Search Console — posizioni reali nei risultati di ricerca.

Richiede un service account Google con accesso alla proprietà GSC di thanatos.agency.
Credenziali nel vault integrations.json -> google_search_console.fields:
  - service_account_json: il JSON del service account (intero)
  - default_property: es. "sc-domain:thanatos.agency" (o "https://www.thanatos.agency/")
Aggiungere l'email del service account come utente della proprietà in Search Console.
"""
import datetime
import json
import urllib.parse

import frappe

SCOPE = ["https://www.googleapis.com/auth/webmasters.readonly"]
VAULT = "/home/frappe/.secrets/integrations.json"


def _conf():
    try:
        e = json.load(open(VAULT))["google_search_console"]["fields"]
        sa = (e.get("service_account_json") or {}).get("value")
        prop = (e.get("default_property") or {}).get("value") or "sc-domain:thanatos.agency"
        return sa, prop
    except Exception:
        return None, "sc-domain:thanatos.agency"


def gsc_status():
    sa, prop = _conf()
    return {"configured": bool(sa), "property": prop}


def _token(sa):
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    info = json.loads(sa) if isinstance(sa, str) else sa
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPE)
    creds.refresh(Request())
    return creds.token


@frappe.whitelist()
def fetch_rankings(days=28, row_limit=250):
    """Scarica le query con posizione media/impression/clic dalla Search Console e le salva."""
    sa, prop = _conf()
    if not sa:
        return {"ok": False, "reason": "GSC non configurato (manca service_account_json)"}
    import requests
    try:
        token = _token(sa)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "gsc token")
        return {"ok": False, "reason": "Credenziali non valide: " + str(e)[:120]}
    end = frappe.utils.getdate()
    start = end - datetime.timedelta(days=int(days))
    body = {"startDate": str(start), "endDate": str(end), "dimensions": ["query"], "rowLimit": int(row_limit)}
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
        q = (row.get("keys") or [""])[0][:200]
        if not q:
            continue
        data = {
            "query": q, "property": prop, "capture_date": today,
            "position": round(float(row.get("position") or 0), 1),
            "impressions": int(row.get("impressions") or 0),
            "clicks": int(row.get("clicks") or 0),
            "ctr": round(float(row.get("ctr") or 0) * 100, 2),
        }
        name = frappe.db.get_value("Keyword Ranking", {"query": q, "capture_date": today}, "name")
        if name:
            frappe.db.set_value("Keyword Ranking", name, data, update_modified=False)
        else:
            frappe.get_doc(dict(doctype="Keyword Ranking", **data)).insert(ignore_permissions=True)
        # importa come SEO Keyword (origin GSC) le query con buona visibilita'
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
    return {"ok": True, "rows": n}


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
