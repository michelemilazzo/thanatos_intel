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

# --- routing bilingue: slug IT canonico <-> alias EN ----------------------
# Usato per: (1) dedurre la lingua dall'URL (parte IT=italiano, EN=inglese),
# (2) riscrivere gli href verso EN quando si rende in inglese, (3) far
# risolvere entrambi gli slug alla stessa pagina (vedi website_route_rules).
ROUTE_PAIRS = [
    ("/piani", "/plans"),
    ("/notizie", "/news"),
    ("/chi-siamo", "/about"),
    ("/soluzioni", "/solutions"),
    ("/servizi", "/services"),
    ("/collabora", "/collaborate"),
    ("/casi", "/cases"),
    ("/contatti", "/contact"),
    ("/registrati", "/register"),
    ("/verifica-blacklist", "/blacklist-check"),
    ("/verifica-rischio", "/risk-check"),
    ("/diventa-collaboratore", "/become-a-partner"),
    ("/termini", "/terms"),
    ("/portale", "/portal"),
]
IT_TO_EN = {it: en for it, en in ROUTE_PAIRS}
# Lang-neutral: lingua dal cookie, NON forzata dall'URL.
#  - portale: area riservata, un cliente IT puo' avere /portal come home
#  - news: gli articoli vivono sotto /news/<slug> (route da DB), un lettore
#    italiano non deve vederli tradotti in inglese
_LANG_NEUTRAL = {"/portal", "/portale", "/news", "/notizie"}


def _norm_path(p):
    p = (p or "/").split("?")[0].split("#")[0]
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p or "/"


def lang_from_path(path):
    """'it'/'en' se lo slug dell'URL indica la lingua, altrimenti None."""
    p = _norm_path(path)
    for it, en in ROUTE_PAIRS:
        if it in _LANG_NEUTRAL or en in _LANG_NEUTRAL:
            continue
        if p == en or p.startswith(en + "/"):
            return "en"
        if p == it or p.startswith(it + "/"):
            return "it"
    return None


def _swap_route(url, mapping):
    """Rimappa il path iniziale di un href IT->EN, preservando query/hash."""
    m = re.match(r"^([^?#]*)([?#].*)?$", url or "")
    path, rest = m.group(1), (m.group(2) or "")
    for src, dst in mapping.items():
        if path == src:
            return dst + rest
        if path.startswith(src + "/"):
            return dst + path[len(src):] + rest
    return url


SKIP_TAGS = {"script", "style", "noscript", "code", "pre", "textarea", "kbd", "samp", "svg"}
ATTRS = ("placeholder", "title", "alt", "aria-label", "content")  # content solo su meta description
_LETTER = re.compile(r"[A-Za-zÀ-ÿ]")
_SKIP_STR = re.compile(r"^(?:https?://|mailto:|tel:|[\w.+-]+@[\w.-]+\.\w+|[\W\d\s]+)$")


def current_lang():
    # 1) override esplicito ?lang= (toggle lingua)
    l = frappe.form_dict.get("lang") if getattr(frappe.local, "form_dict", None) else None
    if l:
        l = l.lower()[:2]
        return l if (l == "it" or l in SUPPORTED) else "it"
    # 2) lo slug canonico dell'URL determina la lingua (IT vs EN)
    try:
        byp = lang_from_path(frappe.local.request.path) if getattr(frappe.local, "request", None) else None
    except Exception:
        byp = None
    if byp:
        return byp
    # 3) cookie scelto, default italiano
    if getattr(frappe.local, "request", None):
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
        if target == "en":
            for el in tree.iter():
                for attr in ("href", "action"):
                    v = el.get(attr)
                    if not v or "://" in v or v.startswith(("#", "mailto:", "tel:")):
                        continue
                    nv = _swap_route(v, IT_TO_EN)
                    if nv != v:
                        el.set(attr, nv)
        out = lxml.html.tostring(tree, encoding="unicode", doctype="<!DOCTYPE html>")
        frappe.cache().set_value(key, out, expires_in_sec=86400)
        return out
    except Exception:
        frappe.log_error(frappe.get_traceback(), "site_i18n translate_html")
        return html
