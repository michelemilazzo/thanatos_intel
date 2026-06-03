import frappe
from frappe.model.document import Document


class NewsSource(Document):
	@frappe.whitelist()
	def fetch_now(self):
		from thanatos_intel.news.ingestion import fetch_source
		return fetch_source(self.name)
