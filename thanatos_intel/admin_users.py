"""Gestione utenti e ruoli Thanatos — desk page thanatos-users (solo System Manager)."""
import frappe

# Profili assegnabili dalla UI (label -> ruoli Frappe). Set curato, non tocca
# ruoli di sistema sensibili oltre a quelli elencati.
STAFF_ROLES = [
    ("Thanatos Director", "Direttore"),
    ("Thanatos Supervisor", "Supervisore"),
    ("Thanatos Investigator", "Investigatore"),
    ("Thanatos Analyst", "Analista"),
    ("Thanatos Intake Officer", "Intake / Accoglienza"),
    ("Thanatos Legal Officer", "Ufficio Legale"),
    ("Thanatos Compliance Officer", "Compliance / AML"),
    ("Investigation Manager", "Investigation Manager"),
    ("Investigator", "Investigator (base)"),
    ("System Manager", "Amministratore di sistema"),
]
PORTAL_ROLES = [
    ("Investigation Client", "Cliente"),
    ("Affiliate", "Affiliato / Partner"),
]
MANAGED = [r for r, _ in STAFF_ROLES + PORTAL_ROLES]


def _guard():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Solo un amministratore può gestire ruoli e utenti.", frappe.PermissionError)


@frappe.whitelist()
def list_users(search=None, limit=200):
    _guard()
    filters = {"name": ["not in", ("Guest",)]}
    if search:
        filters["full_name"] = ["like", "%" + search + "%"]
    users = frappe.get_all(
        "User", filters=filters,
        fields=["name", "full_name", "user_type", "enabled", "last_login"],
        order_by="enabled desc, full_name asc", limit_page_length=int(limit))
    out = []
    for u in users:
        roles = set(frappe.get_roles(u.name))
        u["managed_roles"] = sorted(roles & set(MANAGED))
        u["is_staff"] = u.user_type == "System User"
        out.append(u)
    return {
        "users": out,
        "staff_roles": STAFF_ROLES,
        "portal_roles": PORTAL_ROLES,
    }


@frappe.whitelist()
def set_user_roles(user, roles):
    """Imposta i ruoli GESTITI dell'utente al set passato (JSON list).
    Tocca solo i ruoli in MANAGED: gli altri ruoli dell'utente restano invariati."""
    _guard()
    if isinstance(roles, str):
        roles = frappe.parse_json(roles)
    roles = set(roles or []) & set(MANAGED)
    if user == "Administrator":
        frappe.throw("L'utente Administrator non è modificabile da qui.")
    doc = frappe.get_doc("User", user)

    current = set(frappe.get_roles(user))
    current_managed = current & set(MANAGED)
    to_add = roles - current_managed
    to_remove = current_managed - roles

    # user_type coerente: se assegno un ruolo staff -> System User; se solo portale -> Website User
    staff_set = {r for r, _ in STAFF_ROLES}
    if roles & staff_set:
        if doc.user_type != "System User":
            doc.user_type = "System User"
    elif roles & {r for r, _ in PORTAL_ROLES}:
        if doc.user_type != "Website User":
            doc.user_type = "Website User"

    # rimuovi
    if to_remove:
        doc.set("roles", [r for r in doc.roles if r.role not in to_remove])
    # aggiungi
    for r in to_add:
        doc.append("roles", {"role": r})
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "added": sorted(to_add), "removed": sorted(to_remove),
            "user_type": doc.user_type}
