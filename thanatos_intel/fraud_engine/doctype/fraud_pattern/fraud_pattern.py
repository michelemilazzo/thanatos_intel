import frappe
from frappe.model.document import Document


class FraudPattern(Document):
	def increment_cases_matched(self):
		self.cases_matched = (self.cases_matched or 0) + 1
		self.db_update()
