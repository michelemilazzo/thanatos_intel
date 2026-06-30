import frappe
from frappe import _
from frappe.model.document import Document

from thanatos_intel.billing.split_dsl import parse_split


class CommissionRule(Document):
    def validate(self):
        if self.split_dsl:
            # un dry-run del parser convalida la sintassi gia' al save
            try:
                parse_split(self.split_dsl, 100)
            except Exception as e:
                frappe.throw(_("Split DSL non valido: {0}").format(str(e)))
        elif not self.commission_rate:
            frappe.throw(_("Devi specificare commission_rate oppure split_dsl"))


def compute_commission(rule_name, gross_amount, default_partner_label=None):
    """Applica una Commission Rule a un importo gross.

    Ritorna sempre lista di dict {beneficiary, pct, amount}:
    - Se la rule ha split_dsl => usa parse_split
    - Altrimenti => unica riga {beneficiary=default_partner_label or rule.partner_level or 'partner',
                                 pct=commission_rate, amount=gross*rate/100}
    """
    rule = frappe.get_doc("Commission Rule", rule_name)
    if not rule.active:
        frappe.throw(_("Commission Rule {0} non attiva").format(rule_name))

    if rule.split_dsl:
        return parse_split(rule.split_dsl, gross_amount)

    rate = float(rule.commission_rate or 0)
    benef = default_partner_label or rule.partner_level or "partner"
    amount = round(float(gross_amount) * rate / 100.0, 2)
    return [{"beneficiary": benef, "pct": rate, "amount": amount}]
