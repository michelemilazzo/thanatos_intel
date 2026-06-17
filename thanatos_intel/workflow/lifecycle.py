"""Aggancio del Motore Pratiche al ciclo di vita di Investigation Case."""
import frappe
from thanatos_intel.workflow import engine


def on_case_after_insert(doc, method=None):
    """Se la pratica nasce con un blueprint, materializza subito gli step.
    Non avvia il motore: l'avvio (start) lo decide il wizard/operatore."""
    if not doc.get("blueprint") or doc.get("case_steps"):
        return
    try:
        doc.reload()
        engine.setup_from_blueprint(doc)
        doc.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "workflow.lifecycle.after_insert")
