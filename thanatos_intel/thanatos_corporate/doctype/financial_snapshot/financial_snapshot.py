from frappe.model.document import Document


class FinancialSnapshot(Document):
    def before_save(self):
        if self.equity and self.equity > 0:
            self.debt_to_equity = round(((self.short_term_debt or 0) + (self.long_term_debt or 0)) / self.equity, 2)
        if self.total_liabilities and self.cash is not None and self.short_term_debt:
            self.current_ratio = round((self.total_assets or 0) / self.total_liabilities, 2) if self.total_liabilities else None
        d_e = self.debt_to_equity or 0
        if d_e > 5:
            self.insolvency_risk = "Critical"
        elif d_e > 2.5:
            self.insolvency_risk = "High"
        elif d_e > 1.5:
            self.insolvency_risk = "Medium"
        elif d_e > 0:
            self.insolvency_risk = "Low"
