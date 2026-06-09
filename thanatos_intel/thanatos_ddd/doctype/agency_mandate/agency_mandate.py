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
