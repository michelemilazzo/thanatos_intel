"""Vendita self-serve: il cliente compra un documento/servizio dal portale, paga
dal wallet, riceve nel suo archivio (e via email). Riusa: wallet pre-pay
(official_documents/openapi), consegna (case_file_delivery), gate legale
(Consent Record + legal.agreements). Acquisto spot leggero su un «caso personale».
"""
import frappe
from frappe.utils import now_datetime

# Servizi vendibili self-serve. gated=True → richiede dichiarazione (servizi su terzi).
SELF_SERVE = [
    {"key": "ordinaria_capitale", "label": "Visura ordinaria — società di capitale", "doc": "ordinaria_capitale", "gated": False, "cap": "visura"},
    {"key": "storica_capitale",   "label": "Visura storica — società di capitale",   "doc": "storica_capitale",   "gated": False, "cap": "visura"},
    {"key": "ordinaria_persone",  "label": "Visura ordinaria — società di persone",  "doc": "ordinaria_persone",  "gated": False, "cap": "visura"},
    {"key": "ordinaria_individuale", "label": "Visura ordinaria — impresa individuale", "doc": "ordinaria_individuale", "gated": False, "cap": "visura"},
    {"key": "bilancio",           "label": "Bilancio ottico",                         "doc": "bilancio",           "gated": False, "cap": "visura"},
    {"key": "certificato",        "label": "Certificato di iscrizione",               "doc": "certificato",        "gated": False, "cap": "visura"},
    {"key": "certificato_vigenza", "label": "Certificato di vigenza",                 "doc": "certificato_vigenza", "gated": False, "cap": "visura"},
]


@frappe.whitelist()
def list_services():
    from thanatos_intel.osint.tool_catalog import tool_price
    from thanatos_intel.workflow.vault import client_of_user
    from thanatos_intel.billing.credits import available_to_spend
    cl = client_of_user()
    services = [{"key": s["key"], "label": s["label"], "gated": s["gated"],
                 "prezzo": tool_price(None, s["cap"])} for s in SELF_SERVE]
    return {"services": services,
            "wallet": (available_to_spend(cl.name) if cl else 0),
            "client": (cl.name if cl else None)}


@frappe.whitelist()
def buy_document(service, target, finalita=None, accept_declaration=0):
    from thanatos_intel.workflow.vault import client_of_user
    cl = client_of_user()
    if not cl:
        frappe.throw("Devi essere un cliente registrato per acquistare.")
    s = next((x for x in SELF_SERVE if x["key"] == service), None)
    if not s:
        frappe.throw("Servizio non valido.")
    target = "".join(ch for ch in (target or "") if ch.isalnum())
    if not target:
        frappe.throw("Inserisci il target (P.IVA / Codice Fiscale).")

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
