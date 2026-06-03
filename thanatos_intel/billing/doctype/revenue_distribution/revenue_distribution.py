import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class RevenueDistribution(Document):
    def before_insert(self):
        self.net_amount = (float(self.gross_amount or 0)
                           - float(self.stripe_fee or 0)
                           - float(self.vat_amount or 0))

    @frappe.whitelist()
    def compute_split(self):
        from thanatos_intel.billing.revenue_engine import compute_distribution
        compute_distribution(self)
        self.save(ignore_permissions=True)
        return {"net": self.net_amount, "thanatos": self.thanatos_share, "mmos": self.mmos_share}

    @frappe.whitelist()
    def queue_payouts(self):
        from thanatos_intel.billing.revenue_engine import queue_third_party_payouts
        result = queue_third_party_payouts(self)
        self.status = "Payouts Queued"
        self.save(ignore_permissions=True)
        return result
