"""Rubrica generale: tutti i Contact nativi (non solo clienti) con assegnazione/condivisione
e gestore della pratica collegata. Solo staff."""
import frappe


def _staff():
    if "System Manager" not in frappe.get_roles():
        try:
            from thanatos_intel.analytics import _is_staff
            if not _is_staff():
                frappe.throw("Solo staff.", frappe.PermissionError)
        except Exception:
            frappe.throw("Solo staff.", frappe.PermissionError)


def _full_name(u):
    return frappe.db.get_value("User", u, "full_name") or u if u else ""


@frappe.whitelist()
def list_contacts(search=None, limit=300):
    _staff()
    filters = {}
    if search:
        filters = {"name": ["like", "%" + search + "%"]}
    rows = frappe.get_all("Contact",
        filters=filters,
        fields=["name", "first_name", "last_name", "email_id", "phone", "mobile_no",
                "company_name", "thanatos_assigned_to", "thanatos_is_shared"],
        order_by="modified desc", limit_page_length=int(limit))
    out = []
    for c in rows:
        # caso collegato + gestore
        case = frappe.db.sql("""select dl.link_name from `tabDynamic Link` dl
            where dl.parenttype='Contact' and dl.parent=%s and dl.link_doctype='Investigation Case' limit 1""",
            (c.name,))
        manager = ""
        case_name = case[0][0] if case else None
        if case_name:
            inv = frappe.db.get_value("Investigation Case", case_name, "assigned_investigator")
            manager = _full_name(inv)
        nm = (((c.first_name or "") + " " + (c.last_name or "")).strip()) or c.name
        out.append({
            "name": c.name, "display": nm, "email": c.email_id or "", "phone": c.mobile_no or c.phone or "",
            "company": c.company_name or "", "assigned_to": c.thanatos_assigned_to or "",
            "assigned_name": _full_name(c.thanatos_assigned_to), "is_shared": bool(c.thanatos_is_shared),
            "case": case_name or "", "manager": manager,
        })
    return out


@frappe.whitelist()
def set_assignment(contact=None, assigned_to=None, is_shared=None):
    _staff()
    doc = frappe.get_doc("Contact", contact)
    doc.thanatos_assigned_to = assigned_to or None
    if is_shared is not None:
        doc.thanatos_is_shared = 1 if str(is_shared) in ("1", "true", "True") else 0
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "contact": contact}


@frappe.whitelist()
def staff_users():
    _staff()
    return frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"},
                          fields=["name", "full_name"], limit_page_length=0)
