"""API per creare Intel Lead da fonti esterne o manualmente via POST autenticato."""
import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def create_lead(
    source_type: str,
    content: str,
    source_identifier: str = "",
    source_name: str = "",
    priority: str = "Media",
    tags: str = "",
    media_url: str = "",
) -> dict:
    allowed_sources = {
        "WhatsApp", "Telegram", "Email", "Telefono", "Web",
        "OSINT Feed", "Segnalazione", "Manuale",
    }
    if source_type not in allowed_sources:
        frappe.throw(_("Canale non valido: {0}").format(source_type))

    doc = frappe.get_doc({
        "doctype": "Intel Lead",
        "received_at": now_datetime(),
        "source_type": source_type,
        "source_identifier": source_identifier,
        "source_name": source_name,
        "content": content,
        "priority": priority,
        "tags": tags,
        "media_url": media_url,
        "status": "Nuovo",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "status": doc.status}
