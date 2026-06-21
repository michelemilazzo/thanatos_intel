"""Analytics portale Thanatos: log ricerche, statistiche visite, gestione SEO keyword."""
import re
from collections import Counter

import frappe

_CACHE_KEY = "thanatos_seo_keywords"


def _is_staff(user=None):
    roles = set(frappe.get_roles(user or frappe.session.user))
    return bool(roles & {"System Manager", "Investigation Manager", "Investigator"})


# ---------------- log ricerche ----------------

@frappe.whitelist(allow_guest=True)
def log_search(query, kind="Site", results=0):
    try:
        q = (query or "").strip()
        if not q or len(q) > 200:
            return
        vid = None
        path = None
        try:
            vid = frappe.request.cookies.get("visitor_id")
            path = frappe.request.path
        except Exception:
            pass
        frappe.get_doc({
            "doctype": "Search Log", "query": q[:200], "kind": kind,
            "results_count": int(results or 0),
            "visitor_id": vid,
            "user": (frappe.session.user if frappe.session.user != "Guest" else None),
            "ref_path": path,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "log_search failed")


# ---------------- SEO keyword ----------------

def seo_keywords():
    """Lista keyword attive (cache) — usata da seo_head per la meta keywords."""
    v = frappe.cache().get_value(_CACHE_KEY)
    if v is None:
        try:
            v = frappe.get_all("SEO Keyword", filters={"is_active": 1},
                               fields=["keyword"], order_by="weight desc", limit=40, pluck="keyword")
        except Exception:
            v = []
        frappe.cache().set_value(_CACHE_KEY, v)
    return v


def _bust():
    frappe.cache().delete_value(_CACHE_KEY)


@frappe.whitelist()
def add_keyword(keyword):
    if not _is_staff():
        frappe.throw("Non autorizzato")
    k = (keyword or "").strip()
    if not k:
        frappe.throw("Keyword vuota")
    if frappe.db.exists("SEO Keyword", {"keyword": k}):
        return {"ok": True, "exists": True}
    frappe.get_doc({"doctype": "SEO Keyword", "keyword": k[:140], "origin": "Manual", "is_active": 1}).insert(ignore_permissions=True)
    frappe.db.commit(); _bust()
    return {"ok": True}


@frappe.whitelist()
def toggle_keyword(name, active):
    if not _is_staff():
        frappe.throw("Non autorizzato")
    frappe.db.set_value("SEO Keyword", name, "is_active", 1 if int(active) else 0)
    frappe.db.commit(); _bust()
    return {"ok": True}


@frappe.whitelist()
def delete_keyword(name):
    if not _is_staff():
        frappe.throw("Non autorizzato")
    frappe.delete_doc("SEO Keyword", name, ignore_permissions=True)
    frappe.db.commit(); _bust()
    return {"ok": True}


_STOP = set("""a ad al alla alle allo agli ai con che chi cui da del dei della delle dello degli di e ed è era ce gli ha hai
hanno il in la le lo ma mi ne nei nel nella nelle non o per più piu su sua sue sui suo tra un una uno come dove quando
the and for with that this from are was has have you your our not all can but its into has had who what when where why how
news new più di-cui circa anche sono solo dopo prima oggi dal nuovo nuova essere fare stato stati""".split())


@frappe.whitelist()
def extract_from_news(limit=120, top=30):
    """Estrae keyword frequenti dai titoli/excerpt delle news pubblicate (tematiche)."""
    if not _is_staff():
        frappe.throw("Non autorizzato")
    arts = frappe.get_all("News Article",
                          filters={"published": 1, "category": ["!=", "generale-cronaca"]},
                          fields=["title", "excerpt"], order_by="published_at desc", limit=int(limit))
    cnt = Counter()
    for a in arts:
        text = ((a.title or "") + " " + (a.excerpt or "")).lower()
        for w in re.findall(r"[a-zàèéìòùA-Z0-9]{4,}", text):
            if w in _STOP or w.isdigit():
                continue
            cnt[w] += 1
    existing = set(k.lower() for k in frappe.get_all("SEO Keyword", pluck="keyword"))
    created = 0
    for word, c in cnt.most_common(int(top) * 3):
        if created >= int(top):
            break
        if c < 2 or word in existing:
            continue
        try:
            frappe.get_doc({"doctype": "SEO Keyword", "keyword": word, "origin": "News",
                            "is_active": 1, "weight": c}).insert(ignore_permissions=True)
            existing.add(word); created += 1
        except Exception:
            pass
    frappe.db.commit(); _bust()
    return {"ok": True, "created": created}


# ---------------- statistiche visite ----------------

def portal_stats(days=30):
    def sql(q, *a):
        try:
            return frappe.db.sql(q, a, as_dict=True)
        except Exception:
            return []

    def scalar(q, *a):
        r = sql(q, *a)
        return (list(r[0].values())[0] if r else 0) or 0

    wpv = "`tabWeb Page View`"
    since = "and creation >= date_sub(curdate(), interval %s day)" % int(days)
    out = {}
    out["views"] = scalar("select count(*) c from " + wpv + " where 1=1 " + since)
    out["visitors"] = scalar("select count(distinct visitor_id) c from " + wpv + " where ifnull(visitor_id,'')!='' " + since)
    out["views_today"] = scalar("select count(*) c from " + wpv + " where date(creation)=curdate()")
    out["unique_views"] = scalar("select count(*) c from " + wpv + " where is_unique='1' " + since)
    out["by_day"] = sql("select date(creation) d, count(*) c from " + wpv + " where 1=1 " + since + " group by date(creation) order by d")
    out["top_pages"] = sql("select path, count(*) c from " + wpv + " where 1=1 " + since + " group by path order by c desc limit 12")
    out["referrers"] = sql("select referrer, count(*) c from " + wpv + " where ifnull(referrer,'')!='' " + since + " group by referrer order by c desc limit 10")
    out["sources"] = sql("select coalesce(nullif(source,''),'(diretto)') s, count(*) c from " + wpv + " where 1=1 " + since + " group by s order by c desc limit 10")
    out["geo"] = sql("select coalesce(nullif(time_zone,''),'(n/d)') tz, count(distinct visitor_id) c from " + wpv + " where 1=1 " + since + " group by tz order by c desc limit 12")
    out["browsers"] = sql("select coalesce(nullif(browser,''),'(n/d)') b, count(*) c from " + wpv + " where 1=1 " + since + " group by b order by c desc limit 8")
    sl = "`tabSearch Log`"
    out["searches"] = sql("select query, kind, count(*) c from " + sl + " where 1=1 " + since + " group by query, kind order by c desc limit 25")
    out["searches_total"] = scalar("select count(*) c from " + sl + " where 1=1 " + since)
    return out
