import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AssetPosition(Document):
	def after_insert(self):
		# Aggiorna l'ultima posizione vista sull'asset
		frappe.db.set_value("Tracked Asset", self.tracked_asset, "last_seen",
		                    self.reported_at or now_datetime(), update_modified=False)
