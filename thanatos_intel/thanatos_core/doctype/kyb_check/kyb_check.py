import frappe
from frappe.model.document import Document


class KYBCheck(Document):
    def on_update(self):
        if self.status in ("Approved", "Rejected"):
            if not self.reviewed_by:
                self.db_set("reviewed_by", frappe.session.user, update_modified=False)
            if not self.reviewed_on:
                self.db_set("reviewed_on", frappe.utils.now(), update_modified=False)
        _sync_client_status(self)


def _sync_client_status(doc):
    mapping = {"Approved": "Verified", "Rejected": "Rejected", "Pending": "Pending", "In Review": "In Review"}
    status = mapping.get(doc.status, doc.status)
    frappe.db.set_value("Investigation Client", doc.client, "kyb_status", status, update_modified=False)
