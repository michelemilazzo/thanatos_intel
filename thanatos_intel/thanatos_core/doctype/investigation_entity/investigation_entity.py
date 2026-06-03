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
		# Blacklist Entry (Blocco 4): mappa entity_type -> Blacklist entry_type
		if not frappe.db.has_table("Blacklist Entry"):
			return
		type_map = {
			"Email": "Email", "Domain": "Domain", "IP": "IP",
			"Wallet": "Wallet", "Phone": "Phone",
			"Company": "Company", "Person": "Person",
		}
		bl_type = type_map.get(self.entity_type)
		# Normalizza valore
		val = (self.primary_identifier or "").strip()
		if bl_type in ("Email", "Domain", "IP", "Wallet"):
			val = val.lower()
		filters = {"entry_value": val, "is_active": 1}
		if bl_type:
			filters["entry_type"] = bl_type
		match = frappe.db.get_value("Blacklist Entry", filters, "name")
		if match:
			self.status = "Blacklisted"
			self.blacklist_ref = match
			# Incrementa hit counter
			try:
				from thanatos_intel.fraud_engine.doctype.blacklist_entry.blacklist_entry import BlacklistEntry
				BlacklistEntry.add_hit(val, bl_type)
			except Exception:
				pass

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
