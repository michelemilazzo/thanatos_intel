import frappe

@frappe.whitelist()
def get_case_activity(case_name):
    if not case_name:
        return []

    comments=frappe.get_all(
        "Comment",
        filters={"reference_name":case_name},
        fields=["creation","content","comment_type"],
        order_by="creation desc",
        limit=20
    )

    return comments
