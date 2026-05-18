import frappe


def get_revenue_kpis():
    return {
        "active_packages": frappe.db.count("Visa Service Package", {"active": 1}),
        "total_orders": frappe.db.count("Visa Case Order"),
        "paid_orders": frappe.db.count("Visa Case Order", {"payment_status": "Paid"}),
    }
