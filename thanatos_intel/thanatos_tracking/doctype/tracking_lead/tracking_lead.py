"""Tracking Lead — singolo indizio raccolto su un Target."""
import frappe
from frappe.model.document import Document


class TrackingLead(Document):
    def before_insert(self):
        if not self.reported_by:
            self.reported_by = frappe.session.user

    def validate(self):
        if self.verified and not self.verified_by:
            self.verified_by = frappe.session.user
            if self.status == "New":
                self.status = "Verified"
        if not self.verified:
            self.verified_by = None

    def on_update(self):
        self._sync_counters()

    def on_trash(self):
        self._sync_counters()

    def _sync_counters(self):
        if self.target:
            frappe.get_doc("Tracking Target", self.target).refresh_lead_count()
        if self.trackathon_session:
            try:
                frappe.get_doc("Trackathon Session", self.trackathon_session).refresh_counters()
            except Exception:
                pass
