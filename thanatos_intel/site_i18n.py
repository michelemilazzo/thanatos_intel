"""Traduzione globale on-render del sito Thanatos.

Filtro after_request: traduce QUALSIASI pagina HTML del sito nella lingua scelta
dal visitatore (cookie `site_lang` o ?lang=). Canonico = italiano; se EN, si
traduce tutto il testo visibile (nodi di testo + attributi alt/placeholder/title)
via libretranslate in batch, con cache. Copre automaticamente anche i contenuti
futuri (nessuna i18n per-template). Fail-safe: su errore restituisce l'originale.
"""
import hashlib
import re
import frappe
import requests

SUPPORTED = {"en", "fr", "es", "de", "pt", "ro"}  # 'it' = canonico, no-op
SKIP_TAGS = {"script", "style", "noscript", "code", "pre", "textarea", "kbd", "samp", "svg"}
ATTRS = ("placeholder", "title", "alt", "aria-label", "content")  # content solo su meta description
_LETTER = re.compile(r"[A-Za-zÀ-ÿ]")
_SKIP_STR = re.compile(r"^(?:https?://|mailto:|tel:|[\w.+-]+@[\w.-]+\.\w+|[\W\d\s]+)$")


def current_lang():
    l = frappe.form_dict.get("lang") if getattr(frappe.local, "form_dict", None) else None
    if not l and getattr(frappe.local, "request", None):
        try:
            l = frappe.request.cookies.get("site_lang")
        except Exception:
            l = None
    l = (l or "it").lower()[:2]
    return l if (l == "it" or l in SUPPORTED) else "it"


def _translatable(s):
    if not s:
        return False
    t = s.strip()
    return bool(t) and bool(_LETTER.search(t)) and not _SKIP_STR.match(t) and len(t) <= 1500


def _batch(strings, target):
    """Traduce stringhe uniche (cache per-stringa + batch array). Ritorna dict src->dst."""
    uniq = list({s.strip() for s in strings if _translatable(s)})
    out = {}
    todo = []
    for s in uniq:
        ck = "tr1:%s:%s" % (target, hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest())
        c = frappe.cache().get_value(ck)
        if c is not None:
            out[s] = c
        else:
            todo.append((s, ck))
    base = (frappe.conf.get("libretranslate_url") or "http://10.10.0.4:5000").rstrip("/") + "/translate"
    for i in range(0, len(todo), 40):
        chunk = todo[i:i + 40]
        try:
            r = requests.post(base, timeout=25,
                              json={"q": [s for s, _ in chunk], "source": "it", "target": target, "format": "text"})
            res = (r.json() or {}).get("translatedText") if r.ok else None
            if isinstance(res, list) and len(res) == len(chunk):
                for (s, ck), tr in zip(chunk, res):
                    out[s] = tr or s
                    frappe.cache().set_value(ck, tr or s, expires_in_sec=14 * 86400)
                continue
        except Exception:
            pass
        for s, ck in chunk:  # fallback: lascia invariato
            out[s] = s
    return out


def _apply(orig, m):
    t = orig.strip()
    tr = m.get(t)
    if tr is None or tr == t:
        return orig
    return orig.replace(t, tr, 1)  # preserva spazi attorno


def translate_html(html, target):
    if target == "it" or target not in SUPPORTED or not html:
        return html
    key = "pgtr:%s:%s" % (target, hashlib.sha1(html.encode("utf-8", "ignore")).hexdigest())
    cached = frappe.cache().get_value(key)
    if cached is not None:
        return cached
    try:
        import lxml.html
        tree = lxml.html.fromstring(html)
        text_nodes, strings = [], []
        for el in tree.iter():
            tag = (el.tag if isinstance(el.tag, str) else "").lower()
            if tag in SKIP_TAGS:
                continue
            if el.text and _translatable(el.text):
                text_nodes.append((el, "text")); strings.append(el.text)
            if el.tail and _translatable(el.tail):
                p = el.getparent()
                ptag = (p.tag if (p is not None and isinstance(p.tag, str)) else "").lower()
                if ptag not in SKIP_TAGS:
                    text_nodes.append((el, "tail")); strings.append(el.tail)
            for a in ATTRS:
                if a == "content" and tag != "meta":
                    continue
                v = el.get(a)
                if v and _translatable(v):
                    text_nodes.append((el, "@" + a)); strings.append(v)
        m = _batch(strings, target)
        for (el, kind), src in zip(text_nodes, strings):
            new = _apply(src, m)
            if kind == "text":
                el.text = new
            elif kind == "tail":
                el.tail = new
            elif kind.startswith("@"):
                el.set(kind[1:], new)
        out = lxml.html.tostring(tree, encoding="unicode", doctype="<!DOCTYPE html>")
        frappe.cache().set_value(key, out, expires_in_sec=86400)
        return out
    except Exception:
        frappe.log_error(frappe.get_traceback(), "site_i18n translate_html")
        return html
