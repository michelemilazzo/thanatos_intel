import frappe
from frappe.model.document import Document


class CryptoScamIntelligence(Document):
    def validate(self):
        if self.raw_html and not self.raw_hash:
            import hashlib
            self.raw_hash = hashlib.sha256(self.raw_html.encode("utf-8")).hexdigest()
