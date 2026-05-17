from frappe import _


def get_data():
    return [
        {
            "module_name": "Thanatos Core",
            "category": "Modules",
            "label": _("Thanatos Intel"),
            "color": "navy",
            "icon": "octicon octicon-search",
            "type": "module",
            "description": _("Investigation cases, entities, evidence, reports and risk scoring."),
        }
    ]
