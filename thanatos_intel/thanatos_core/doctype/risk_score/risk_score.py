from frappe.model.document import Document

class RiskScore(Document):
    def validate(self):
        if self.score is None:
            self.score=0
