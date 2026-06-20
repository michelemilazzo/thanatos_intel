import frappe


@frappe.whitelist()
def notify_document_uploaded(case_name, document_name):
    return {
        'message': f'Document {document_name} uploaded for case {case_name}',
        'status': 'queued'
    }


@frappe.whitelist()
def portal_action_count():
    """Conta le azioni pending per il cliente loggato: step Awaiting Client + pagamenti."""
    if frappe.session.user == "Guest":
        return {"count": 0}
    from thanatos_intel.workflow.api import _client_for_user, _is_operator
    if _is_operator(frappe.session.user):
        return {"count": 0}
    cl = _client_for_user(frappe.session.user)
    if not cl:
        return {"count": 0}

    awaiting = frappe.db.sql("""
        SELECT COUNT(DISTINCT ic.name)
        FROM `tabInvestigation Case` ic
        JOIN `tabCase Step` cs ON cs.parent = ic.name
        WHERE ic.client = %s
          AND ic.status NOT IN ('Closed','Cancelled')
          AND cs.status = 'Awaiting Client'
    """, cl.name)[0][0] or 0

    pending_pay = frappe.db.count("Usage Event", {
        "client": cl.name,
        "status": "Pending",
    })

    return {"count": int(awaiting) + int(pending_pay)}
