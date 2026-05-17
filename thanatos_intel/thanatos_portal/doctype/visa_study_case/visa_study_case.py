from frappe.model.document import Document

class VisaStudyCase(Document):
    def validate(self):
        if self.planned_budget_eur and not self.planned_budget_cny:
            self.planned_budget_cny = round(float(self.planned_budget_eur) * 8,2)
