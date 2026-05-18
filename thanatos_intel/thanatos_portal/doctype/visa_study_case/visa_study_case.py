from frappe.model.document import Document

STUDY_ORIGIN_CHECKLIST = [
    "Valid passport and copies",
    "Biometric photos",
    "Visa application form",
    "Admission or pre-enrolment letter",
    "Diploma or degree certificate",
    "Official translations and legalisations",
    "Exam transcript",
    "Accommodation proof",
    "Health insurance policy",
    "Financial proof and bank statements",
    "Appointment receipt",
]

STUDY_DESTINATION_CHECKLIST = [
    "University eligibility check",
    "University application or pre-enrolment support",
    "Admission letter follow-up",
    "Accommodation arrangement",
    "Health insurance support",
    "Visa dossier review",
    "Residence permit preparation",
    "Fiscal code support",
    "Immigration appointment support",
]

FAMILY_REUNIFICATION_ORIGIN_CHECKLIST = [
    "Valid passport and copies",
    "Biometric photos",
    "Family reunification visa application form",
    "Marriage certificate or birth certificate",
    "Official translations and legalisations",
    "Criminal record certificate if required",
    "Proof of family relationship",
    "Sponsor identity document copy",
    "Appointment receipt",
]

FAMILY_REUNIFICATION_DESTINATION_CHECKLIST = [
    "Sponsor residence permit or citizenship document",
    "Sponsor accommodation suitability proof",
    "Sponsor income proof",
    "Family status / household certificate",
    "Nulla osta or family clearance if required",
    "Consular dossier review",
    "Document translation review",
    "Appointment and submission support",
    "Residence permit preparation after arrival",
]

class VisaStudyCase(Document):
    def validate(self):
        self.set_budget_conversion()
        self.populate_default_checklists()
        self.calculate_completion_percent()

    def set_budget_conversion(self):
        if self.planned_budget_eur and not self.planned_budget_cny:
            self.planned_budget_cny = round(float(self.planned_budget_eur) * 8, 2)

    def get_origin_checklist_template(self):
        if self.case_category in ("Family Reunification", "Family Cohesion", "Family Member Accompanying"):
            return FAMILY_REUNIFICATION_ORIGIN_CHECKLIST
        return STUDY_ORIGIN_CHECKLIST

    def get_destination_checklist_template(self):
        if self.case_category in ("Family Reunification", "Family Cohesion", "Family Member Accompanying"):
            return FAMILY_REUNIFICATION_DESTINATION_CHECKLIST
        return STUDY_DESTINATION_CHECKLIST

    def populate_default_checklists(self):
        if not self.origin_country_checklist:
            for item in self.get_origin_checklist_template():
                self.append("origin_country_checklist", {
                    "check_item": item,
                    "responsible_party": "Student",
                })

        if not self.destination_country_checklist:
            for item in self.get_destination_checklist_template():
                self.append("destination_country_checklist", {
                    "check_item": item,
                    "responsible_party": "Italy Agency",
                })

    def calculate_completion_percent(self):
        rows = list(self.origin_country_checklist or []) + list(self.destination_country_checklist or [])
        if not rows:
            self.completion_percent = 0
            return

        completed = sum(1 for row in rows if row.completed)
        self.completion_percent = round((completed / len(rows)) * 100, 2)
