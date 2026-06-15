"""Tuning header di risposta del sito Thanatos.

Frappe serve le pagine HTML del sito con
`Cache-Control: private,max-age=300,stale-while-revalidate=10800` (SWR 3h):
un eventuale 404 transitorio resta "appiccicato" nei browser dei visitatori
fino a 3 ore. Riduciamo SOLO la finestra stale-while-revalidate.

NB: process_response() in frappe/app.py applica `frappe.local.response_headers`
DOPO gli hook after_request, quindi va modificato quello (non response.headers).
"""
import frappe

_WEBSITE_CC = "private,max-age=300,stale-while-revalidate=10800"
_TUNED_CC = "private,max-age=300,stale-while-revalidate=120"


def tune_cache(response=None, request=None, **kwargs):
    try:
        rh = getattr(frappe.local, "response_headers", None)
        if rh is not None and rh.get("Cache-Control") == _WEBSITE_CC:
            rh["Cache-Control"] = _TUNED_CC
        if response is not None and response.headers.get("Cache-Control") == _WEBSITE_CC:
            response.headers["Cache-Control"] = _TUNED_CC
    except Exception:
        pass
