import frappe


PAID_STATUS = "Paid"


def run(order_name):
    """Evaluate a Visa Case Order and return the next workflow action."""
    if not order_name:
        return {"valid": False, "reason": "missing_order_name", "next_step": "stop"}

    if not frappe.db.exists("Visa Case Order", order_name):
        return {"valid": False, "reason": "order_not_found", "next_step": "stop"}

    order = frappe.get_doc("Visa Case Order", order_name)
    paid = order.payment_status == PAID_STATUS

    if not paid:
        return {
            "valid": True,
            "paid": False,
            "existing_case": order.visa_study_case,
            "next_step": "wait_for_payment",
        }

    if order.visa_study_case:
        return {
            "valid": True,
            "paid": True,
            "existing_case": order.visa_study_case,
            "next_step": "case_exists",
        }

    return {
        "valid": True,
        "paid": True,
        "existing_case": None,
        "next_step": "create_case",
    }


def create_case_from_order(order_name):
    """Create a Visa Study Case from a paid order if missing."""
    state = run(order_name)
    if not state.get("valid") or state.get("next_step") != "create_case":
        return state

    order = frappe.get_doc("Visa Case Order", order_name)
    case = frappe.get_doc({
        "doctype": "Visa Study Case",
        "student_full_name": order.customer,
        "case_status": "Pending",
    })
    case.insert(ignore_permissions=True)

    order.visa_study_case = case.name
    order.portal_enabled = 1
    order.save(ignore_permissions=True)

    state["created_case"] = case.name
    state["next_step"] = "generate_document_requests"
    return state
