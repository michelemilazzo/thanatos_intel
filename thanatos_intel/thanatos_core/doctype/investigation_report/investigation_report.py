from frappe.model.document import Document

class InvestigationReport(Document):
    def validate(self):
        if not self.report_status:
            self.report_status='Draft'
