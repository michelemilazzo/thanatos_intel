# -*- coding: utf-8 -*-
"""Portale cliente: documenti SPID richiesti dall'operatore.

Il cliente vede i documenti richiesti per le sue pratiche, la guida su come
recuperarli autenticandosi LUI con SPID sul sito ufficiale, presta il consenso
e li carica. Mai le credenziali SPID del cliente.
"""
import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/documenti-spid"
        raise frappe.Redirect

    from thanatos_intel.api.spid_documents import my_spid_requests
    reqs = my_spid_requests()
    context.pending = [r for r in reqs if r["status"] == "Richiesto"]
    context.done = [r for r in reqs if r["status"] != "Richiesto"]
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Documenti richiesti — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
