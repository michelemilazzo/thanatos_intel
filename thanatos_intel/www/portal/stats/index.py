import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/stats"
        raise frappe.Redirect
    from thanatos_intel.analytics import _is_staff, portal_stats
    if not _is_staff():
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect
    context.title = "Statistiche — Thanatos"
    context.s = portal_stats(30)
    from thanatos_intel import gsc as _gsc
    context.gsc = _gsc.gsc_status()
    context.rankings = _gsc.latest_rankings(25)
    context.rank_summary = _gsc.ranking_summary()
    context.no_cache = 1
    return context
