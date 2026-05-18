import frappe


def get_dashboard_data():
    return {
        "fieldname": "visa_study_case",
        "transactions": [
            {
                "label": "Operations",
                "items": [
                    "Visa Document Request",
                    "Visa Case Order"
                ]
            }
        ]
    }
