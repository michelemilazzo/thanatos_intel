"""Helper esposti ai template Jinja (sandbox sicuro non espone tutto di frappe)."""
import frappe


def user_roles(user=None):
    """Ruoli dell'utente: frappe.get_roles non e nel namespace jinja sicuro."""
    return frappe.get_roles(user or frappe.session.user)


def portal_user(user=None):
    """Dati profilo per il chrome: nome, immagine, iniziali."""
    user = user or frappe.session.user
    if user in ("Guest", "", None):
        return {"name": "", "full_name": "", "image": "", "initials": ""}
    full_name = frappe.db.get_value("User", user, "full_name") or user
    image = frappe.db.get_value("User", user, "user_image") or ""
    parts = [p for p in full_name.replace(".", " ").split() if p]
    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "U"
    return {"name": user, "full_name": full_name, "image": image, "initials": initials}
