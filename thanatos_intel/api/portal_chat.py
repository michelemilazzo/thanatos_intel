"""API per la chat web cliente (/portal/chat). Scope: solo casi del cliente
loggato. Riusa Intel Lead esistente del cliente, ne crea uno nuovo se non c'è."""
import frappe
from frappe import _
from frappe.utils import now_datetime


def _guard(case_name):
    if frappe.session.user == "Guest":
        frappe.throw(_("Login richiesto."), frappe.PermissionError)
    from thanatos_intel.permissions import visible_case_names, is_full_access
    if not is_full_access(frappe.session.user):
        visible = visible_case_names(frappe.session.user) or []
        if case_name not in visible:
            frappe.throw(_("Accesso negato al caso {0}").format(case_name),
                         frappe.PermissionError)


def _get_or_create_lead(case_name, user):
    """Trova (o crea) un Intel Lead di tipo Portal per questo caso+utente."""
    lead = frappe.db.get_value(
        "Intel Lead",
        {"linked_case": case_name, "source_type": "Portal"},
        "name",
    )
    if lead:
        return lead
    # se c'è già un lead WhatsApp collegato lo riuso (thread unificato)
    lead = frappe.db.get_value(
        "Intel Lead",
        {"linked_case": case_name, "source_type": "WhatsApp"},
        "name",
    )
    if lead:
        return lead
    # crea nuovo
    doc = frappe.get_doc({
        "doctype": "Intel Lead",
        "source_type": "Portal",
        "source_identifier": user,
        "source_name": frappe.db.get_value("User", user, "full_name") or user,
        "linked_case": case_name,
        "status": "Aperto",
    })
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


@frappe.whitelist()
def get_case_thread(case_name):
    """Ritorna i messaggi del thread cliente per il caso. Scope: solo casi
    visibili all'utente loggato."""
    _guard(case_name)
    lead = _get_or_create_lead(case_name, frappe.session.user)
    doc = frappe.get_doc("Intel Lead", lead)
    messages = []
    for m in sorted(doc.messages or [], key=lambda x: x.sent_at or ""):
        content = (m.content or "").strip()
        if content.startswith("[") or content.startswith("—"):
            continue
        messages.append({
            "direction": m.direction,
            "content": content,
            "sent_at": str(m.sent_at or ""),
            "media_url": m.media_url,
        })
    return {"lead": lead, "case": case_name, "messages": messages}


@frappe.whitelist()
def send_message(case_name, message_text):
    """Cliente scrive dal portale. Registriamo come Inbound e notifichiamo gli
    operatori (realtime + push)."""
    _guard(case_name)
    text = (message_text or "").strip()
    if not text:
        return {"ok": False}
    lead = _get_or_create_lead(case_name, frappe.session.user)
    doc = frappe.get_doc("Intel Lead", lead)
    doc.append("messages", {
        "direction": "Inbound",
        "sent_at": now_datetime(),
        "content": text,
        "status": "Ricevuto",
        "sent_by": frappe.session.user,
    })
    doc.db_set("last_message_at", now_datetime(), notify=False)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    try:
        frappe.publish_realtime(
            "centralino_update",
            {"lead": lead, "type": "new_message", "source": "portal"},
            after_commit=True,
        )
    except Exception:
        pass
    try:
        from thanatos_intel.api.push import on_new_inbound_message
        on_new_inbound_message(lead, doc.source_name, text)
    except Exception:
        pass
    return {"ok": True, "lead": lead}
