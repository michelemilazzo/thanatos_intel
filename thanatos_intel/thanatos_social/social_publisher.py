"""Allineamento News e Servizi Thanatos → Pagina Facebook / Instagram.

- News: quando un News Article va live (``published`` 0→1) crea un Facebook Post
  e lo pubblica (foto se ha ``featured_image``, altrimenti link). Solo news in
  evidenza/interne salvo override, per non intasare la Pagina col firehose RSS.
- Servizi: scheduler settimanale che pubblica a rotazione un servizio attivo.

Il job giornaliero delle news usa ``frappe.db.set_value`` (che NON fa scattare i
doc_events), perciò l'auto-pubblicazione è coperta sia dall'hook ``on_update``
(pubblicazioni manuali) sia dallo scheduler ``sync_published_news`` (job
giornaliero). Entrambi deduplicano sull'esistenza del Facebook Post di origine.
"""

import re

import frappe
from frappe.utils import add_to_date, cint, get_url, now_datetime

from thanatos_intel.integrations import facebook_graph as fb


def _settings():
    if frappe.db.exists("DocType", "Facebook Settings"):
        return frappe.get_single("Facebook Settings")
    return None


def _hashtags(s) -> str:
    return (getattr(s, "social_hashtags", "") or "").strip()


def _abs_url(file_url: str) -> str:
    if not file_url:
        return ""
    if file_url.startswith("http://") or file_url.startswith("https://"):
        return file_url
    return get_url().rstrip("/") + "/" + file_url.lstrip("/")


def _already_posted(doctype: str, name: str) -> bool:
    return bool(frappe.db.exists(
        "Facebook Post", {"source_doctype": doctype, "source_name": name}))


# ---------------------------------------------------------------------------
# NEWS → social
# ---------------------------------------------------------------------------

def _news_url(doc) -> str:
    route = (doc.get("route") or "").strip("/")
    if not route:
        slug = (doc.get("slug") or "").strip("/")
        route = f"news/{slug}" if slug else ""
    base = get_url().rstrip("/")
    return f"{base}/{route}" if route else base


def _news_caption(doc, s) -> str:
    body = (doc.get("thanatos_angle") or doc.get("excerpt") or "").strip()
    parts = [doc.get("title") or ""]
    if body:
        parts.append(body[:400])
    tags = _hashtags(s)
    if tags:
        parts.append(tags)
    return "\n\n".join(p for p in parts if p).strip()


def _skip_news(doc_or_row, s) -> bool:
    """True se la news NON va pubblicata sui social (filtro anti-spam RSS)."""
    is_rss = doc_or_row.get("source_type") == "RSS Ingestion"
    if is_rss and not cint(doc_or_row.get("featured")) and not cint(
            getattr(s, "auto_publish_news_all", 0)):
        return True
    return False


def _create_and_publish_from_news(doc, s):
    image_url = _abs_url((doc.get("featured_image") or "").strip())
    also_ig = bool(image_url and cint(getattr(s, "also_instagram", 0))
                   and fb.instagram_available())
    post = frappe.get_doc({
        "doctype": "Facebook Post",
        "post_title": ("News: " + (doc.get("title") or doc.name))[:140],
        "post_type": "Foto" if image_url else "Link",
        "message": _news_caption(doc, s),
        "link": _news_url(doc),
        "image_url": image_url,
        "also_instagram": 1 if also_ig else 0,
        "source_doctype": "News Article",
        "source_name": doc.name,
    })
    post.insert(ignore_permissions=True)
    post.publish_now()
    return post.name


def on_news_article_update(doc, method=None):
    """doc_event ``on_update``: pubblica sui social alla transizione 0→1 di
    ``published`` (pubblicazione manuale). Best-effort, non blocca il salvataggio.
    """
    try:
        if not cint(doc.get("published")):
            return
        before = doc.get_doc_before_save()
        if before and cint(before.get("published")):
            return  # era già pubblicato: nessuna transizione
        s = _settings()
        if not s or not fb.is_enabled() or not cint(getattr(s, "auto_publish_news", 0)):
            return
        if _skip_news(doc, s) or _already_posted("News Article", doc.name):
            return
        _create_and_publish_from_news(doc, s)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "social on_news_article_update")


