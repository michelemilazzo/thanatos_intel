__version__ = '0.0.1'

# Patch: impedisce che Drive appaia nelle app per gli utenti Investigation Client,
# altrimenti get_default_path() restituisce /drive sovrascrivendo il portal home_page.
try:
    import drive.api.product as _drive_product

    _orig_drive_access = _drive_product.access_app

    def _patched_drive_access():
        try:
            import frappe
            PORTAL_ROLES = {"Investigation Client", "Affiliate"}
            if PORTAL_ROLES & set(frappe.get_roles()):
                return False
        except Exception:
            pass
        return _orig_drive_access()

    _drive_product.access_app = _patched_drive_access
except (ImportError, AttributeError):
    pass
