# Copyright (c) 2026, OneKeyCo
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InvestigationCase(Document):
    """Main investigative case container.

    This controller intentionally stays lightweight for MVP v0.1.
    Business logic will be expanded progressively with evidence,
    risk scoring, reporting and OSINT workflows.
    """

    def validate(self):
        self.set_default_status()
        self.normalize_case_title()

    def set_default_status(self):
        if not self.status:
            self.status = "Open"

    def normalize_case_title(self):
        if self.case_title:
            self.case_title = self.case_title.strip()

    def before_save(self):
        self.add_audit_note()

    def add_audit_note(self):
        """Placeholder for future immutable audit trail integration."""
        return None
