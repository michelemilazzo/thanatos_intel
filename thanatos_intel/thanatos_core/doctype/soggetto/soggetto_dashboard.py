from frappe import _


def get_data():
    return {
        "fieldname": "soggetto",
        "transactions": [
            {"label": _("Ruoli collegati"),
             "items": ["Customer", "Employee", "Investigator", "Intelligence Contact"]},
        ],
    }
