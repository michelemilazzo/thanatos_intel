import frappe
from frappe.model.document import Document

BODY_TEMPLATE = "thanatos_intel/thanatos_ddd/templates/mandate_body.html"


def _render_body(doc) -> str:
    """Renderizza il template Jinja del corpo e restituisce HTML pulito."""
    return frappe.render_template(BODY_TEMPLATE, {"doc": doc, "frappe": frappe})


class AgencyMandate(Document):
    def before_insert(self):
        if not self.mandate_body:
            self.mandate_body = _render_body(self)

    def before_save(self):
        # Auto-popola se ancora vuoto (es. creato via API senza trigger)
        if not self.mandate_body:
            self.mandate_body = _render_body(self)


@frappe.whitelist()
def regenerate_body(mandate_name: str) -> dict:
    """Re-renderizza il corpo dal template Jinja, sovrascrivendo le modifiche."""
    doc = frappe.get_doc("Agency Mandate", mandate_name)
    doc.mandate_body = _render_body(doc)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "mandate_body": doc.mandate_body}


@frappe.whitelist()
def preview_body(values) -> dict:
    """Renderizza il corpo dal template usando i valori CORRENTI del form (anche non
    salvati). Non salva: serve all'operatore per rivedere prima di produrre il PDF."""
    import json
    if isinstance(values, str):
        values = json.loads(values or "{}")
    doc = frappe.new_doc("Agency Mandate")
    for k, v in (values or {}).items():
        if v not in (None, ""):
            try:
                doc.set(k, v)
            except Exception:
                pass
    return {"mandate_body": _render_body(doc)}


@frappe.whitelist()
def autofill_from_case(investigation_case) -> dict:
    """Ricava i campi del mandato dal caso investigativo + cliente collegato."""
    case = frappe.get_doc("Investigation Case", investigation_case)
    out = {}
    if case.get("client"):
        out["applicant_name"] = frappe.db.get_value("Investigation Client", case.client, "client_name") or ""
    out["subject_matter"] = (case.get("summary") or case.get("description") or "").strip()[:500] or (
        f"Attività investigativa, di due diligence e verifica documentale nell'ambito del caso {case.name}.")
    out["osint_authorization"] = 1
    out["doc_verification_authorization"] = 1
    return out
