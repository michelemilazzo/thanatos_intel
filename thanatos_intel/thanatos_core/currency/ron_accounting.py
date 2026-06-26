"""Contabilità RON (lei) per i doctype finanziari.

La Company opera in EUR (sede in Romania): per la contabilità locale (ANAF) serve il
corrispettivo in lei al **cambio ufficiale BNR** (Banca Națională a României).
Ogni importo resta in EUR; i campi `<campo>_ron` riportano il valore convertito,
con `exchange_rate_ron` = lei per 1 EUR del giorno.
"""
import frappe
from thanatos_intel.thanatos_core.currency.converter import to_ron_bnr

# doctype custom → campi monetari (in EUR) da affiancare con `<campo>_ron`
RON_FIELDS = {
    "Revenue Distribution": ["gross_amount", "stripe_fee", "vat_amount", "net_amount", "commissions_total"],
    "Diplomatic Proforma": ["amount", "total"],
    "Usage Event": ["unit_price", "total"],
    "Investigation Subscription Plan": ["monthly_price"],
}


def to_ron(amount, from_ccy="EUR"):
    return to_ron_bnr(amount, from_ccy)


def ron_rate(from_ccy="EUR"):
    return to_ron_bnr(1, from_ccy)


def apply_ron(doc, method=None):
    """Doctype custom: importi in EUR → campi `<campo>_ron` al cambio BNR."""
    fields = RON_FIELDS.get(doc.doctype)
    if not fields or not doc.meta.has_field("exchange_rate_ron"):
        return
    src = getattr(doc, "currency", None) or "EUR"
    doc.exchange_rate_ron = ron_rate(src)
    if doc.meta.has_field("ron_ccy"):
        doc.ron_ccy = "RON"
    for f in fields:
        rf = f + "_ron"
        if doc.meta.has_field(rf):
            doc.set(rf, to_ron(doc.get(f) or 0, src))


def apply_ron_erp(doc, method=None):
    """Sales Invoice / Quotation ERPNext: company currency EUR → totali in RON (base_*)."""
    if not doc.meta.has_field("custom_grand_total_ron"):
        return
    import frappe
    if frappe.db.get_value("Company", doc.get("company"), "country") != "Romania":
        for _f in ("custom_eur_ron_rate", "custom_grand_total_ron", "custom_net_total_ron"):
            if doc.meta.has_field(_f):
                doc.set(_f, 0)
        if doc.meta.has_field("custom_ron_ccy"):
            doc.set("custom_ron_ccy", None)
        return
    rate = ron_rate("EUR")  # company currency = EUR
    doc.custom_eur_ron_rate = rate
    if doc.meta.has_field("custom_ron_ccy"):
        doc.custom_ron_ccy = "RON"
    base_grand = doc.get("base_grand_total") or doc.get("grand_total") or 0
    base_net = doc.get("base_net_total") or doc.get("net_total") or 0
    doc.custom_grand_total_ron = to_ron(base_grand, "EUR")
    if doc.meta.has_field("custom_net_total_ron"):
        doc.custom_net_total_ron = to_ron(base_net, "EUR")
