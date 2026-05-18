import frappe


def get_country_kpis():
    countries=["Italy","Canada","UK","Germany","USA"]
    data={}
    for country in countries:
        data[country]=frappe.db.count(
            "Visa Study Case",
            {"destination_country":country}
        )
    return data
