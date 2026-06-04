import frappe


def get_context(context):
    context.no_cache = 1
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/ddd"
        raise frappe.Redirect
    name = frappe.form_dict.get("name")
    if not name or not frappe.db.exists("Diplomatic Eligibility Case", name):
        frappe.local.flags.redirect_location = "/portal/ddd"
        raise frappe.Redirect

    case = frappe.get_doc("Diplomatic Eligibility Case", name)
    context.case = case
    context.title = f"Case {name}"
    context.applicant = (frappe.get_doc("Applicant Profile", case.applicant)
                         if case.applicant else None)
    context.country = (frappe.get_doc("Country Framework", case.country)
                       if case.country else None)
    context.documents = frappe.get_all("Required Document",
        filters={"ddd_case": name},
        fields=["name", "document_type", "status", "attached_file",
                "passport_analysis"])
    context.compliance = frappe.get_all("Compliance Check",
        filters={"ddd_case": name},
        fields=["name", "check_type", "outcome", "officer", "notes"])
    context.screenings = frappe.get_all("Sanctions Screening",
        filters={"ddd_case": name},
        fields=["name", "screening_type", "source", "matches_found",
                "outcome", "screened_on"])
    context.opinions = frappe.get_all("Legal Opinion",
        filters={"ddd_case": name},
        fields=["name", "conclusion", "legal_officer", "issued_on"])
    context.mandates = frappe.get_all("Agency Mandate",
        filters={"ddd_case": name},
        fields=["name", "subject_matter", "fee_total", "status",
                "mandate_pdf", "signed_on"])
    context.dossiers = frappe.get_all("Final Dossier",
        filters={"ddd_case": name},
        fields=["name", "version", "decision", "dossier_pdf",
                "generated_on"])
    context.audit = frappe.get_all("Diplomatic Audit Log",
        filters={"ddd_case": name},
        fields=["ts", "user", "event_type", "old_value", "new_value", "reason"],
        order_by="ts desc", limit=30)
    return context
