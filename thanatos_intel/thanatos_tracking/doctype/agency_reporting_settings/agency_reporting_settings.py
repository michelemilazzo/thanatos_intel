import frappe
from frappe.model.document import Document


class AgencyReportingSettings(Document):
    pass


def email_for(agency):
    s = frappe.get_single("Agency Reporting Settings")
    return {
        "FBI": s.fbi_email,
        "Europol": s.europol_email,
        "Interpol": s.interpol_email,
        "National Police": s.national_police_email,
        "Other": s.other_email,
    }.get(agency) or ""
