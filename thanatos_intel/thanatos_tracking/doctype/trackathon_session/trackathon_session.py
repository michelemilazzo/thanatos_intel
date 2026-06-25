"""Trackathon Session — sprint OSINT collaborativo a tempo su uno o piu' target."""
import frappe
from frappe.model.document import Document


class TrackathonSession(Document):
    def refresh_counters(self):
        names = [t.target for t in (self.targets or []) if t.target]
        total = verified = 0
        per_target = {}
        if names:
            rows = frappe.get_all(
                "Tracking Lead",
                filters={"trackathon_session": self.name},
                fields=["target", "verified"],
            )
            total = len(rows)
            verified = sum(1 for r in rows if r.verified)
            for r in rows:
                per_target[r.target] = per_target.get(r.target, 0) + 1
        self.db_set("leads_count", total)
        self.db_set("verified_leads", verified)
        for t in (self.targets or []):
            frappe.db.set_value("Trackathon Target Link", t.name, "leads", per_target.get(t.target, 0))

    def refresh_participant_stats(self):
        for p in (self.participants or []):
            cnt = frappe.db.count(
                "Tracking Lead",
                {"trackathon_session": self.name, "reported_by": p.user},
            )
            frappe.db.set_value("Trackathon Participant", p.name, "leads_contributed", cnt)


@frappe.whitelist()
def refresh(session):
    doc = frappe.get_doc("Trackathon Session", session)
    doc.refresh_counters()
    doc.refresh_participant_stats()
    return {"leads_count": doc.leads_count, "verified_leads": doc.verified_leads}
