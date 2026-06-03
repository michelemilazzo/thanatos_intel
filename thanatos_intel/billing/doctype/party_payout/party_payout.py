import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class PartyPayout(Document):
    @frappe.whitelist()
    def execute(self):
        from thanatos_intel.billing.revenue_engine import execute_payout
        return execute_payout(self)
