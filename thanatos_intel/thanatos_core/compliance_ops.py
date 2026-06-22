"""Operazioni ISMS schedulate (F3): document control sulle policy + promemoria
audit interno / riesame della direzione. Postano in Bacheca (no duplicati 7gg).
"""
import frappe
from frappe.utils import nowdate, getdate, add_days


def _post(title, body, category="Sistema", audience="Interno"):
    if not frappe.db.exists("DocType", "Bacheca Update"):
        return
    recent = frappe.get_all("Bacheca Update",
                            filters={"title": title, "modified": [">", str(add_days(getdate(nowdate()), -7))]},
                            limit=1)
    if recent:
        return
    frappe.get_doc({"doctype": "Bacheca Update", "title": title, "body": body,
                    "category": category, "audience": audience, "published": 1}).insert(ignore_permissions=True)


def policy_review_check():
    """Document control: segnala le policy con data di revisione scaduta."""
    if not frappe.db.exists("DocType", "Compliance Policy"):
        return
    overdue = frappe.get_all("Compliance Policy",
                             filters={"status": "Approvata", "next_review": ["<=", nowdate()]},
                             fields=["name", "title"])
    for p in overdue:
        _post(f"Revisione policy scaduta: {p.title}",
              f"La policy {p.name} ha superato la data di revisione: aggiornare versione e ri-approvare (controllo documenti).")
    if overdue:
        frappe.db.commit()


def iso_review_reminder():
    """Promemoria annuale: audit interno (9.2) e riesame direzione (9.3)."""
    if not frappe.db.exists("DocType", "ISMS Review"):
        return
    today = getdate(nowdate())
    for rtype, label, clause in (("Audit Interno", "audit interno", "9.2"),
                                 ("Riesame Direzione", "riesame della direzione", "9.3")):
        last = frappe.get_all("ISMS Review",
                              filters={"review_type": rtype, "status": ["in", ["Svolto", "Chiuso"]],
                                       "review_date": [">", str(add_days(today, -365))]}, limit=1)
        if not last:
            _post(f"ISO: pianificare {label}",
                  f"Non risulta un {label} svolto negli ultimi 12 mesi. Pianificarlo (clausola {clause}).")
    frappe.db.commit()
