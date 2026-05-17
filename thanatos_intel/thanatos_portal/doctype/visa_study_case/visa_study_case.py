from frappe.model.document import Document

CHINA_DEFAULT_CHECKLIST = [
    "Valid passport and copies",
    "Biometric photos",
    "National D visa application form",
    "Admission or pre-enrolment letter",
    "Diploma or degree certificate",
    "Official translations and legalisations",
    "Exam transcript",
    "Accommodation proof",
    "Health insurance policy",
    "Financial proof and bank statements",
    "Prenot@mi appointment receipt",
]

ITALY_AGENCY_DEFAULT_CHECKLIST = [
    "University eligibility check",
    "University application or pre-enrolment support",
    "Admission letter follow-up",
    "Accommodation arrangement",
    "Health insurance support",
    "Visa dossier review",
    "Residence permit postal kit preparation",
    "Fiscal code support",
    "Questura appointment support",
]

class VisaStudyCase(Document):
    def validate(self):
        self.set_budget_conversion()
        self.populate_default_checklists()
        self.calculate_completion_percent()

    def set_budget_conversion(self):
        if self.planned_budget_eur and not self.planned_budget_cny:
            self.planned_budget_cny = round(float(self.planned_budget_eur) * 8, 2)

    def populate_default_checklists(self):
        if not self.china_checklist:
            for item in CHINA_DEFAULT_CHECKLIST:
                self.append("china_checklist", {
                    "check_item": item,
                    "responsible_party": "China Student",
                })

        if not self.italy_checklist:
            for item in ITALY_AGENCY_DEFAULT_CHECKLIST:
                self.append("italy_checklist", {
                    "check_item": item,
                    "responsible_party": "Italy Agency",
                })

    def calculate_completion_percent(self):
        rows = list(self.china_checklist or []) + list(self.italy_checklist or [])
        if not rows:
            self.completion_percent = 0
            return

        completed = sum(1 for row in rows if row.completed)
        self.completion_percent = round((completed / len(rows)) * 100, 2)
