import frappe
from frappe import _
from frappe.utils import now_datetime


_THREAD_WINDOW_HOURS = 24


class IntelLead(frappe.model.document.Document):

    @frappe.whitelist()
    def promote_to_case(self, case_title: str = "", case_type: str = "") -> dict:
        if self.status == "Promosso a Caso" and self.linked_case:
            return {"case": self.linked_case}

        title = case_title or (
            f"[{self.source_type}] {self.source_name or self.source_identifier or 'Lead'}"
        )
        case = frappe.get_doc({
            "doctype": "Investigation Case",
            "case_title": title,
            "case_type": case_type or None,
            "status": "Open",
            "notes": (
                f"Generato da Intel Lead {self.name}\n"
                f"Canale: {self.source_type}\n"
                f"Mittente: {self.source_name or self.source_identifier or '—'}\n\n"
                f"Contenuto originale:\n{self.content or ''}"
            ),
        })
        case.insert(ignore_permissions=True)
        frappe.db.commit()

        self.db_set("status", "Promosso a Caso", notify=True)
        self.db_set("linked_case", case.name, notify=True)
        self.db_set("promoted_at", now_datetime(), notify=True)
        self.db_set("promoted_by", frappe.session.user, notify=True)

        return {"case": case.name, "case_url": f"/app/investigation-case/{case.name}"}


def _is_write_conflict(exc) -> bool:
    """Conflitto transiente di scrittura concorrente sullo stesso documento."""
    from frappe.exceptions import TimestampMismatchError
    if isinstance(exc, TimestampMismatchError):
        return True
    s = str(exc)
    return any(k in s for k in ("1205", "Lock wait", "1213", "Deadlock",
                                "has been modified"))


def find_or_create_lead(source_identifier: str, source_name: str, content: str,
                        source_type: str = "WhatsApp", media_url: str = "",
                        wa_number: dict | None = None, wa_message_id: str = "",
                        suppress_notify: bool = False) -> str:
    """Wrapper con retry: due webhook/salvataggi concorrenti sullo stesso lead
    causano TimestampMismatch / lock wait -> ritenta rifacendo la query pulita."""
    import time
    attempts = 5
    for i in range(attempts):
        try:
            return _find_or_create_lead_once(
                source_identifier, source_name, content, source_type, media_url,
                wa_number, wa_message_id, suppress_notify)
        except Exception as e:
            frappe.db.rollback()
            if not _is_write_conflict(e) or i == attempts - 1:
                raise
            time.sleep(0.2 * (i + 1))


def _find_or_create_lead_once(source_identifier: str, source_name: str, content: str,
                        source_type: str = "WhatsApp", media_url: str = "",
                        wa_number: dict | None = None, wa_message_id: str = "",
                        suppress_notify: bool = False) -> str:
    """
    Cerca un lead aperto dallo stesso mittente nelle ultime N ore.
    Se esiste, aggiunge il messaggio al thread; altrimenti crea un nuovo lead.
    """
    # un thread per numero: riusa SEMPRE il lead aperto (non archiviato) dello stesso
    # mittente+numero WA, senza finestra temporale (no chat duplicate per giorno)
    filters = {
        "source_type": source_type,
        "source_identifier": source_identifier,
        "status": ["not in", ["Archiviato"]],
    }
    if wa_number:
        filters["whatsapp_number"] = wa_number.get("phone_number", "")

    existing = frappe.db.get_value("Intel Lead", filters, "name", order_by="last_message_at desc")

    if existing:
        doc = frappe.get_doc("Intel Lead", existing)
        doc.append("messages", {
            "direction": "Inbound",
            "sent_at": now_datetime(),
            "content": content or "(nessun testo)",
            "status": "Letto",
            "wa_message_id": wa_message_id or "",
            "media_url": media_url or "",
        })
        doc.db_set("last_message_at", now_datetime(), notify=False)
        doc.db_set("content", content or doc.content, notify=False)
        if source_name and not doc.source_name:
            doc.db_set("source_name", source_name, notify=False)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        # Notifica real-time operatore assegnato
        if doc.assigned_to and not suppress_notify:
            try:
                from thanatos_intel.ingest.intel_notifications import notify_new_message_in_thread
                notify_new_message_in_thread(existing, doc.assigned_to,
                                             source_name or source_identifier, content or "")
            except Exception:
                pass
        return existing

    # Nuovo lead
    doc = frappe.get_doc({
        "doctype": "Intel Lead",
        "received_at": now_datetime(),
        "last_message_at": now_datetime(),
        "source_type": source_type,
        "source_identifier": source_identifier,
        "source_name": source_name or "",
        "content": content or "(nessun testo)",
        "media_url": media_url or "",
        "status": "Nuovo",
        "priority": (wa_number or {}).get("default_priority") or "Media",
        "tags": (wa_number or {}).get("default_tags") or "",
        "assigned_to": (wa_number or {}).get("auto_assign_to") or "",
        "whatsapp_number": (wa_number or {}).get("phone_number") or "",
        "messages": [{
            "direction": "Inbound",
            "sent_at": now_datetime(),
            "content": content or "(nessun testo)",
            "status": "Letto",
            "wa_message_id": wa_message_id or "",
            "media_url": media_url or "",
        }],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    # Notifica operatore assegnato per nuovo lead
    assigned = (wa_number or {}).get("auto_assign_to") or ""
    if assigned and not suppress_notify:
        try:
            from thanatos_intel.ingest.intel_notifications import notify_new_lead
            notify_new_lead(doc.name, assigned, source_name or "", source_identifier, content or "")
        except Exception:
            pass
    return doc.name
