import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, today, flt

NORMALIZE = ("Email", "Domain", "IP", "Wallet", "IBAN")


class BlacklistReport(Document):
    def validate(self):
        self.entry_value = (self.entry_value or "").strip()
        if self.entry_type in NORMALIZE:
            self.entry_value = self.entry_value.lower()

    def on_update(self):
        if self.status == "Approved" and not flt(self.bonus_amount) and not self.blacklist_entry:
            self._approve()

    def _approve(self):
        entry = self._upsert_entry()
        self.db_set("blacklist_entry", entry, update_modified=False)
        self.db_set("reviewed_by", frappe.session.user, update_modified=False)
        self.db_set("reviewed_on", now_datetime(), update_modified=False)

        # dedup bonus: stesso reporter+valore già premiato → nessun nuovo bonus
        prior = frappe.db.exists("Blacklist Report", {
            "reporter": self.reporter, "entry_type": self.entry_type,
            "entry_value": self.entry_value, "bonus_amount": [">", 0],
            "name": ["!=", self.name]})
        bonus = 0
        if not prior:
            from thanatos_intel.billing.credits import grant_credit, monthly_earned
            amt = flt(frappe.db.get_single_value("Thanatos Billing Settings", "report_bonus_amount")) or 2
            cap = flt(frappe.db.get_single_value("Thanatos Billing Settings", "report_bonus_monthly_cap")) or 20
            bonus = min(amt, max(0, cap - monthly_earned(self.reporter)))
            if bonus > 0:
                grant_credit(self.reporter, bonus, "Blacklist Report", self.name,
                             f"Bonus segnalazione {self.entry_type}: {self.entry_value}")
        self.db_set("bonus_amount", bonus, update_modified=False)

    def _upsert_entry(self):
        existing = frappe.db.get_value("Blacklist Entry",
                                       {"entry_type": self.entry_type, "entry_value": self.entry_value})
        if existing:
            doc = frappe.get_doc("Blacklist Entry", existing)
            doc.occurrences = (doc.occurrences or 0) + 1
            doc.last_seen = today()
            doc.save(ignore_permissions=True)
            return existing
        doc = frappe.get_doc({
            "doctype": "Blacklist Entry", "entry_type": self.entry_type, "entry_value": self.entry_value,
            "source": "Community", "risk_level": "Medium", "occurrences": 1, "is_active": 1,
            "verified": 0, "last_seen": today(), "reason": self.reason,
        })
        doc.insert(ignore_permissions=True)
        return doc.name
