"""Collega HD Ticket a Investigation Case e notifica l'investigatore assegnato."""
import frappe


def on_ticket_created(doc, method=None):
    """Notifica all'investigatore responsabile del caso."""
    case_name = doc.get("investigation_case")
    if not case_name:
        return
    try:
        case = frappe.get_doc("Investigation Case", case_name)
        # Notifica all'investigatore assegnato (se presente)
        assigned_to = case.get("assigned_to") or case.get("investigator")
        if assigned_to:
            frappe.sendmail(
                recipients=[assigned_to],
                subject=f"Nuovo ticket: {doc.subject} — {case_name}",
                message=(
                    f"<p>Il cliente ha aperto un ticket di supporto per il caso "
                    f"<strong>{case.case_title or case_name}</strong>.</p>"
                    f"<p><strong>Oggetto:</strong> {doc.subject}</p>"
                    f"<p><a href='/support/tickets/{doc.name}'>Apri ticket →</a></p>"
                ),
                delayed=True,
            )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "helpdesk_bridge.on_ticket_created")


@frappe.whitelist()
def create_ticket_for_case(case_name: str, subject: str, description: str) -> dict:
    """API per creare ticket dal portal."""
    frappe.has_permission("Investigation Case", "read", case_name, throw=True)
    case = frappe.get_doc("Investigation Case", case_name)
    ticket = frappe.get_doc({
        "doctype": "HD Ticket",
        "subject": subject,
        "description": description,
        "investigation_case": case_name,
        "raised_by": frappe.session.user,
    })
    ticket.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "ticket": ticket.name, "url": f"/support/tickets/{ticket.name}"}


@frappe.whitelist()
def get_tickets_for_case(case_name: str) -> list:
    """Restituisce i ticket collegati al caso (per il portal)."""
    frappe.has_permission("Investigation Case", "read", case_name, throw=True)
    return frappe.get_all(
        "HD Ticket",
        filters={"investigation_case": case_name},
        fields=["name", "subject", "status", "creation", "raised_by"],
        order_by="creation desc",
        limit=20,
    )
