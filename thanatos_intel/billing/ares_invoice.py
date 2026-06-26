import frappe
from frappe import _

ITEM = "Servizio Investigativo"


def _accounts(company):
    c = frappe.get_doc("Company", company)
    iva = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Tax", "is_group": 0, "account_name": ["like", "%IVA%"]},
        "name",
    ) or frappe.db.get_value(
        "Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name"
    )
    return {
        "income": c.default_income_account,
        "cost_center": c.cost_center,
        "debit_to": c.default_receivable_account,
        "currency": c.default_currency or "EUR",
        "iva": iva,
    }


def _ensure_project(case, company, customer):
    title = frappe.db.get_value("Investigation Case", case, "case_title") or case
    pname = (title[:90] + " [ARES]").strip()
    existing = frappe.db.get_value("Project", {"company": company, "project_name": pname}, "name")
    if existing:
        return existing
    return frappe.get_doc(
        {"doctype": "Project", "project_name": pname, "company": company, "customer": customer}
    ).insert(ignore_permissions=True).name


def _terms(be):
    return (
        "<b>Modalit&agrave; di pagamento:</b> bonifico bancario<br>"
        "<b>IBAN:</b> {iban}<br><b>Banca:</b> {bank} &mdash; "
        "<b>Intestatario:</b> {holder}"
    ).format(iban=be.iban or "", bank=be.bank_name or "", holder=be.account_holder or be.legal_name or "")


@frappe.whitelist()
def create_ares_invoice(case, customer, amount, description=None, billing_entity="ARES INVESTIGAZIONI SRL"):
    if not frappe.has_permission("Sales Invoice", "create"):
        frappe.throw(_("Permessi insufficienti per creare fatture."))
    amount = float(amount)
    be = frappe.get_doc("Billing Entity", billing_entity)
    company = be.erp_company
    if not company:
        frappe.throw(_("Billing Entity {0}: manca erp_company.").format(billing_entity))
    acc = _accounts(company)
    if not acc["iva"]:
        frappe.throw(_("Conto IVA non trovato per {0}.").format(company))
    desc = description or "Servizi di investigazione - {0}".format(
        frappe.db.get_value("Investigation Case", case, "case_title") or case
    )
    inv = frappe.new_doc("Sales Invoice")
    inv.company = company
    inv.customer = customer
    inv.project = _ensure_project(case, company, customer)
    inv.currency = acc["currency"]
    inv.posting_date = frappe.utils.today()
    inv.debit_to = acc["debit_to"]
    lh = frappe.db.get_value("Company", company, "default_letter_head")
    if lh:
        inv.letter_head = lh
    if inv.meta.has_field("investigation_case"):
        inv.investigation_case = case
    inv.append("items", {
        "item_code": ITEM, "qty": 1, "rate": amount, "description": desc,
        "income_account": acc["income"], "cost_center": acc["cost_center"],
    })
    inv.append("taxes", {
        "charge_type": "On Net Total", "account_head": acc["iva"],
        "description": "IVA 22%", "rate": 22, "cost_center": acc["cost_center"],
    })
    inv.terms = _terms(be)
    inv.insert(ignore_permissions=True)
    iban = (be.iban or "").replace(" ", "")
    mop = frappe.db.exists("Mode of Payment", "Wire Transfer") or frappe.db.exists("Mode of Payment", "Bonifico")
    for r in inv.payment_schedule:
        if mop:
            frappe.db.set_value("Payment Schedule", r.name, "mode_of_payment", mop)
            frappe.db.set_value("Payment Schedule", r.name, "mode_of_payment_code", "MP05-Bonifico bancario")
        if iban:
            frappe.db.set_value("Payment Schedule", r.name, "bank_account_iban", iban)
    frappe.db.commit()
    return inv.name
