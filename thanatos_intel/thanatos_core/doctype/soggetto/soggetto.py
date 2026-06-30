import frappe
from frappe.model.document import Document

# doctype-ruolo che possono collegarsi a un Soggetto: (doctype, etichetta ruolo, campo nome)
ROLE_DOCTYPES = [
    ("Customer", "Cliente", "customer_name"),
    ("Investigator", "Operatore/Investigatore", "full_name"),
    ("Intelligence Contact", "Contatto Intelligence", "full_name"),
    ("Reseller", "Collaboratore/Reseller", "reseller_name"),
    ("Employee", "Dipendente", "employee_name"),
]


class Soggetto(Document):
    def validate(self):
        self.refresh_roles()

    def refresh_roles(self):
        found = []
        for dt, label, _f in ROLE_DOCTYPES:
            try:
                if frappe.db.exists("DocType", dt) and frappe.db.has_column(dt, "soggetto"):
                    if frappe.db.exists(dt, {"soggetto": self.name}):
                        found.append(label)
            except Exception:
                pass
        self.ruoli = " · ".join(found) if found else "(nessun ruolo collegato)"
