import frappe

STAFF_ROLES = {
    "System Manager", "Administrator",
    "Thanatos Director", "Thanatos Compliance Officer", "Thanatos Legal Officer",
    "Thanatos Auditor", "Thanatos Supervisor", "Thanatos Analyst",
    "Thanatos Investigator", "Thanatos Intake Officer",
}


def is_ddd_staff(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(STAFF_ROLES & set(frappe.get_roles(user)))


def client_applicants(user=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        return []
    return frappe.get_all("Applicant Profile", filters={"email": user}, pluck="name")


def can_access_case(case_name, user=None):
    user = user or frappe.session.user
    if is_ddd_staff(user):
        return True
    applicant = frappe.db.get_value("Diplomatic Eligibility Case", case_name, "applicant")
    return bool(applicant and applicant in set(client_applicants(user)))


def can_access_mandate(mandate, user=None):
    user = user or frappe.session.user
    if is_ddd_staff(user):
        return True
    applicant = frappe.db.get_value("Agency Mandate", mandate, "applicant")
    return bool(applicant and applicant in set(client_applicants(user)))
