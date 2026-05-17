import frappe

READ_ROLES = ("Thanatos Investigator", "Thanatos Analyst", "Thanatos Supervisor")
WRITE_ROLES = ("Thanatos Investigator", "Thanatos Supervisor")
SUPERVISOR_ROLES = ("Thanatos Supervisor",)


def has_thanatos_role(*roles):
    user_roles = set(frappe.get_roles())
    return bool(user_roles.intersection(roles))


def can_read_thanatos_doc(doc, user=None):
    return has_thanatos_role(*READ_ROLES)


def can_write_thanatos_doc(doc, user=None):
    return has_thanatos_role(*WRITE_ROLES)


def can_supervise_thanatos_doc(doc, user=None):
    return has_thanatos_role(*SUPERVISOR_ROLES)
