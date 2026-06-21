"""Auto-acquisizione capacità (proposta + tracciamento, con gate umano).

Da un gap di capacità l'AI propone: trova app Frappe, piano installazione,
integrazione con Thanatos Intel, testo marketing, email al cliente/mailing.
NON esegue nulla di irreversibile: crea una Capability Acquisition (stato
Proposta) che un umano approva ed esegue. Riusa il gateway MMOS AI.
"""
import json
import re
import frappe

_SYS = (
    "Sei l'ingegnere di piattaforma di Thanatos Intel (stack Frappe/ERPNext). "
    "Data una capacità mancante e un'app Frappe suggerita, produci un piano di acquisizione. "
    "REGOLA: prima riusare app Frappe esistenti. Rispondi SOLO JSON con schema: "
    "{\"app\": str, \"app_source\": str, \"install_plan\": str, \"integration_plan\": str, "
    "\"marketing_copy\": str, \"client_email\": str}. "
    "install_plan: passi bench concreti (get-app, install-app, configure). "
    "integration_plan: come collegarla a Thanatos Intel (menu/cockpit, permessi, layer dati). "
    "marketing_copy: annuncio del nuovo servizio (3-4 frasi, italiano). "
    "client_email: email breve al cliente che ne ha fatto richiesta. Italiano, concreto."
)


def _resp_text(resp):
    try:
        from thanatos_intel.workflow.ai_concierge import _resp_text as _ac
        t = _ac(resp)
        if t:
            return t
    except Exception:
        pass
    return ""


def _parse(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0) if m else text)
    except Exception:
        return None


@frappe.whitelist()
def propose_acquisition(need, suggested_app=None, source_case=None, requested_client=None, note=None):
    from thanatos_intel.ai.doc_ingest import _gateway
    roles = set(frappe.get_roles())
    if not (roles & {"System Manager", "Investigation Manager", "Thanatos Director",
                     "Investigator", "Thanatos Investigator", "Thanatos Supervisor"}):
        frappe.throw("Riservato agli operatori.")
    apps = frappe.get_installed_apps()
    msg = (f"Capacità mancante: {need}\n"
           f"App Frappe suggerita: {suggested_app or '(scegli la migliore esistente)'}\n"
           f"App già installate: {', '.join(apps)}\n"
           f"Nota: {note or '-'}\n\nProduci il piano di acquisizione. Solo JSON.")
    resp = _gateway(msg, system=_SYS, task_type="chat")
    plan = _parse(_resp_text(resp)) or {}

    doc = frappe.new_doc("Capability Acquisition")
    doc.need = (need or "Capacità")[:140]
    doc.status = "Proposta"
    doc.suggested_app = (plan.get("app") or suggested_app or "")[:140]
    doc.app_source = (plan.get("app_source") or "")[:140]
    doc.install_plan = plan.get("install_plan") or ""
    doc.integration_plan = plan.get("integration_plan") or ""
    doc.marketing_copy = plan.get("marketing_copy") or ""
    doc.client_email = plan.get("client_email") or ""
    if source_case and frappe.db.exists("Investigation Case", source_case):
        doc.source_case = source_case
    if requested_client and frappe.db.exists("Investigation Client", requested_client):
        doc.requested_client = requested_client
    if note:
        doc.notes = note[:140]
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": doc.name, "ai": bool(plan)}
