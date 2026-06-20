"""Notifiche real-time per Intel Lead: nuovi messaggi WA, assegnazioni, trasferimenti."""
import frappe
from frappe.utils import get_url


def notify_new_lead(lead_name: str, assigned_to: str, source_name: str,
                    source_identifier: str, preview: str = ""):
    _emit_centralino(lead_name, "new_lead", source_name or source_identifier, preview)
    if not assigned_to:
        return
    _notify(
        user=assigned_to,
        title="📩 Nuovo messaggio WhatsApp",
        message=f"Da {source_name or source_identifier}: {preview[:80]}{'…' if len(preview) > 80 else ''}",
        lead_name=lead_name,
        indicator="blue",
    )


def notify_new_message_in_thread(lead_name: str, assigned_to: str,
                                  source_name: str, preview: str = ""):
    _emit_centralino(lead_name, "new_message", source_name, preview)
    if not assigned_to:
        return
    _notify(
        user=assigned_to,
        title="💬 Nuovo messaggio WhatsApp",
        message=f"{source_name or 'Contatto'}: {preview[:80]}{'…' if len(preview) > 80 else ''}",
        lead_name=lead_name,
        indicator="blue",
    )


def notify_assigned(lead_name: str, assigned_to: str, assigned_by: str):
    if not assigned_to or assigned_to == assigned_by:
        return
    by_name = frappe.db.get_value("User", assigned_by, "full_name") or assigned_by
    _notify(
        user=assigned_to,
        title="📋 Lead assegnato a te",
        message=f"{by_name} ti ha assegnato il lead {lead_name}",
        lead_name=lead_name,
        indicator="orange",
    )


def notify_transferred(lead_name: str, new_assignee: str, transferred_by: str):
    if not new_assignee or new_assignee == transferred_by:
        return
    by_name = frappe.db.get_value("User", transferred_by, "full_name") or transferred_by
    _notify(
        user=new_assignee,
        title="🔀 Conversazione trasferita",
        message=f"{by_name} ti ha trasferito la conversazione {lead_name}",
        lead_name=lead_name,
        indicator="purple",
    )


def _emit_centralino(lead_name: str, event_type: str, source_name: str = "", preview: str = ""):
    try:
        frappe.publish_realtime(
            "centralino_update",
            {"lead": lead_name, "type": event_type,
             "source_name": source_name, "preview": preview[:80]},
            after_commit=True,
        )
    except Exception:
        pass


def _notify(user: str, title: str, message: str, lead_name: str, indicator: str = "blue"):
    # Toast real-time via Socket.IO
    try:
        frappe.publish_realtime(
            event="msgprint",
            message={"message": f"<b>{title}</b><br>{message}", "indicator": indicator},
            user=user,
        )
    except Exception:
        pass

    # Notification Log (campanella nel desk)
    try:
        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": title,
            "email_content": message,
            "for_user": user,
            "type": "Alert",
            "document_type": "Intel Lead",
            "document_name": lead_name,
            "from_user": frappe.session.user or "Administrator",
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "intel_notifications Notification Log")
