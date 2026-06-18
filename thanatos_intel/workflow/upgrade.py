"""Fase 4 — Approfondimento indagine.

Dal report di una verifica wallet automatizzata il cliente può richiedere un
incarico investigativo completo selezionando i moduli suggeriti (Service Catalog
con flag is_investigation_upgrade). Si crea una nuova pratica "Indagine
Investigativa" collegata all'originale, con i servizi scelti e il preventivo =
somma dei prezzi; la nuova pratica segue il proprio workflow (triage, mandato,
firma, preventivo, pagamento).
"""
import json

import frappe
from frappe import _

UPGRADE_BLUEPRINT = "Indagine Investigativa"


@frappe.whitelist()
def upgrade_options(case_name=None):
    """Moduli di approfondimento disponibili (catalogo flaggato)."""
    if case_name:
        from thanatos_intel.workflow.engagement import _guard
        _guard(case_name)
    rows = frappe.get_all(
        "Service Catalog",
        filters={"is_investigation_upgrade": 1, "is_active": 1},
        fields=["service_code", "service_name", "price", "currency", "category", "description"],
        order_by="price")
    return {"options": rows}


@frappe.whitelist()
def request_full_investigation(case_name, codes):
    """Crea la pratica di approfondimento dai moduli selezionati."""
    from thanatos_intel.workflow.engagement import _guard
    _guard(case_name)
    if isinstance(codes, str):
        codes = json.loads(codes)
    codes = [c for c in (codes or [])]
    if not codes:
        frappe.throw(_("Seleziona almeno un modulo di approfondimento."))

    valid = set(frappe.get_all("Service Catalog",
                filters={"is_investigation_upgrade": 1, "is_active": 1, "service_code": ["in", codes]},
                pluck="service_code"))
    codes = [c for c in codes if c in valid]
    if not codes:
        frappe.throw(_("Moduli selezionati non validi."))

    total = sum(float(frappe.db.get_value("Service Catalog", c, "price") or 0) for c in codes)
    src = frappe.get_doc("Investigation Case", case_name)

    new = frappe.get_doc({
        "doctype": "Investigation Case",
        "case_title": "Approfondimento — %s" % (src.get("case_title") or src.name),
        "case_type": src.get("case_type") or "Asset Recovery",
        "client": src.get("client"),
        "blueprint": UPGRADE_BLUEPRINT,
        "parent_case": src.name,
        "status": "Open",
        "summary": "Approfondimento investigativo della pratica %s" % src.name,
        "description": _summary_html(codes, total, src),
    })
    # moduli scelti come servizi del caso
    for c in codes:
        new.append("services", {"service_catalog": c})
    # copia i wallet della pratica di origine
    for ce in (src.get("case_entities") or []):
        is_wallet = (ce.entity_type or "") == "Wallet" or \
            frappe.db.get_value("Investigation Entity", ce.entity, "entity_type") == "Wallet"
        if is_wallet:
            new.append("case_entities", {"entity": ce.entity, "entity_type": "Wallet",
                                         "role_in_case": "Subject"})
    new.flags.ignore_mandatory = True
    new.insert(ignore_permissions=True)

    # preventivo iniziale = somma moduli, messo sullo step di pagamento
    from thanatos_intel.workflow import engine
    engine.start(new.name)
    new.reload()
    for s in new.get("case_steps") or []:
        if (s.action_type or "") == "pay":
            frappe.db.set_value("Case Step Instance", s.name, "price", total, update_modified=False)
    frappe.db.commit()

    return {"case": new.name, "total": total, "modules": len(codes),
            "url": "/portal/case/%s" % new.name}


def _summary_html(codes, total, src):
    items = ""
    for c in codes:
        nm, pr = frappe.db.get_value("Service Catalog", c, ["service_name", "price"])
        items += "<li>%s — € %s</li>" % (nm, pr)
    return (
        "<p><b>Approfondimento investigativo</b> richiesto dal cliente a partire dalla "
        "pratica di verifica automatizzata <b>%s</b>.</p>"
        "<p>Moduli selezionati:</p><ul>%s</ul>"
        "<p><b>Preventivo indicativo: € %s</b> (soggetto a conferma operatore in fase di Preventivo).</p>"
        % (src.name, items, total))
