import frappe


@frappe.whitelist()
def osint_placeholder(query=None, target_type=None):
    """Safe MVP placeholder for future authorized OSINT connectors.

    This endpoint does not perform external collection yet. It only returns
    a normalized response shape that the UI and future services can use.
    """
    return {
        "status": "placeholder",
        "query": query,
        "target_type": target_type,
        "risk_score": 0,
        "classification": "Low",
        "notes": "External OSINT providers are not enabled in MVP baseline. Configure authorized providers before production use.",
    }
