"""Neutralizza i redirect globali /login e /signup -> /mail/* introdotti dall'app
Frappe `mail` (apps/mail/mail/hooks.py), che dirottano il login del sito.

Persistente: vive in thanatos_intel (deploy pipeline), non tocca l'app vendored.
Meccanismo: resolve_redirect (frappe/website/path_resolver.py) salta il redirect se
la cache `website_redirects[<path>]` è già False; lo pre-impostiamo via before_request
per i soli path 'login'/'signup'. PathResolver usa path.strip('/ ') come chiave.
"""
import frappe

_BYPASS = ("login", "signup")


def neutralize_mail_login_redirect():
    try:
        req = getattr(frappe.local, "request", None)
        if not req:
            return
        path = (req.path or "").strip("/ ")
        if path in _BYPASS:
            frappe.cache.hset("website_redirects", path, False)
    except Exception:
        pass
