import frappe


def get_case_category_kpis():
    categories=["Study","Family Reunification","Work","Business","Tourism"]
    data={}
    for category in categories:
        data[category]=frappe.db.count(
            "Visa Study Case",
            {"case_category":category}
        )
    return data
