import json
import urllib.request
from urllib.parse import urlparse

import frappe
from frappe.utils import add_days, today


def _is_staff_seo():
	try:
		from thanatos_intel.analytics import _is_staff
		return _is_staff()
	except Exception:
		return "System Manager" in frappe.get_roles()


# timezone (browser) -> paese, per la geo del traffico reale
_TZ_COUNTRY = {
	"Europe/Rome": "Italia", "Europe/Vatican": "Italia",
	"Europe/Tallinn": "Estonia", "Europe/Bucharest": "Romania",
	"Europe/Paris": "Francia", "Europe/Berlin": "Germania",
	"Europe/Madrid": "Spagna", "Europe/London": "Regno Unito",
	"Europe/Zurich": "Svizzera", "Europe/Amsterdam": "Paesi Bassi",
	"Europe/Brussels": "Belgio", "Europe/Vienna": "Austria",
	"Europe/Lisbon": "Portogallo", "Europe/Athens": "Grecia",
	"Europe/Warsaw": "Polonia", "Europe/Moscow": "Russia",
	"Europe/Istanbul": "Turchia", "Europe/Kiev": "Ucraina",
	"America/Los_Angeles": "USA", "America/New_York": "USA",
	"America/Chicago": "USA", "America/Denver": "USA",
	"America/Sao_Paulo": "Brasile", "America/Toronto": "Canada",
	"Africa/Freetown": "Sierra Leone", "Africa/Lagos": "Nigeria",
	"Africa/Cairo": "Egitto", "Africa/Casablanca": "Marocco",
	"Asia/Dubai": "Emirati", "Asia/Shanghai": "Cina",
	"Asia/Tokyo": "Giappone", "Asia/Kolkata": "India",
}


def _tz_to_country(tz):
	if not tz or tz in ("UTC", "Etc/Unknown", "Etc/UTC"):
		return "(n/d)"
	if tz in _TZ_COUNTRY:
		return _TZ_COUNTRY[tz]
	return tz.split("/")[-1].replace("_", " ")


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


def internal_traffic(days=30):
	"""Traffico reale dalla tabella interna Web Page View (server-side, accurato).
	A differenza di Cloudflare RUM (campionato e geo-IP) conta ogni page view e ricava
	il paese dal fuso del browser, quindi mostra l'Italia."""
	if not frappe.db.exists("DocType", "Web Page View"):
		return {"configured": False}
	wpv = "`tabWeb Page View`"
	since = "and creation >= date_sub(curdate(), interval %s day)" % int(days)

	def sql(q):
		try:
			return frappe.db.sql(q, as_dict=True)
		except Exception:
			return []

	def scalar(q):
		r = sql(q)
		return (list(r[0].values())[0] if r else 0) or 0

	total = scalar("select count(*) c from " + wpv + " where 1=1 " + since)
	visitors = scalar("select count(distinct visitor_id) c from " + wpv + " where ifnull(visitor_id,'')!='' " + since)
	by_date = [{"label": str(r.d), "count": r.c}
	           for r in sql("select date(creation) d, count(*) c from " + wpv + " where 1=1 " + since + " group by date(creation) order by d")]
	top_pages = [{"label": (r.path or "/"), "count": r.c}
	             for r in sql("select path, count(*) c from " + wpv + " where 1=1 " + since + " group by path order by c desc limit 12")]
	conf = frappe.get_site_config()
	def _host(v):
		if not v:
			return ""
		return (urlparse(v).netloc or v).replace("www.", "")
	self_bases = {_host(frappe.utils.get_url()), _host(conf.get("host_name")), _host(frappe.local.site)}
	for d in (conf.get("domains") or []):
		self_bases.add(_host(d if isinstance(d, str) else (d or {}).get("domain")))
	self_bases.discard("")
	refs = {}
	for r in sql("select referrer, count(*) c from " + wpv + " where ifnull(referrer,'')!='' " + since + " group by referrer order by c desc limit 60"):
		try:
			h = urlparse(r.referrer).netloc or r.referrer
		except Exception:
			h = r.referrer
		if not h or h.replace("www.", "") in self_bases:
			continue
		refs[h] = refs.get(h, 0) + r.c
	top_referrers = [{"label": k, "count": v} for k, v in sorted(refs.items(), key=lambda x: -x[1])[:10]]
	countries = {}
	for r in sql("select coalesce(nullif(time_zone,''),'') tz, count(distinct visitor_id) c from " + wpv + " where 1=1 " + since + " group by tz"):
		c = _tz_to_country(r.tz)
		countries[c] = countries.get(c, 0) + r.c
	top_countries = [{"label": k, "count": v} for k, v in sorted(countries.items(), key=lambda x: -x[1])[:10]]

	return {
		"configured": True,
		"total": total,
		"visitors": visitors,
		"by_date": by_date,
		"top_pages": top_pages,
		"top_referrers": top_referrers,
		"top_countries": top_countries,
		"days": int(days),
	}


@frappe.whitelist()
def get_dashboard(days=30):
	if not _is_staff_seo():
		frappe.throw("Non autorizzato", frappe.PermissionError)
	days = int(days or 30)
	internal_tr = internal_traffic(days)
	cf = cf_traffic(days)
	if internal_tr.get("configured"):
		traffic = dict(internal_tr)
		traffic["source"] = "internal"
		if cf.get("configured") and not cf.get("error"):
			traffic["cf_total"] = cf.get("total")
	else:
		traffic = cf
		traffic["source"] = "cloudflare"
	out = {"traffic": traffic, "traffic_cf": cf}

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

	gsc = {"configured": False, "connected": False}
	try:
		from thanatos_intel import gsc as _gsc
		gsc = _gsc.gsc_status()
		gsc["summary"] = _gsc.ranking_summary()
		gsc["queries"] = _gsc.latest_rankings(limit=30)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "seo_dashboard gsc")
	out["gsc"] = gsc
	out["gsc_connected"] = bool(gsc.get("connected"))
	return out
