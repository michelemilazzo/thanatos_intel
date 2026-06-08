import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class PartyPayout(Document):
    def validate(self):
        self._set_ron_accounting()

    def _set_ron_accounting(self):
        """Importo transato in EUR; corrispettivo contabile in RON (lei) al cambio ECB."""
        self.ron_ccy = "RON"
        if not self.amount:
            self.amount_ron = 0
            self.exchange_rate_ron = 0
            return
        from thanatos_intel.thanatos_core.currency.converter import convert
        src = self.currency or "EUR"
        self.exchange_rate_ron = convert(1, "RON", src)
        self.amount_ron = convert(self.amount, "RON", src)

    @frappe.whitelist()
    def execute(self):
        from thanatos_intel.billing.revenue_engine import execute_payout
        return execute_payout(self)
