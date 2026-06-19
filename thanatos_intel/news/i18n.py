"""Traduzione on-render del newsroom nella lingua scelta dal visitatore.
Canonico = italiano; si traduce SOLO se il visitatore sceglie esplicitamente
un'altra lingua (?lang=en o cookie news_lang). Cache aggressiva (7 giorni).
"""
import hashlib
import frappe
import requests

SUPPORTED = {"it", "en", "fr", "es", "de", "pt", "ro"}


def view_lang():
    l = frappe.form_dict.get("lang")
    if not l and getattr(frappe.local, "request", None):
        try:
            l = frappe.request.cookies.get("site_lang")
        except Exception:
            l = None
    l = (l or "it").lower()[:2]
    return l if l in SUPPORTED else "it"


def set_lang_cookie(lang):
    if lang in SUPPORTED and getattr(frappe.local, "cookie_manager", None):
        try:
            frappe.local.cookie_manager.set_cookie("news_lang", lang)
        except Exception:
            pass


def localize(text, target, fmt="html"):
    if not text or target == "it" or target not in SUPPORTED:
        return text
    key = "news_tr:%s:%s" % (target, hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest())
    cached = frappe.cache().get_value(key)
    if cached is not None:
        return cached
    base = (frappe.conf.get("libretranslate_url") or "http://10.10.0.4:5000").rstrip("/")
    out = text
    try:
        r = requests.post(base + "/translate", timeout=15,
                          json={"q": text[:4500], "source": "it", "target": target, "format": fmt})
        if r.ok:
            out = (r.json() or {}).get("translatedText") or text
    except Exception:
        pass
    frappe.cache().set_value(key, out, expires_in_sec=7 * 86400)
    return out


def localize_articles(articles, target):
    """Traduce title+excerpt di una lista di dict articolo (in place)."""
    if target == "it":
        return articles
    for a in articles:
        if a.get("title"):
            a["title"] = localize(a["title"], target, fmt="text")
        if a.get("excerpt"):
            a["excerpt"] = localize(a["excerpt"], target, fmt="text")
    return articles
