import frappe
from frappe import _

no_cache = 1


def get_context(context):
    """Pagina SEO cliente: mostra keyword + analytics per il sito Thanatos."""
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/seo"
        raise frappe.Redirect

    user = frappe.session.user

    # Carica le keyword SEO (clienti vedono le keyword di thanatos.agency)
    # Per ora: mostra tutte le keyword active (potrebbe essere filtrate per sito in futuro)
    keywords = frappe.get_all(
        "SEO Keyword",
        filters={"is_active": 1},
        fields=["name", "keyword", "origin", "weight", "notes"],
        order_by="weight desc, modified desc",
        limit_page_length=100
    )

    # Conteggi per tipo origin
    origins = frappe.db.sql("""
        SELECT origin, COUNT(*) as count
        FROM `tabSEO Keyword`
        WHERE is_active = 1
        GROUP BY origin
    """, as_dict=True)

    context.user = user
    context.user_fullname = frappe.db.get_value("User", user, "full_name") or user
    context.keywords = keywords or []
    context.origins = {o['origin']: o['count'] for o in origins}
    context.csrf_token = frappe.sessions.get_csrf_token()

    return context
