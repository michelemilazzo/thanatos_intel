import frappe


def get_payment_kpis():
    return {
        "paid_orders": frappe.db.count("Visa Case Order", {"payment_status": "Paid"}),
        "pending_orders": frappe.db.count("Visa Case Order", {"payment_status": "Pending"}),
        "partial_orders": frappe.db.count("Visa Case Order", {"payment_status": "Partially Paid"}),
        "cancelled_orders": frappe.db.count("Visa Case Order", {"payment_status": "Cancelled"}),
    }
