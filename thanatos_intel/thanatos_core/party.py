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
        if not s and frappe.db.exists("DocType", "Soggetto Email"):
            s = frappe.db.get_value("Soggetto Email", {"email": email, "parenttype": "Soggetto"}, "parent")
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


@frappe.whitelist()
def person_card(soggetto):
    """HTML 'scheda persona': ruoli, record collegati, email, fatture, casi — in un colpo solo."""
    from frappe.utils import get_url_to_form, fmt_money
    if not soggetto or not frappe.db.exists("Soggetto", soggetto):
        return ""
    sog = frappe.get_doc("Soggetto", soggetto)
    H = []
    H.append("<div style='font-size:13px'>")

    # ruoli
    if sog.ruoli:
        H.append("<div style='margin-bottom:8px'><b>Ruoli:</b> %s</div>" % frappe.utils.escape_html(sog.ruoli))

    # record-ruolo collegati
    role_rows = []
    for dt, label in [("Customer", "Cliente"), ("Employee", "Dipendente"),
                      ("Investigator", "Investigatore"), ("Intelligence Contact", "Contatto Intel")]:
        try:
            if not frappe.db.has_column(dt, "soggetto"):
                continue
            for nm in frappe.get_all(dt, filters={"soggetto": soggetto}, pluck="name"):
                role_rows.append((label, dt, nm))
        except Exception:
            pass
    if role_rows:
        H.append("<div style='margin-bottom:8px'><b>Record collegati</b><ul style='margin:4px 0 0 16px;padding:0'>")
        for label, dt, nm in role_rows:
            H.append("<li>%s: <a href='%s'>%s</a></li>" % (label, get_url_to_form(dt, nm), frappe.utils.escape_html(nm)))
        H.append("</ul></div>")

    # email (primaria + alias)
    mails = []
    if sog.email:
        mails.append(sog.email + " (primaria)")
    for r in (sog.get("emails") or []):
        if r.email:
            mails.append(r.email + ((" — " + r.etichetta) if r.etichetta else "") + (" ⭐" if r.is_default else ""))
    if mails:
        H.append("<div style='margin-bottom:8px'><b>Email:</b> %s</div>" % frappe.utils.escape_html(" · ".join(mails)))

    # Customer collegati -> fatture
    customers = [nm for (_l, dt, nm) in role_rows if dt == "Customer"]
    if customers:
        try:
            invs = frappe.get_all("Sales Invoice", filters={"customer": ["in", customers]},
                                  fields=["name", "status", "grand_total", "currency", "posting_date"],
                                  order_by="posting_date desc", limit=8)
            if invs:
                H.append("<div style='margin-bottom:8px'><b>Fatture</b><ul style='margin:4px 0 0 16px;padding:0'>")
                for iv in invs:
                    H.append("<li><a href='%s'>%s</a> · %s %s · %s · %s</li>" % (
                        get_url_to_form("Sales Invoice", iv.name), iv.name,
                        iv.currency or "", iv.grand_total or 0, iv.status or "", iv.posting_date or ""))
                H.append("</ul></div>")
        except Exception:
            pass

    # Casi: Investigation Case con un Link verso Customer (rilevato dinamicamente) + per investigatore
    cases = set()
    try:
        if frappe.db.exists("DocType", "Investigation Case") and customers:
            meta = frappe.get_meta("Investigation Case")
            for df in meta.get("fields", []):
                if df.fieldtype == "Link" and df.options == "Customer":
                    for nm in frappe.get_all("Investigation Case", filters={df.fieldname: ["in", customers]}, pluck="name"):
                        cases.add(nm)
    except Exception:
        pass
    try:
        investigators = [nm for (_l, dt, nm) in role_rows if dt == "Investigator"]
        if investigators and frappe.db.exists("DocType", "Case Assignment"):
            for nm in frappe.get_all("Case Assignment",
                                     filters={"assignee": ["in", investigators], "parenttype": "Investigation Case"},
                                     fields=["parent"], pluck="parent"):
                cases.add(nm)
    except Exception:
        pass
    if cases:
        H.append("<div style='margin-bottom:8px'><b>Casi</b><ul style='margin:4px 0 0 16px;padding:0'>")
        for nm in list(cases)[:12]:
            H.append("<li><a href='%s'>%s</a></li>" % (get_url_to_form("Investigation Case", nm), frappe.utils.escape_html(nm)))
        H.append("</ul></div>")

    # Gruppi/cluster societari in cui la persona compare (per link soggetto o per nome)
    try:
        groups = set()
        if frappe.db.has_column("Corporate Group Member", "soggetto"):
            groups.update(frappe.get_all("Corporate Group Member",
                          filters={"soggetto": soggetto}, fields=["parent"], pluck="parent"))
        if sog.full_name:
            groups.update(frappe.get_all("Corporate Group Member",
                          filters={"entity_name": sog.full_name}, fields=["parent"], pluck="parent"))
        if groups:
            H.append("<div style='margin-bottom:8px'><b>Gruppi societari</b><ul style='margin:4px 0 0 16px;padding:0'>")
            for g in list(groups)[:10]:
                H.append("<li><a href='%s'>%s</a></li>" % (get_url_to_form("Corporate Group", g), frappe.utils.escape_html(g)))
            H.append("</ul></div>")
    except Exception:
        pass

    H.append("</div>")
    return "".join(H)
