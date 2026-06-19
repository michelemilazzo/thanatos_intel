"""Tuning header di risposta del sito Thanatos.

Frappe serve le pagine HTML del sito con
`Cache-Control: private,max-age=300,stale-while-revalidate=10800` (SWR 3h):
un eventuale 404 transitorio resta "appiccicato" nei browser dei visitatori
fino a 3 ore.

- Sulle risposte 200 riduciamo SOLO la finestra stale-while-revalidate.
- Sulle risposte NON-200 (404/5xx transitori durante deploy/restart/build)
  forziamo `no-store`: il browser non conserva l'errore e ricarica appena
  l'origine torna sana. Senza questo, un 404 di pochi secondi durante un
  deploy faceva "perdere la home" ai visitatori per minuti.

NB: process_response() in frappe/app.py applica `frappe.local.response_headers`
DOPO gli hook after_request, quindi va modificato quello (non solo
response.headers).
"""
import frappe

_WEBSITE_CC = "private,max-age=300,stale-while-revalidate=10800"
_TUNED_CC = "private,max-age=300,stale-while-revalidate=120"
_NO_STORE = "no-store, no-cache, must-revalidate, max-age=0"


def tune_cache(response=None, request=None, **kwargs):
    try:
        status = getattr(response, "status_code", 200)
        rh = getattr(frappe.local, "response_headers", None)

        if status != 200:
            if rh is not None:
                rh["Cache-Control"] = _NO_STORE
            if response is not None:
                response.headers["Cache-Control"] = _NO_STORE
            return response

        if rh is not None and rh.get("Cache-Control") == _WEBSITE_CC:
            rh["Cache-Control"] = _TUNED_CC
        if response is not None and response.headers.get("Cache-Control") == _WEBSITE_CC:
            response.headers["Cache-Control"] = _TUNED_CC
    except Exception:
        pass
    return response


# ---- traduzione globale del sito (IT canonico, EN/altro on-render) ----

_NO_STORE_TR = "private, no-store, max-age=0"


def translate_response(response=None, request=None, **kwargs):
    """after_request: traduce l'HTML della pagina nella lingua scelta (cookie
    site_lang o ?lang). Esclude desk/api/asset/portal. Fail-safe."""
    try:
        if response is None or getattr(response, "status_code", 200) != 200:
            return response
        ctype = (response.headers.get("Content-Type") or "")
        if "text/html" not in ctype:
            return response
        path = ""
        try:
            path = (request.path if request is not None else frappe.local.request.path) or ""
        except Exception:
            pass
        if path.startswith(("/api", "/assets", "/app", "/private", "/files", "/socket")):
            return response

        from thanatos_intel import site_i18n
        lang = site_i18n.current_lang()
        # persiste la scelta lingua nel cookie
        chosen = frappe.form_dict.get("lang") if getattr(frappe.local, "form_dict", None) else None
        if chosen and chosen in (("it",) + tuple(site_i18n.SUPPORTED)):
            try:
                response.set_cookie("site_lang", chosen, max_age=180 * 86400, samesite="Lax")
            except Exception:
                pass
        if lang == "it":
            return response
        html = response.get_data(as_text=True)
        out = site_i18n.translate_html(html, lang)
        if out and out != html:
            response.set_data(out.encode("utf-8"))
            response.headers["Cache-Control"] = _NO_STORE_TR
            rh = getattr(frappe.local, "response_headers", None)
            if rh is not None:
                rh["Cache-Control"] = _NO_STORE_TR
    except Exception:
        try:
            frappe.log_error(frappe.get_traceback(), "translate_response")
        except Exception:
            pass
    return response
