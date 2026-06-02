import frappe
from frappe.model.document import Document

# Soglie di mappatura score -> livello di rischio
RISK_THRESHOLDS = [
	(85, "Critico"),
	(60, "Alto"),
	(30, "Medio"),
	(0, "Basso"),
]


class InvestigationEntity(Document):
	def before_save(self):
		self.calculate_risk_score()
		self.check_blacklist()

	def calculate_risk_score(self):
		# Somma i punti dei Risk Indicator e mappa il livello
		score = sum((ri.points or 0) for ri in (self.risk_indicators or []))
		self.risk_score = float(score)
		for threshold, level in RISK_THRESHOLDS:
			if score >= threshold:
				self.risk_level = level
				break

	def check_blacklist(self):
		# Blacklist Entry viene introdotta nel Blocco 4: salta se non ancora presente
		if not frappe.db.has_table("Blacklist Entry"):
			return
		match = frappe.db.get_value(
			"Blacklist Entry",
			{"entry_value": self.primary_identifier, "is_active": 1},
			"name",
		)
		if match:
			self.status = "Blacklisted"
			self.blacklist_ref = match

	def on_update(self):
		# Notifica i manager se il rischio supera la soglia operativa
		if (self.risk_score or 0) >= 60:
			notify_managers(self)


def notify_managers(entity):
	# Notifica best-effort agli Investigation Manager; non blocca il salvataggio
	try:
		managers = frappe.get_all(
			"Has Role",
			filters={"role": "Investigation Manager", "parenttype": "User"},
			pluck="parent",
		)
		for user in set(managers):
			if user in ("Administrator", "Guest"):
				continue
			notification = frappe.new_doc("Notification Log")
			notification.update({
				"subject": f"Entita ad alto rischio: {entity.primary_identifier} (score {entity.risk_score})",
				"for_user": user,
				"type": "Alert",
				"document_type": "Investigation Entity",
				"document_name": entity.name,
			})
			notification.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "InvestigationEntity notify_managers")
