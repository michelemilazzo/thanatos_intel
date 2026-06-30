import frappe
from frappe import _
from frappe.model.document import Document

from thanatos_intel.billing.split_dsl import parse_split


class CommissionRule(Document):
    def validate(self):
        if self.applies_to == "Plan" and not self.subscription_plan:
            frappe.throw(_("Subscription Plan richiesto quando Applies To = Plan"))
        if self.applies_to == "Service" and not self.service:
            frappe.throw(_("Service richiesto quando Applies To = Service"))
        if self.split_dsl:
            try:
                parse_split(self.split_dsl, 100)
            except Exception as e:
                frappe.throw(_("Split DSL non valido: {0}").format(str(e)))
        elif not self.commission_rate:
            frappe.throw(_("Devi specificare commission_rate oppure split_dsl"))


def resolve_commission(plan=None, service=None, partner_level=None):
    """Restituisce la Commission Rule attiva piu specifica per una vendita.

    Specificita: match Plan/Service > Any; partner_level valorizzato > vuoto;
    poi priority decrescente.
    """
    rules = frappe.get_all(
        "Commission Rule",
        filters={"active": 1},
        fields=["name", "applies_to", "subscription_plan", "service",
                "partner_level", "commission_type", "commission_rate",
                "split_dsl", "max_recurring_months", "priority"],
    )

    def ok(r):
        if r.applies_to == "Plan" and r.subscription_plan != plan:
            return False
        if r.applies_to == "Service" and r.service != service:
            return False
        if r.partner_level and r.partner_level != partner_level:
            return False
        return True

    cands = [r for r in rules if ok(r)]
    if not cands:
        return None

    def score(r):
        return (
            2 if r.applies_to in ("Plan", "Service") else 0,
            1 if r.partner_level else 0,
            r.priority or 0,
        )

    return max(cands, key=score)


def compute_commission(rule_or_name, gross_amount, default_partner_label=None):
    """Applica una Commission Rule a un importo gross. Ritorna lista di dict
    {beneficiary, pct, amount}.

    - Se la rule ha split_dsl => usa parse_split (multi-beneficiario).
    - Altrimenti => unica riga con commission_rate (modalita' legacy).
    """
    if isinstance(rule_or_name, str):
        rule = frappe.get_doc("Commission Rule", rule_or_name)
    else:
        rule = rule_or_name
    if not getattr(rule, "active", 1):
        frappe.throw(_("Commission Rule {0} non attiva").format(rule.name))

    if rule.split_dsl:
        return parse_split(rule.split_dsl, gross_amount)

    rate = float(rule.commission_rate or 0)
    benef = default_partner_label or rule.partner_level or "partner"
    amount = round(float(gross_amount) * rate / 100.0, 2)
    return [{"beneficiary": benef, "pct": rate, "amount": amount}]


def commission_for_label(rule_or_name, gross_amount, partner_label):
    """Ritorna l'importo che spetta a un singolo beneficiario (case-insensitive).

    Comodo per pagine 'i miei guadagni': se la rule e' un DSL multi-split,
    estrai la quota del partner_label corrente; se e' legacy, ritorna la quota
    intera (default_partner_label=partner_label fa coincidere il beneficiary).
    """
    if not partner_label:
        partner_label = "partner"
    lines = compute_commission(rule_or_name, gross_amount, default_partner_label=partner_label)
    target = partner_label.lower()
    return round(sum(float(l["amount"]) for l in lines if str(l["beneficiary"]).lower() == target), 2)
