import frappe


THANATOS_ROLES = [
    "Thanatos Investigator",
    "Thanatos Analyst",
    "Thanatos Supervisor",
]


def after_install():
    create_roles()


def create_roles():
    for role_name in THANATOS_ROLES:
        if not frappe.db.exists("Role", role_name):
            role = frappe.get_doc({
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
            })
            role.insert(ignore_permissions=True)
    frappe.db.commit()
