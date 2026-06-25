import frappe
from frappe.model.document import Document


class Investigator(Document):
	def before_insert(self):
		if not (self.codename or "").strip():
			self.codename = _next_codename()

	def validate(self):
		if self.codename:
			self.codename = self.codename.strip()


def _next_codename():
	rows = frappe.get_all("Investigator", filters={"codename": ["like", "INV-%"]},
	                      pluck="codename")
	mx = 0
	for c in rows:
		try:
			n = int(str(c).split("-", 1)[1])
			mx = max(mx, n)
		except Exception:
			pass
	n = mx + 1
	code = f"INV-{n:02d}"
	while frappe.db.exists("Investigator", {"codename": code}):
		n += 1
		code = f"INV-{n:02d}"
	return code


def external_name(investigator):
	"""Nome da mostrare a clienti/esterni: codename se presente, mai il nome reale."""
	if not investigator:
		return ""
	code = frappe.db.get_value("Investigator", investigator, "codename")
	return code or "Investigatore Thanatos"
