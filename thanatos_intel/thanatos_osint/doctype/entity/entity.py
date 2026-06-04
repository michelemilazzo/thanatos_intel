import json
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class Entity(Document):
    def before_save(self):
        if not self.first_seen:
            self.first_seen = now_datetime()
        self.last_seen = now_datetime()
        self.risk_band = _band(self.risk_score or 0)

    def autoname(self):
        if not self.label:
            self.label = self.primary_value or self.entity_type


def _band(score: int) -> str:
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Medium"
    if score > 0:
        return "Low"
    return ""


@frappe.whitelist()
def upsert(entity_type: str, primary_value: str, label: str = None, **kwargs) -> str:
    """Crea o aggiorna entity. Match per (entity_type, primary_value)."""
    existing = frappe.db.get_value("Entity",
        {"entity_type": entity_type, "primary_value": primary_value}, "name")
    if existing:
        doc = frappe.get_doc("Entity", existing)
        doc.last_seen = now_datetime()
        for k, v in kwargs.items():
            if hasattr(doc, k) and v is not None:
                setattr(doc, k, v)
        doc.save(ignore_permissions=True)
        return doc.name
    doc = frappe.get_doc({
        "doctype": "Entity",
        "entity_type": entity_type,
        "primary_value": primary_value,
        "label": label or primary_value,
        **{k: v for k, v in kwargs.items() if v is not None},
    })
    doc.insert(ignore_permissions=True)
    return doc.name
