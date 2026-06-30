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
        self._ensure_one_default("indirizzi")
        self._ensure_one_default("ibans")
        self._sync_primary_email()

    def _ensure_one_default(self, table):
        rows = self.get(table) or []
        defaults = [r for r in rows if r.get("is_default")]
        if rows and not defaults:
            rows[0].is_default = 1          # il primo inserito = predefinito
        elif len(defaults) > 1:
            for r in defaults[1:]:
                r.is_default = 0            # un solo predefinito

    def _sync_primary_email(self):
        """L'email primaria (campo email) e' sempre presente tra gli alias ed e' la
        predefinita; gli altri indirizzi restano come alias non predefiniti."""
        primary = (self.email or "").strip().lower()
        if not primary:
            return
        match = None
        for r in (self.get("emails") or []):
            if (r.email or "").strip().lower() == primary:
                match = r
        if not match:
            self.append("emails", {"email": self.email, "etichetta": "primaria"})
            match = (self.get("emails") or [])[-1]
        for r in (self.get("emails") or []):
            r.is_default = 1 if r is match else 0

    def default_address(self):
        for r in (self.indirizzi or []):
            if r.is_default:
                return r
        return (self.indirizzi or [None])[0]

    def default_iban(self):
        for r in (self.ibans or []):
            if r.is_default:
                return r
        return (self.ibans or [None])[0]

    def address(self, tipo=None):
        """Indirizzo specifico per tipo (es. Fatturazione); altrimenti il predefinito."""
        if tipo:
            for r in (self.indirizzi or []):
                if r.tipo == tipo:
                    return r
        return self.default_address()

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
