_patched = False

def apply():
    global _patched
    if _patched:
        return
    try:
        import frappe
        import drive.api.product as _m
        PORTAL_ROLES = {"Investigation Client", "Affiliate"}
        orig = _m.access_app
        def _guarded():
            try:
                if PORTAL_ROLES & set(frappe.get_roles()):
                    return False
            except Exception:
                pass
            return orig()
        _m.access_app = _guarded
        _patched = True
    except (ImportError, AttributeError, RuntimeError):
        pass
