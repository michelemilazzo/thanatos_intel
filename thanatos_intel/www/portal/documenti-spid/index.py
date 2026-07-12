# -*- coding: utf-8 -*-
"""Portale cliente: documenti SPID richiesti dall'operatore.

Il cliente vede i documenti richiesti per le sue pratiche, guida passo-passo su
come recuperarli col PROPRIO SPID, aiuto se non sa/non ha SPID, consenso e upload.
Mai le credenziali SPID del cliente.
"""
import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/documenti-spid"
        raise frappe.Redirect

    from thanatos_intel.api.spid_documents import my_spid_requests
    from thanatos_intel.osint.spid_catalog import SPID_HELP
    reqs = my_spid_requests()
    context.pending = [r for r in reqs if r["status"] == "Richiesto"]
    context.done = [r for r in reqs if r["status"] != "Richiesto"]
    context.spid_help = SPID_HELP
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Documenti richiesti — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
