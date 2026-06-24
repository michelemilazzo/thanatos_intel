"""Statistiche reali della newsroom: visitatori (Web Page View), articoli, piu letti."""
import frappe


def newsroom_stats(top_n=5):
    def scalar(q):
        try:
            r = frappe.db.sql(q)
            return (r[0][0] if r and r[0] and r[0][0] is not None else 0)
        except Exception:
            return 0

    visitors_total = scalar("select count(distinct visitor_id) from `tabWeb Page View` where ifnull(visitor_id,'')!=''")
    visitors_today = scalar("select count(distinct visitor_id) from `tabWeb Page View` where ifnull(visitor_id,'')!='' and date(creation)=curdate()")
    views_total = scalar("select count(*) from `tabWeb Page View`")
    views_today = scalar("select count(*) from `tabWeb Page View` where date(creation)=curdate()")
    online_since = scalar("select min(creation) from `tabWeb Page View`")
    articles_total = frappe.db.count("News Article", {"published": 1})

    # fallback se visitor_id non popolato: usa le visite (page views)
    if not visitors_total:
        visitors_total = views_total
    if not visitors_today:
        visitors_today = views_today

    GENERAL = "generale-cronaca"

    def _pick(exclude_general=False, only_general=False, limit=5, seen=None):
        seen = seen if seen is not None else set()
        out = []
        try:
            rows = frappe.db.sql(
                """select path, count(*) c from `tabWeb Page View`
                where path like %s and path not like %s and path != %s
                group by path order by c desc limit 60""",
                ("/news/%", "/news/categoria/%", "/news"), as_dict=True)
            for r in rows:
                slug = (r.path or "").rstrip("/").rsplit("/", 1)[-1]
                if slug in seen:
                    continue
                art = frappe.db.get_value("News Article", {"slug": slug, "published": 1},
                                          ["title", "slug", "featured_image", "category"], as_dict=True)
                if not art:
                    continue
                if exclude_general and art.category == GENERAL:
                    continue
                if only_general and art.category != GENERAL:
                    continue
                art["reads"] = r.c
                seen.add(slug); out.append(art)
                if len(out) >= limit:
                    return out
        except Exception:
            pass
        filt = {"published": 1}
        if exclude_general:
            filt["category"] = ["!=", GENERAL]
        if only_general:
            filt["category"] = GENERAL
        recent = frappe.get_all("News Article", filters=filt,
                                fields=["title", "slug", "featured_image", "category"],
                                order_by="published_at desc", limit=limit * 3)
        for t in recent:
            if t.slug in seen:
                continue
            t["reads"] = 0
            seen.add(t.slug); out.append(t)
            if len(out) >= limit:
                break
        return out

    # 5 articoli tematici (escludendo cronaca) + 1 di cronaca
    seen = set()
    top = _pick(exclude_general=True, limit=5, seen=seen) + _pick(only_general=True, limit=1, seen=seen)

    return frappe._dict(visitors_today=visitors_today, visitors_total=visitors_total,
                        views_total=views_total, articles_total=articles_total,
                        online_since=online_since, top_read=top)
