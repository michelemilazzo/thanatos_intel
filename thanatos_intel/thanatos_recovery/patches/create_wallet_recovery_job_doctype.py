import frappe
import json

def execute():
    """Create Wallet Recovery Job DocType if it doesn't exist"""
    doctype_path = frappe.get_app_path("thanatos_intel", 
        "thanatos_recovery/doctype/wallet_recovery_job/wallet_recovery_job.json")
    
    with open(doctype_path, "r") as f:
        doctype_dict = json.load(f)
    
    if not frappe.db.exists("DocType", "Wallet Recovery Job"):
        doc = frappe.new_doc("DocType")
        doc.update(doctype_dict)
        doc.custom = 1
        doc.insert(ignore_if_duplicate=True)
        frappe.logger().info("✅ Created Wallet Recovery Job DocType")
    else:
        frappe.logger().info("✅ Wallet Recovery Job DocType already exists")

