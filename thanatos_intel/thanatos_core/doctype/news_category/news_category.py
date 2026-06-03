import frappe
from frappe.model.document import Document


class NewsCategory(Document):
	def before_save(self):
		if self.category_slug:
			self.category_slug = frappe.utils.slug(self.category_slug)
