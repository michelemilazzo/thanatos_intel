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

    top = []
    try:
        rows = frappe.db.sql("""
            select path, count(*) c from `tabWeb Page View`
            where path like '/news/%%' and path not like '/news/categoria/%%' and path != '/news'
            group by path order by c desc limit %s""", (top_n,), as_dict=True)
        for r in rows:
            slug = (r.path or "").rstrip("/").rsplit("/", 1)[-1]
            art = frappe.db.get_value("News Article", {"slug": slug, "published": 1},
                                      ["title", "slug", "featured_image", "category"], as_dict=True)
            if art:
                art["reads"] = r.c
                top.append(art)
    except Exception:
        pass
    # se nessuna lettura tracciata, mostra i piu recenti come "in evidenza"
    if not top:
        top = frappe.get_all("News Article", filters={"published": 1},
                             fields=["title", "slug", "featured_image", "category"],
                             order_by="published_at desc", limit=top_n)
        for t in top:
            t["reads"] = 0

    return frappe._dict(visitors_today=visitors_today, visitors_total=visitors_total,
                        views_total=views_total, articles_total=articles_total,
                        online_since=online_since, top_read=top)
