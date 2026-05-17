from frappe.model.document import Document

class InvestigationEntity(Document):
    def validate(self):
        if self.entity_name:
            self.entity_name=self.entity_name.strip()
