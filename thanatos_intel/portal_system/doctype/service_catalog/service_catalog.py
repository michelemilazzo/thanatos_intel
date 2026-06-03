import frappe
from frappe.model.document import Document

# Tipi di cliente che ottengono sconti automatici
DISCOUNT_MAP = {
	"Law Firm": "discount_law_firm",
	"Accounting Firm": "discount_accountant",
	# Enterprise = sconto su client_type=Company con subscription_status=Enterprise
}


class ServiceCatalog(Document):
	def before_save(self):
		# Allinea price (default) come media del range
		if self.price_min and self.price_max:
			if self.price_min > self.price_max:
				frappe.throw("Price Min non può essere maggiore di Price Max")
			self.price = float(self.price_min + self.price_max) / 2.0
		elif self.price_min:
			self.price = self.price_min
		elif self.price_max:
			self.price = self.price_max

	@staticmethod
	def get_price(service_code: str, client_type: str = "Individual", is_enterprise: bool = False) -> float:
		# Ritorna il prezzo applicabile con sconto in base al tipo cliente
		s = frappe.get_cached_doc("Service Catalog", service_code)
		base = float(s.price or 0)
		discount = 0.0
		if is_enterprise:
			discount = float(s.discount_enterprise or 0)
		else:
			field = DISCOUNT_MAP.get(client_type)
			if field:
				discount = float(s.get(field) or 0)
		return round(base * (1.0 - discount / 100.0), 2)
