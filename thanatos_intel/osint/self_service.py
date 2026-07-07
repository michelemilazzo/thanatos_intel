"""Vendita self-serve: il cliente compra un documento/servizio dal portale, paga
dal wallet, riceve nel suo archivio (e via email). Riusa: wallet pre-pay
(official_documents/openapi), consegna (case_file_delivery), gate legale
(Consent Record + legal.agreements). Acquisto spot leggero su un «caso personale».
"""
import frappe
from frappe.utils import now_datetime

# Servizi vendibili self-serve. gated=True → richiede dichiarazione (servizi su terzi).
# engine: "doc" (documento ufficiale PDF via official_documents) | "lookup" (servizio dato via openapi_client)
SELF_SERVE = [
    {"key": "ordinaria_capitale", "label": "Visura ordinaria — società di capitale", "doc": "ordinaria_capitale", "gated": False, "cap": "visura", "engine": "doc"},
    {"key": "storica_capitale",   "label": "Visura storica — società di capitale",   "doc": "storica_capitale",   "gated": False, "cap": "visura", "engine": "doc"},
    {"key": "ordinaria_persone",  "label": "Visura ordinaria — società di persone",  "doc": "ordinaria_persone",  "gated": False, "cap": "visura", "engine": "doc"},
    {"key": "ordinaria_individuale", "label": "Visura ordinaria — impresa individuale", "doc": "ordinaria_individuale", "gated": False, "cap": "visura", "engine": "doc"},
    {"key": "bilancio",           "label": "Bilancio ottico",                         "doc": "bilancio",           "gated": False, "cap": "visura", "engine": "doc"},
    {"key": "certificato",        "label": "Certificato di iscrizione",               "doc": "certificato",        "gated": False, "cap": "visura", "engine": "doc"},
    {"key": "certificato_vigenza", "label": "Certificato di vigenza",                 "doc": "certificato_vigenza", "gated": False, "cap": "visura", "engine": "doc"},
    {"key": "soci",        "label": "Soci e titolari effettivi (UBO)",   "kind": "soci",        "gated": True, "cap": "soci",        "engine": "lookup", "target_label": "P.IVA azienda"},
    {"key": "negativita",  "label": "Negatività / protesti / pregiudizievoli", "kind": "negativita", "gated": True, "cap": "negativita",  "engine": "lookup", "target_label": "P.IVA / Codice Fiscale"},
    {"key": "patrimoniale", "label": "Patrimoniale persona (beni intestati)", "kind": "patrimoniale", "gated": True, "cap": "patrimoniale", "engine": "lookup", "target_label": "Codice Fiscale persona"},
    {"key": "veicolo",     "label": "Veicolo per targa",                "kind": "veicolo",     "gated": True, "cap": "veicolo",     "engine": "lookup", "target_label": "Targa"},
]

# Documenti DocuEngine self-serve dal portale: SOLO quelli a un unico campo dati
# (Codice Fiscale/P.IVA azienda). I certificati anagrafici (molti campi + esenzione
# bollo) restano al desk. Campo dati = "taxCode". engine "docuengine".
SELF_SERVE_DE = [
    {"key": "de_bilancio_ottico",  "label": "Bilancio ottico (azienda)",       "document_id": "667443c29e6f0e447bc265aa"},
    {"key": "de_bilancio_xbrl",    "label": "Bilancio XBRL (azienda)",         "document_id": "667c131a9e6f0e447bc265c1"},
    {"key": "de_statuto",          "label": "Statuto (azienda)",               "document_id": "6687eed51a241a5d1be0f9fa"},
    {"key": "de_cert_iscrizione",  "label": "Certificato di iscrizione (azienda)", "document_id": "689c99942d09c0a9bcb946e8"},
    {"key": "de_soci_attivi",      "label": "Soci attivi (azienda)",           "document_id": "6932c9602a2ea4883e6ebba9"},
    {"key": "de_esponenti_attivi", "label": "Esponenti/amministratori attivi (azienda)", "document_id": "69cbcb52e9834541b0415e79"},
    {"key": "de_fascicolo_cap",    "label": "Fascicolo società di capitali",   "document_id": "69c40e2f327b41417c839015"},
    {"key": "de_visura_inglese",   "label": "Visura camerale in inglese (azienda)", "document_id": "66840ce41a241a5d1be0f9e5"},
]


