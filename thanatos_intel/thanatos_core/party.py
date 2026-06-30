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


# Mappa campi sorgente per ogni doctype-ruolo -> (nome, CF, email, telefono)
PARTY_MAP = {
    "Customer": {"name": "customer_name", "cf": "tax_id", "individual_only": True},
    "Employee": {"name": "employee_name", "email": "company_email",
                 "email2": "personal_email", "phone": "cell_number"},
    "Intelligence Contact": {"name": "full_name", "email": "email", "phone": "phone"},
    "Investigator": {"name": "full_name", "email": "platform_user", "phone": "phone"},
}


def autolink(doc, method=None):
    """Collega automaticamente il record-ruolo al suo Soggetto (riusa o crea, mai duplica).
    Hookato in `validate`: imposta doc.soggetto in-memory cosi' persiste al salvataggio."""
    m = PARTY_MAP.get(getattr(doc, "doctype", None))
    if not m:
        return
    try:
        if not doc.meta.has_field("soggetto"):
            return
    except Exception:
        return
    if getattr(doc, "soggetto", None):
        return
    if m.get("individual_only") and getattr(doc, "customer_type", None) != "Individual":
        return
    full_name = getattr(doc, m["name"], None)
    cf = getattr(doc, m["cf"], None) if m.get("cf") else None
    email = getattr(doc, m.get("email", ""), None) if m.get("email") else None
    if not email and m.get("email2"):
        email = getattr(doc, m["email2"], None)
    phone = getattr(doc, m.get("phone", ""), None) if m.get("phone") else None
    if not (full_name or cf or email or phone):
        return
    sog = get_or_create_soggetto(full_name=full_name, codice_fiscale=cf, email=email, telefono=phone)
    if sog:
        doc.soggetto = sog


def backfill_all():
    """Backfill: collega tutti i record-ruolo esistenti senza soggetto. Ritorna conteggi."""
    res = {}
    for dt in PARTY_MAP:
        if not frappe.db.exists("DocType", dt) or not frappe.db.has_column(dt, "soggetto"):
            continue
        names = frappe.get_all(dt, filters={"soggetto": ["in", ["", None]]}, pluck="name")
        n = 0
        for nm in names:
            try:
                doc = frappe.get_doc(dt, nm)
                autolink(doc)
                if doc.get("soggetto"):
                    frappe.db.set_value(dt, nm, "soggetto", doc.soggetto, update_modified=False)
                    n += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(), "soggetto backfill %s/%s" % (dt, nm))
        res[dt] = n
    frappe.db.commit()
    return res
