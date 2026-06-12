"""Helper esposti ai template Jinja (sandbox sicuro non espone tutto di frappe)."""
import frappe


def user_roles(user=None):
    """Ruoli dell'utente: frappe.get_roles non e nel namespace jinja sicuro."""
    return frappe.get_roles(user or frappe.session.user)
