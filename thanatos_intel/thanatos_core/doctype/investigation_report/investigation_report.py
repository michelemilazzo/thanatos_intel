import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class InvestigationReport(Document):
    def validate(self):
        if not self.report_status:
            self.report_status = "Draft"

    def before_submit(self):
        if not self.pdf_file:
            self.generate_pdf()
        if self.report_status not in ("Final", "Delivered"):
            self.report_status = "Final"

    @frappe.whitelist()
    def generate_pdf(self):
        from thanatos_intel.reporting.pdf_report import build_report_pdf
        file_url, sha = build_report_pdf(self.name)
        self.pdf_file = file_url
        self.pdf_hash = sha
        self.generated_at = now_datetime()
        self.signed_by = frappe.session.user
        self.db_update()
        frappe.db.commit()
        return {"file_url": file_url, "sha256": sha}
