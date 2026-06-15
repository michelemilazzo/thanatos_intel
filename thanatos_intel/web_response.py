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
