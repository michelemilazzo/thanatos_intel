"""Sincronizzazione Blacklist dalle entita di un Investigation Case.

Bottone "Aggiungi alla Blacklist" sul case. Standardizza il popolamento della
blacklist interna: ogni entita non-vittima rilevante diventa una Blacklist Entry.
Riutilizzabile su tutti i casi futuri.
"""
import frappe
from frappe.utils import nowdate

# entity_type Investigation Entity -> entry_type Blacklist Entry
TYPE_MAP = {"Wallet": "Wallet", "Domain": "Domain", "Email": "Email", "IP": "IP",
            "Phone": "Phone", "Company": "Company", "Person": "Person"}
LEVEL_MAP = {"Critico": "Critical", "Alto": "High", "Medio": "Medium", "Basso": "Medium"}
SKIP_ROLES = {"Victim"}


def _entry_value(entity):
    et = entity.entity_type
    v = (entity.primary_identifier or "").strip()
    if et in ("Email", "Domain", "IP", "Wallet"):
        return v.lower()
    return v


@frappe.whitelist()
def sync_blacklist_from_case(case_name):
    """Crea Blacklist Entry per le entita non-vittima del case. Idempotente."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    case = frappe.get_doc("Investigation Case", case_name)
    created, skipped = 0, 0
    for row in case.case_entities:
        if row.role_in_case in SKIP_ROLES:
            skipped += 1
            continue
        if not frappe.db.exists("Investigation Entity", row.entity):
            continue
        ent = frappe.get_doc("Investigation Entity", row.entity)
        etype = TYPE_MAP.get(ent.entity_type)
        if not etype:
            skipped += 1
            continue
        val = _entry_value(ent)
        if not val:
            continue
        if frappe.db.exists("Blacklist Entry", {"entry_type": etype, "entry_value": val}):
            skipped += 1
            continue
        level = LEVEL_MAP.get(ent.risk_level, "Medium")
        reason = (ent.notes or ent.full_name or row.notes or "Entita collegata a frode")[:480]
        # nota di prudenza per i soggetti (sospetti, non condannati) e per impersonazioni
        if ent.entity_type == "Person":
            reason = "SOGGETTO DELL'INDAGINE (sospetto, non condannato). " + reason
        if "impersona" in (ent.notes or "").lower() or "db.com" in val:
            reason = "VETTORE DI IMPERSONAZIONE (verificare; possibile soggetto reale impersonato). " + reason
            level = "Medium"
        frappe.get_doc({
            "doctype": "Blacklist Entry", "entry_type": etype, "entry_value": val,
            "risk_level": level, "is_active": 1, "verified": 1, "source": "Internal",
            "case_ref": case_name, "reason": reason, "last_seen": nowdate(),
        }).insert(ignore_permissions=True)
        created += 1
    # company numbers dei Company Profile collegati al case (grappolo)
    for cp in frappe.get_all("Company Profile", filters={"investigation_case": case_name},
                             fields=["company_name", "company_number", "current_status"]):
        if not cp.company_number:
            continue
        val = ("UK " + cp.company_number)
        if frappe.db.exists("Blacklist Entry", {"entry_type": "Company", "entry_value": val}):
            continue
        frappe.get_doc({"doctype": "Blacklist Entry", "entry_type": "Company", "entry_value": val,
                        "risk_level": "High", "is_active": 1, "verified": 1, "source": "Internal",
                        "case_ref": case_name,
                        "reason": "Societa del grappolo (%s, %s) collegata alla frode." % (cp.company_name, cp.current_status),
                        "last_seen": nowdate()}).insert(ignore_permissions=True)
        created += 1
    frappe.db.commit()
    return {"created": created, "skipped": skipped,
            "total_blacklist": frappe.db.count("Blacklist Entry")}