def sync_published_news():
    """Scheduler: intercetta le news pubblicate dal job giornaliero (db.set_value,
    che non fa scattare gli hook) e le posta sui social. Cap di sicurezza per run.
    """
    s = _settings()
    if not s or not fb.is_enabled() or not cint(getattr(s, "auto_publish_news", 0)):
        return
    since = add_to_date(now_datetime(), hours=-30)
    rows = frappe.get_all(
        "News Article",
        filters={"published": 1, "published_at": [">=", since]},
        fields=["name", "source_type", "featured"],
        order_by="published_at desc", limit=40,
    )
    done = 0
    for r in rows:
        if done >= 8:  # non intasare la Pagina in un solo giro
            break
        if _already_posted("News Article", r.name) or _skip_news(r, s):
            continue
        try:
            doc = frappe.get_doc("News Article", r.name)
            _create_and_publish_from_news(doc, s)
            done += 1
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), f"sync_published_news {r.name}")


# ---------------------------------------------------------------------------
# SERVIZI → spotlight settimanale a rotazione
# ---------------------------------------------------------------------------

def _service_caption(svc, s) -> str:
    desc = re.sub(r"<[^>]+>", " ", svc.get("description") or "")
    desc = re.sub(r"\s+", " ", desc).strip()
    parts = [f"🔎 {svc.get('service_name') or svc.name}"]
    if desc:
        parts.append(desc[:400])
    if svc.get("price"):
        parts.append(f"💶 A partire da {int(svc.price)} {svc.get('currency') or 'EUR'}")
    tags = _hashtags(s)
    if tags:
        parts.append(tags)
    return "\n\n".join(p for p in parts if p).strip()


def _next_service(s):
    rows = frappe.get_all("Service Catalog", filters={"is_active": 1},
                          fields=["name"], order_by="creation asc")
    if not rows:
        return None
    names = [r.name for r in rows]
    last = getattr(s, "service_spotlight_last", None)
    idx = (names.index(last) + 1) % len(names) if last in names else 0
    return frappe.get_doc("Service Catalog", names[idx])


def publish_service_spotlight():
    """Scheduler settimanale: pubblica a rotazione un servizio attivo."""
    try:
        s = _settings()
        if not s or not fb.is_enabled() or not cint(
                getattr(s, "service_spotlight_enabled", 0)):
            return
        svc = _next_service(s)
        if not svc:
            return
        post = frappe.get_doc({
            "doctype": "Facebook Post",
            "post_title": ("Servizio: " + (svc.get("service_name") or svc.name))[:140],
            "post_type": "Link",
            "message": _service_caption(svc, s),
            "link": get_url().rstrip("/") + "/servizi",
            "source_doctype": "Service Catalog",
            "source_name": svc.name,
        })
        post.insert(ignore_permissions=True)
        post.publish_now()
        frappe.db.set_single_value("Facebook Settings", "service_spotlight_last", svc.name)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "social service_spotlight")


@frappe.whitelist()
def publish_service_now(service_code: str):
    """Pubblica manualmente un servizio specifico (usabile da pulsante/API)."""
    s = _settings()
    if not s or not fb.is_enabled():
        frappe.throw("Integrazione Facebook non attiva.")
    svc = frappe.get_doc("Service Catalog", service_code)
    post = frappe.get_doc({
        "doctype": "Facebook Post",
        "post_title": ("Servizio: " + (svc.get("service_name") or svc.name))[:140],
        "post_type": "Link",
        "message": _service_caption(svc, s),
        "link": get_url().rstrip("/") + "/servizi",
        "source_doctype": "Service Catalog",
        "source_name": svc.name,
    })
    post.insert(ignore_permissions=True)
    post.publish_now()
    return {"name": post.name, "status": post.status, "fb_post_id": post.fb_post_id}
