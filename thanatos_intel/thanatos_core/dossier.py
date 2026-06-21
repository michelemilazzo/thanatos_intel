"""Dossier IP (inventario live di tutto ciò che abbiamo costruito) + Bacheca.

Il dossier si rilegge di tanto in tanto: app/moduli/DocType custom (l'IP),
servizi, capacità acquisite, compliance, brand. La bacheca raccoglie gli
aggiornamenti (nuovi servizi/capacità/milestone), interni e verso clienti.
"""
import frappe
from frappe.utils import now_datetime


def _count(dt, f=None):
    try:
        return frappe.db.count(dt, f or {})
    except Exception:
        return 0


@frappe.whitelist()
def dossier_data():
    apps = frappe.get_installed_apps()
    mods = [m.module_name for m in frappe.get_all("Module Def",
            filters={"app_name": "thanatos_intel"}, fields=["module_name"])]
    dt_count = _count("DocType", {"custom": 0, "module": ["in", mods]}) if mods else 0
    cats = [r.category for r in frappe.get_all("Service Catalog", fields=["category"],
            group_by="category") if r.category]
    caps = frappe.get_all("Capability Acquisition",
                          fields=["name", "need", "suggested_app", "status"],
                          order_by="creation desc", limit=20) if frappe.db.exists("DocType", "Capability Acquisition") else []
    return {
        "apps": apps,
        "modules": sorted(mods),
        "custom_doctypes": dt_count,
        "services": _count("Service Catalog"),
        "service_categories": sorted(cats),
        "capabilities": caps,
        "compliance": {"policy": _count("Compliance Policy"), "risk": _count("Risk Register Item"),
                       "ropa": _count("ROPA Entry")},
        "counts": {"casi": _count("Investigation Case"), "clienti": _count("Investigation Client"),
                   "entita": _count("Investigation Entity"), "reperti": _count("Investigation Evidence"),
                   "servizi": _count("Service Catalog"), "news": _count("News Article")},
        "brand": {"logo": "/assets/thanatos_intel/images/thanatos-logo-mark.png",
                  "company": "Thanatos Investigazioni S.R.L.", "reg": "Constanța · RO 46901022"},
    }


@frappe.whitelist()
def bacheca(limit=30):
    return frappe.get_all("Bacheca Update",
                          fields=["name", "title", "category", "audience", "body", "published", "modified"],
                          order_by="modified desc", limit=int(limit))


@frappe.whitelist()
def post_update(title, body=None, category="Milestone", audience="Interno", publish=1):
    roles = set(frappe.get_roles())
    if not (roles & {"System Manager", "Investigation Manager", "Thanatos Director", "Investigator"}):
        frappe.throw("Riservato agli operatori.")
    d = frappe.new_doc("Bacheca Update")
    d.title = (title or "Aggiornamento")[:140]
    d.body = body or ""
    d.category = category
    d.audience = audience
    d.published = 1 if int(publish) else 0
    d.published_on = now_datetime()
    d.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": d.name}