@frappe.whitelist()
def list_services():
    from thanatos_intel.osint.tool_catalog import tool_price
    from thanatos_intel.workflow.vault import client_of_user
    from thanatos_intel.billing.credits import available_to_spend
    cl = client_of_user()
    services = [{"key": s["key"], "label": s["label"], "gated": s["gated"],
                 "target_label": s.get("target_label") or "P.IVA / Codice Fiscale",
                 "prezzo": tool_price(None, s["cap"])} for s in SELF_SERVE]
    # documenti DocuEngine (prezzo dal catalogo openapi, markup cliente incluso)
    try:
        from thanatos_intel.osint.official_documents import docuengine_catalog
        by_id = {d["id"]: d for d in docuengine_catalog(case=None).get("documenti") or []}
        for s in SELF_SERVE_DE:
            d = by_id.get(s["document_id"])
            if d:
                services.append({"key": s["key"], "label": s["label"], "gated": False,
                                 "target_label": "Codice Fiscale / P.IVA azienda",
                                 "prezzo": d["prezzo"]})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "self_service DocuEngine catalog")
    return {"services": services,
            "wallet": (available_to_spend(cl.name) if cl else 0),
            "client": (cl.name if cl else None)}


@frappe.whitelist()
def buy_document(service, target, finalita=None, accept_declaration=0, name=None, surname=None):
    from thanatos_intel.workflow.vault import client_of_user
    cl = client_of_user()
    if not cl:
        frappe.throw("Devi essere un cliente registrato per acquistare.")
    s = next((x for x in SELF_SERVE if x["key"] == service), None)
    de = next((x for x in SELF_SERVE_DE if x["key"] == service), None) if not s else None
    if not s and not de:
        frappe.throw("Servizio non valido.")
    target = "".join(ch for ch in (target or "") if ch.isalnum())
    if not target:
        frappe.throw("Inserisci il target (%s)." % ((s or de).get("target_label") or "Codice Fiscale / P.IVA"))

    # documento DocuEngine a campo singolo (taxCode) — dati pubblici, non gated
    if de:
        case = _personal_case(cl.name)
        from thanatos_intel.osint.official_documents import richiedi_docuengine
        res = richiedi_docuengine(case, de["document_id"], valori={"taxCode": target}, self_mode=1)
        res["servizio"] = de["label"]
        res["case"] = case
        return res

    # gate legale per servizi su terzi
    if s["gated"]:
        if not int(accept_declaration or 0):
            from thanatos_intel.legal.agreements import get_doc
            return {"needs_declaration": True,
                    "declaration": get_doc("dichiarazione", servizio=s["label"], target=target)}
        frappe.get_doc({"doctype": "Consent Record", "client": cl.name, "data_subject": target,
                        "purpose": (finalita or ("Servizio %s" % s["label"]))[:140],
                        "legal_basis": "Interesse legittimo", "given_on": now_datetime(),
                        "channel": "portale self-serve"}).insert(ignore_permissions=True)

    case = _personal_case(cl.name)

    if s["engine"] == "lookup":
        from thanatos_intel.osint.openapi_client import enqueue_lookup
        res = enqueue_lookup(s["kind"], value=target, investigation_case=case,
                             name=name, surname=surname, tax_code=target, self_mode=1)
    else:
        from thanatos_intel.osint.official_documents import richiedi_documento
        res = richiedi_documento(case, s["doc"], target, self_mode=1)

    res["servizio"] = s["label"]
    res["case"] = case
    return res


def _personal_case(client):
    """Contenitore leggero per gli acquisti spot del cliente (uno solo, riusato)."""
    name = frappe.db.get_value("Investigation Case",
                               {"client": client, "case_title": "Acquisti documenti self-service"}, "name")
    if name:
        return name
    from thanatos_intel.billing.crm_pipeline import _next_case_number
    c = frappe.get_doc({"doctype": "Investigation Case", "case_number": _next_case_number(),
                        "case_title": "Acquisti documenti self-service", "client": client,
                        "status": "Open"})
    c.flags.ignore_mandatory = True
    c.insert(ignore_permissions=True)
    return c.name
