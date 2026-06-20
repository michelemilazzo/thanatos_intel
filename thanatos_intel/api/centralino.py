import frappe
from frappe import _


# ─── Conversations ────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_conversations(filter_type="all", search=""):
    user = frappe.session.user
    conditions = ["l.docstatus < 2", "l.status != 'Archiviato'"]
    values = {}

    if filter_type == "mine":
        conditions.append("l.assigned_to = %(user)s")
        values["user"] = user
    elif filter_type == "unassigned":
        conditions.append("(l.assigned_to IS NULL OR l.assigned_to = '')")

    if search:
        conditions.append(
            "(l.source_name LIKE %(search)s OR l.source_identifier LIKE %(search)s)"
        )
        values["search"] = f"%{search}%"

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            l.name, l.source_name, l.source_identifier, l.source_type,
            l.status, l.priority, l.assigned_to, l.last_message_at, l.creation,
            l.linked_case, l.linked_contact, l.whatsapp_number,
            (SELECT COUNT(*) FROM `tabIntel Lead Message` m
             WHERE m.parent = l.name AND m.direction = 'Inbound') AS msg_count
        FROM `tabIntel Lead` l
        WHERE {where}
        ORDER BY COALESCE(l.last_message_at, l.creation) DESC
        LIMIT 150
        """,
        values,
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_thread(lead_name):
    doc = frappe.get_doc("Intel Lead", lead_name)
    messages = []
    for m in sorted(doc.messages or [], key=lambda x: x.sent_at or ""):
        messages.append({
            "name": m.name,
            "direction": m.direction,
            "content": m.content,
            "sent_at": str(m.sent_at or ""),
            "status": m.status,
            "sent_by": m.sent_by,
            "media_url": m.media_url,
        })
    return {
        "name": doc.name,
        "source_name": doc.source_name,
        "source_identifier": doc.source_identifier,
        "source_type": doc.source_type,
        "status": doc.status,
        "priority": doc.priority,
        "assigned_to": doc.assigned_to,
        "linked_case": doc.linked_case,
        "linked_contact": doc.linked_contact,
        "whatsapp_number": doc.whatsapp_number,
        "messages": messages,
    }


@frappe.whitelist()
def send_reply(lead_name, message_text):
    from thanatos_intel.ingest.whatsapp_send import send_reply as _send
    return _send(lead_name, message_text)


@frappe.whitelist()
def close_lead(lead_name):
    frappe.db.set_value("Intel Lead", lead_name, "status", "Chiuso")
    frappe.db.commit()
    _emit(lead_name, "closed")
    return {"ok": True}


@frappe.whitelist()
def reopen_lead(lead_name):
    frappe.db.set_value("Intel Lead", lead_name, "status", "Aperto")
    frappe.db.commit()
    _emit(lead_name, "reopened")
    return {"ok": True}


@frappe.whitelist()
def assign_lead(lead_name, to_user):
    frappe.db.set_value("Intel Lead", lead_name, "assigned_to", to_user)
    frappe.db.commit()
    _emit(lead_name, "assigned")
    return {"ok": True}


# ─── Operator status ──────────────────────────────────────────────────────────

@frappe.whitelist()
def set_operator_status(status):
    if status not in ("online", "busy", "offline"):
        frappe.throw(_("Stato non valido"))
    frappe.cache.hset("centralino_op_status", frappe.session.user, status)
    frappe.publish_realtime(
        "centralino_op_status",
        {"user": frappe.session.user, "status": status},
    )
    return {"ok": True}


@frappe.whitelist()
def get_operator_statuses():
    raw = frappe.cache.hgetall("centralino_op_status") or {}
    # hgetall returns bytes keys/values in some redis versions
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }


# ─── Users list for assign dialog ────────────────────────────────────────────

@frappe.whitelist()
def get_operators():
    roles = ("Investigator", "Investigation Manager", "System Manager")
    users = frappe.db.sql(
        """
        SELECT DISTINCT u.name, u.full_name, u.user_image
        FROM `tabUser` u
        JOIN `tabHas Role` r ON r.parent = u.name
        WHERE r.role IN %(roles)s AND u.enabled = 1 AND u.name != 'Guest'
        ORDER BY u.full_name
        """,
        {"roles": roles},
        as_dict=True,
    )
    return users


# ─── Helper ───────────────────────────────────────────────────────────────────

def _emit(lead_name, event_type, extra=None):
    payload = {"lead": lead_name, "type": event_type}
    if extra:
        payload.update(extra)
    frappe.publish_realtime("centralino_update", payload, after_commit=True)
