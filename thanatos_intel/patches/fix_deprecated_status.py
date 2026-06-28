"""Allinea valori KYB/KYC Status deprecati alle opzioni correnti.

Vecchie opzioni 'In Review'/'Manual Review' -> 'Pending Review'. Idempotente:
gira a ogni after_migrate, non fa nulla se non ci sono valori obsoleti.
"""
import frappe

_MAP = {
    "kyb_status": {"In Review": "Pending Review", "Manual Review": "Pending Review"},
    "kyc_status": {"In Review": "Pending Review", "Manual Review": "Pending Review"},
}


def apply():
    if not frappe.db.table_exists("Investigation Client"):
        return
    cols = {c["Field"] for c in frappe.db.sql("DESCRIBE `tabInvestigation Client`", as_dict=True)}
    for field, mapping in _MAP.items():
        if field not in cols:
            continue
        for old, new in mapping.items():
            frappe.db.sql(
                f"UPDATE `tabInvestigation Client` SET `{field}`=%s WHERE `{field}`=%s",
                (new, old),
            )
    frappe.db.commit()
