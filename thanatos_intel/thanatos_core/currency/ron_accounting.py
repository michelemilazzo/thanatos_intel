"""Contabilità RON (lei) per i doctype finanziari.

La Company opera in EUR (sede in Romania): per la contabilità locale (ANAF) serve il
corrispettivo in lei. Ogni importo resta in EUR; i campi `<campo>_ron` riportano il
valore convertito al cambio ECB del giorno (via converter), con `exchange_rate_ron`.
"""
import frappe
from thanatos_intel.thanatos_core.currency.converter import convert

RON_FIELDS = {
    "Revenue Distribution": ["gross_amount", "stripe_fee", "vat_amount", "net_amount", "commissions_total"],
    "Diplomatic Proforma": ["amount", "total"],
    "Usage Event": ["unit_price", "total"],
    "Investigation Subscription Plan": ["monthly_price"],
}


def apply_ron(doc, method=None):
    fields = RON_FIELDS.get(doc.doctype)
    if not fields or not doc.meta.has_field("exchange_rate_ron"):
        return
    src = getattr(doc, "currency", None) or "EUR"
    doc.exchange_rate_ron = convert(1, "RON", src)
    if doc.meta.has_field("ron_ccy"):
        doc.ron_ccy = "RON"
    for f in fields:
        rf = f + "_ron"
        if doc.meta.has_field(rf):
            doc.set(rf, convert(doc.get(f) or 0, "RON", src))
