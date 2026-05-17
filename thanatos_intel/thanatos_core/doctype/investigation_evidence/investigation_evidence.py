from frappe.model.document import Document

class InvestigationEvidence(Document):
    def validate(self):
        if self.hash_value:
            self.hash_value=self.hash_value.strip().lower()
