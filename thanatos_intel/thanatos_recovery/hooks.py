"""
Hooks per thanatos_recovery module (da aggiungere a thanatos_intel/thanatos_recovery/hooks.py)
"""

import frappe


# App metadata
app_name = "thanatos_recovery"
app_title = "Thanatos Recovery"
app_publisher = "OneKey"
app_description = "Wallet recovery tool - Offline seed recovery for Thanatos"
app_email = "dev@onekeyco.com"
app_license = "proprietary"
app_version = "0.1.0"


# Frappe permissions
has_permission = {}


# Fixtures (auto-import di DocTypes, etc)
fixtures = [
    {
        "doctype": "DocType",
        "name": "Wallet Recovery Job",
        "filters": {
            "module": "Thanatos Core"
        }
    }
]


# Scheduler events
scheduler_events = {
    "daily": [
        "thanatos_intel.thanatos_recovery.api.vault_manager.cleanup_expired_recoveries"
    ]
}


# Hooks per Investigation Case
doc_events = {
    "Investigation Case": {
        "after_insert": "thanatos_intel.thanatos_recovery.api.hooks.on_case_created",
        "on_trash": "thanatos_intel.thanatos_recovery.api.hooks.on_case_deleted"
    }
}


# Sidebar/Sidebar Extensions
sidebar_config = {
    "Investigation Case": {
        "items": [
            {
                "label": "Wallet Recovery",
                "route": "/app/wallet-recovery-job",
                "icon": "lock"
            }
        ]
    }
}


# Setup (eseguito on_site_install)
def setup():
    """Eseguito al primo install del modulo"""
    frappe.logger().info("Initializing Thanatos Recovery module...")
    from thanatos_intel.thanatos_recovery.api.vault_manager import ensure_vault_exists
    ensure_vault_exists()
    frappe.logger().info("Vault initialized")


# Assets - Load form scripts
app_include_js = "/assets/thanatos_intel/js/wallet_recovery_form.js"
app_include_css = "/assets/thanatos_intel/css/wallet_recovery.css"


# Permissions
def has_wallet_recovery_permission(user, doctype, doc=None, ptype="read"):
    """
    Custom permission check per Wallet Recovery Job
    Può essere limitato a staff solo
    """
    roles = frappe.get_roles(user)

    if "Investigation Manager" in roles or "Investigator" in roles:
        return True

    return False


# Migrate (su bench update)
migrations = []
