import json
import urllib.request

import frappe
from frappe.utils import add_days, today


def _is_staff_seo():
	try:
		from thanatos_intel.analytics import _is_staff
		return _is_staff()
	except Exception:
		return "System Manager" in frappe.get_roles()


def _cf_graphql(query, variables):
	conf = frappe.get_site_config()
	email = conf.get("cloudflare_email")
	key = conf.get("cloudflare_api_key")
	if not (email and key):
		return None
	body = json.dumps({"query": query, "variables": variables}).encode()
	req = urllib.request.Request(
		"https://api.cloudflare.com/client/v4/graphql", data=body,
		headers={"X-Auth-Email": email, "X-Auth-Key": key, "Content-Type": "application/json"})
	try:
		r = json.load(urllib.request.urlopen(req, timeout=20))
		return r.get("data")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "seo_dashboard cf_graphql")
		return None


def cf_traffic(days=30):
	conf = frappe.get_site_config()
	aid = conf.get("cf_account_id")
	site = conf.get("cf_rum_site_tag")
	if not (aid and site):
		return {"configured": False}
	d_to = today()
	d_from = add_days(d_to, -int(days))
	q = """query($a:string!,$s:string,$f:string,$t:string){viewer{accounts(filter:{accountTag:$a}){
	  total: rumPageloadEventsAdaptiveGroups(limit:1, filter:{siteTag:$s, date_geq:$f, date_leq:$t}){count}
	  byDate: rumPageloadEventsAdaptiveGroups(limit:60, orderBy:[date_ASC], filter:{siteTag:$s, date_geq:$f, date_leq:$t}){count dimensions{date}}
	  topPages: rumPageloadEventsAdaptiveGroups(limit:12, orderBy:[count_DESC], filter:{siteTag:$s, date_geq:$f, date_leq:$t}){count dimensions{requestPath}}
	  topRef: rumPageloadEventsAdaptiveGroups(limit:10, orderBy:[count_DESC], filter:{siteTag:$s, date_geq:$f, date_leq:$t, refererHost_neq:""}){count dimensions{refererHost}}
	  topCountry: rumPageloadEventsAdaptiveGroups(limit:10, orderBy:[count_DESC], filter:{siteTag:$s, date_geq:$f, date_leq:$t}){count dimensions{countryName}}
	}}}"""
	data = _cf_graphql(q, {"a": aid, "s": site, "f": d_from, "t": d_to})
	if not data:
		return {"configured": True, "error": True}
	accs = (data.get("viewer") or {}).get("accounts") or [{}]
	acc = accs[0] if accs else {}

	def rows(key, dim):
		return [{"label": ((g.get("dimensions") or {}).get(dim) or "—"), "count": g.get("count", 0)}
		        for g in (acc.get(key) or [])]

	return {
		"configured": True,
		"total": ((acc.get("total") or [{}])[0]).get("count", 0),
		"by_date": rows("byDate", "date"),
		"top_pages": rows("topPages", "requestPath"),
		"top_referrers": rows("topRef", "refererHost"),
		"top_countries": rows("topCountry", "countryName"),
		"days": int(days),
	}


@frappe.whitelist()
def get_dashboard(days=30):
	if not _is_staff_seo():
		frappe.throw("Non autorizzato", frappe.PermissionError)
	days = int(days or 30)
	out = {"traffic": cf_traffic(days)}

	kws = frappe.get_all("SEO Keyword", filters={"is_active": 1},
	                     fields=["keyword", "origin", "weight"], order_by="weight desc", limit=300)
	by_origin = {}
	for k in kws:
		by_origin[k.origin or "?"] = by_origin.get(k.origin or "?", 0) + 1
	out["keywords"] = {"total": len(kws), "by_origin": by_origin, "top": kws[:40]}

	out["content"] = {
		"articles": frappe.db.count("News Article", {"published": 1}),
		"categories": (frappe.db.count("News Category", {"is_active": 1})
		               if frappe.db.exists("DocType", "News Category") else 0),
	}

	internal = {"page_views": (frappe.db.count("Web Page View")
	                           if frappe.db.exists("DocType", "Web Page View") else 0)}
	try:
		internal["top_searches"] = frappe.db.sql(
			"""select query as label, count(*) as count from `tabSearch Log`
			   where ifnull(query,'')!='' group by query order by count desc limit 10""", as_dict=True)
	except Exception:
		internal["top_searches"] = []
	out["internal"] = internal

	out["gsc_connected"] = bool(frappe.get_site_config().get("gsc_service_account"))
	return out
