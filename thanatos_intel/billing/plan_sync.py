"""Sincronizza i prezzi dei piani abbonamento (Investigation Subscription Plan)
dalla fonte unica Service Catalog (codici SVC-AB-00x).

Elimina il drift tra la pagina pricing pubblica (legge Service Catalog) e il
checkout in /portal/billing (legge ISP): il prezzo vive in un solo posto
(Service Catalog), ISP lo eredita. Hook: Service Catalog on_update -> resync.

Se il prezzo cambia, azzera stripe_price_id: i Price su Stripe sono immutabili,
quindi al prossimo checkout viene creato un nuovo Price con l'importo aggiornato.
"""
import frappe

# piano ISP (name) -> codice Service Catalog (fonte unica del prezzo)
PLAN_SVC = {
    "Basic": "SVC-AB-001",
    "Professional": "SVC-AB-002",
    "Legal": "SVC-AB-003",
    "Enterprise": "SVC-AB-004",
}


def _sync_one(plan_name, svc_code):
    if not frappe.db.exists("Investigation Subscription Plan", plan_name):
        return None
    cat = frappe.db.get_value("Service Catalog", {"service_code": svc_code, "is_active": 1},
                              ["price", "currency"], as_dict=True)
    if not cat or not cat.price:
        return None
    plan = frappe.get_doc("Investigation Subscription Plan", plan_name)
    changed = False
    if float(plan.monthly_price or 0) != float(cat.price):
        plan.monthly_price = cat.price
        plan.stripe_price_id = None  # forza un nuovo Price Stripe col prezzo aggiornato
        changed = True
    if cat.currency and plan.currency != cat.currency:
        plan.currency = cat.currency
        changed = True
    if changed:
        plan.flags.ignore_permissions = True
        plan.save(ignore_permissions=True)
    return changed


@frappe.whitelist()
def sync_plans_from_catalog():
    """Allinea tutti i piani ISP ai prezzi del Service Catalog. Ritorna i cambiati."""
    frappe.only_for(("System Manager", "Investigation Manager"))
    out = {name: _sync_one(name, svc) for name, svc in PLAN_SVC.items()}
    frappe.db.commit()
    return out


def on_service_catalog_update(doc, method=None):
    """Hook: se cambia un SVC-AB di piano, risincronizza il piano ISP collegato."""
    code = getattr(doc, "service_code", None)
    if not code:
        return
    for plan_name, svc in PLAN_SVC.items():
        if svc == code:
            _sync_one(plan_name, svc)
            break
