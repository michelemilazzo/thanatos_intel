"""Seed idempotente del Motore Pratiche: Case Role + Service Blueprint pilota.

Chiamato da install.after_migrate. Sicuro da rieseguire.
"""
import frappe

# ruolo -> (is_client, is_internal, frappe_role, descrizione)
ROLES = [
    ("Cliente", 1, 0, "Investigation Client", "Mandante: apre pratiche, firma, paga, riceve report"),
    ("Operatore", 0, 1, "Investigation Manager", "PM struttura: triage, approva i gate, assegna"),
    ("Investigatore", 0, 1, "Investigator", "Esegue lavorazione e raccolta evidenze"),
    ("Avvocato", 0, 1, None, "Revisione legale, conformita'"),
    ("Commercialista", 0, 1, None, "Fatturazione e adempimenti"),
    ("Mediatore", 0, 1, None, "Mediazione/relazione cliente"),
    ("Collaboratore", 0, 1, "Affiliate", "Referral/partner"),
    ("Sistema", 0, 1, None, "Azioni automatiche del motore"),
]

# blueprint -> dict
BLUEPRINTS = {
    "Indagine Investigativa": {
        "category": "Investigazioni",
        "self_serve": 0,
        "identity_tier": "KYC",
        "description": "Indagine su persone/aziende con catena di custodia e report.",
        "steps": [
            ("Apri pratica", "Cliente", "AUTO", "form", 1, 0),
            ("Triage e accettazione", "Operatore", "GATE", "review", 1, 0),
            ("Generazione mandato", "Sistema", "AUTO", "work", 1, 0),
            ("Firma mandato", "Cliente", "AUTO", "sign", 1, 0),
            ("Preventivo", "Operatore", "GATE", "work", 1, 0),
            ("Pagamento", "Cliente", "AUTO", "pay", 1, 0),
            ("Assegnazione investigatore", "Operatore", "GATE", "work", 0, 0),
            ("Lavorazione e raccolta evidenze", "Investigatore", "GATE", "work", 1, 0),
            ("Revisione legale", "Avvocato", "GATE", "review", 1, 1),
            ("Consegna report", "Sistema", "AUTO", "deliver", 1, 0),
            ("Chiusura e fatturazione", "Operatore", "AUTO", "notify", 1, 0),
        ],
    },
    "OSINT Lookup": {
        "category": "OSINT",
        "self_serve": 1,
        "identity_tier": "Base",
        "description": "Ricerca su fonti aperte, self-service a pagamento.",
        "steps": [
            ("Apri pratica", "Cliente", "AUTO", "form", 1, 0),
            ("Pagamento", "Cliente", "AUTO", "pay", 1, 0),
            ("Esecuzione OSINT", "Investigatore", "GATE", "work", 0, 0),
            ("Consegna report", "Sistema", "AUTO", "deliver", 1, 0),
            ("Chiusura", "Sistema", "AUTO", "notify", 1, 0),
        ],
    },
}


def _seed_roles():
    for role_name, is_client, is_internal, frappe_role, desc in ROLES:
        if frappe.db.exists("Case Role", role_name):
            continue
        if frappe_role and not frappe.db.exists("Role", frappe_role):
            frappe_role = None
        frappe.get_doc({
            "doctype": "Case Role", "role_name": role_name,
            "is_client": is_client, "is_internal": is_internal,
            "frappe_role": frappe_role, "description": desc, "is_active": 1,
        }).insert(ignore_permissions=True)


def _seed_blueprints():
    for name, spec in BLUEPRINTS.items():
        if frappe.db.exists("Service Blueprint", name):
            continue
        doc = frappe.get_doc({
            "doctype": "Service Blueprint", "blueprint_name": name,
            "category": spec["category"], "self_serve": spec["self_serve"],
            "identity_tier": spec["identity_tier"], "description": spec["description"],
            "is_active": 1,
        })
        for label, role, mode, action, client_visible, optional in spec["steps"]:
            doc.append("steps", {
                "step_label": label, "actor_role": role, "mode": mode,
                "action_type": action, "client_visible": client_visible,
                "optional": optional, "notify": 1,
            })
        doc.insert(ignore_permissions=True)


def seed_workflow():
    _seed_roles()
    _seed_blueprints()
    frappe.db.commit()
