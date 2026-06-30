"""Anagrafica unica: trova/crea un Soggetto (persona) deduplicando, e collega i ruoli."""
import frappe


def _phone_tail(p):
    d = "".join(c for c in (p or "") if c.isdigit())
    return d[-9:] if d else ""


def get_or_create_soggetto(full_name=None, codice_fiscale=None, email=None, telefono=None):
    """Riusa un Soggetto esistente (CF -> email -> telefono -> nome) o lo crea. Mai duplicare."""
    s = None
    if codice_fiscale:
        s = frappe.db.get_value("Soggetto", {"codice_fiscale": codice_fiscale})
    if not s and email:
        s = frappe.db.get_value("Soggetto", {"email": email})
    if not s and telefono:
        tail = _phone_tail(telefono)
        if tail:
            rows = frappe.db.sql_list(
                "SELECT name FROM `tabSoggetto` WHERE REPLACE(REPLACE(telefono,' ',''),'+','') LIKE %s LIMIT 1",
                ("%" + tail,))
            s = rows[0] if rows else None
    if not s and full_name:
        s = frappe.db.get_value("Soggetto", {"full_name": full_name})
    if s:
        return s
    doc = frappe.get_doc({"doctype": "Soggetto", "full_name": full_name or "Sconosciuto",
                          "codice_fiscale": codice_fiscale or "", "email": email or "",
                          "telefono": telefono or ""}).insert(ignore_permissions=True)
    return doc.name


def link_role(role_doctype, role_name, soggetto):
    """Collega un record-ruolo (Customer/Investigator/...) al Soggetto, se ha il campo."""
    try:
        if frappe.db.has_column(role_doctype, "soggetto"):
            frappe.db.set_value(role_doctype, role_name, "soggetto", soggetto, update_modified=False)
            return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "link_role")
    return False
