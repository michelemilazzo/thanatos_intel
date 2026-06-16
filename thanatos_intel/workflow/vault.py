"""Vault cliente + identità a livelli (Fase 3 Motore Pratiche).

Il Vault (Client Vault Item) è l'archivio documenti del cliente presso Thanatos
(KYC/KYB/CIS/KIT), riusabile tra pratiche, con scadenze. L'identità è a livelli:
Base < KYC < KYB < KIT. Un tier è soddisfatto dallo stato onboarding (kyc/kyb
"Passed") OPPURE da un Vault Item "Valido" del tipo richiesto.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime, today

_OK_ONBOARD = ("Passed", "Not Required")


def client_of_user(user=None):
    user = user or frappe.session.user
    return frappe.db.get_value(
        "Investigation Client", {"platform_user": user},
        ["name", "client_type", "kyc_status", "kyb_status"], as_dict=True)


def tier_satisfied(client, tier):
    """True se il cliente (name) soddisfa il tier identità."""
    if not tier or tier == "Base":
        return bool(client)
    if not client:
        return False
    c = frappe.db.get_value("Investigation Client", client,
                            ["kyc_status", "kyb_status"], as_dict=True) or frappe._dict()

    def has_valid(kind):
        return bool(frappe.db.exists("Client Vault Item",
                    {"client": client, "doc_kind": kind, "status": "Valido"}))

    if tier == "KYC":
        return c.kyc_status in _OK_ONBOARD or has_valid("KYC")
    if tier == "KYB":
        return c.kyb_status in _OK_ONBOARD or has_valid("KYB")
    if tier == "KIT":
        return has_valid("KIT")
    return False


def identity_status(client):
    return {t: tier_satisfied(client, t) for t in ("Base", "KYC", "KYB", "KIT")}


@frappe.whitelist()
def my_vault():
    """Archivio del cliente loggato + stato identità per tier."""
    cl = client_of_user()
    if not cl:
        return {"client": None, "items": [], "identity": {}}
    items = frappe.get_all(
        "Client Vault Item", filters={"client": cl.name},
        fields=["name", "doc_kind", "title", "file", "status", "valid_until",
                "verified_on"], order_by="doc_kind, creation desc")
    return {"client": cl.name, "client_type": cl.client_type,
            "items": items, "identity": identity_status(cl.name)}


@frappe.whitelist()
def vault_upload(doc_kind, title=None, file_url=None, valid_until=None):
    """Il cliente carica un documento nel proprio Vault (stato 'In verifica')."""
    cl = client_of_user()
    if not cl:
        frappe.throw(_("Nessun profilo cliente associato."))
    if doc_kind not in ("KYC", "KYB", "CIS", "KIT", "Altro"):
        frappe.throw(_("Tipo documento non valido."))
    doc = frappe.get_doc({
        "doctype": "Client Vault Item", "client": cl.name, "doc_kind": doc_kind,
        "title": title or doc_kind, "file": file_url, "status": "In verifica",
        "valid_until": valid_until or None,
    })
    doc.insert(ignore_permissions=True)
    return {"ok": True, "name": doc.name}


@frappe.whitelist()
def vault_verify(item, valid_until=None, status="Valido"):
    """Operatore: verifica/aggiorna lo stato di un Vault Item."""
    from thanatos_intel.workflow.api import _is_operator
    if not _is_operator():
        frappe.throw(_("Solo un operatore può verificare i documenti."), frappe.PermissionError)
    if status not in ("Valido", "In verifica", "Scaduto"):
        frappe.throw(_("Stato non valido."))
    vals = {"status": status}
    if status == "Valido":
        vals["verified_by"] = frappe.session.user
        vals["verified_on"] = today()
        if valid_until:
            vals["valid_until"] = valid_until
    frappe.db.set_value("Client Vault Item", item, vals)
    return {"ok": True}


def expire_vault_items():
    """Job giornaliero: marca Scaduti i Vault Item con valid_until passata."""
    rows = frappe.get_all("Client Vault Item", filters={
        "status": "Valido", "valid_until": ["<", today()]}, pluck="name")
    for n in rows:
        frappe.db.set_value("Client Vault Item", n, "status", "Scaduto")
    if rows:
        frappe.db.commit()
    return len(rows)
