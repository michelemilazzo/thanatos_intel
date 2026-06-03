"""
Revenue split engine for Thanatos Intel.

Pipeline (per ogni pagamento incassato → Revenue Distribution):
  gross   = quanto pagato dal cliente
  net     = gross - stripe_fee - vat
  infra   = somma costi infrastruttura allocati pro-quota
  commiss = somma commissioni dei terzi del caso (Investigator/Agency/Lawyer/Accountant)
  pool    = net - infra - commiss
  thanatos= pool * 50%   (split di default, configurabile in site_config thanatos_profit_pct)
  mmos    = pool * 50%

Output:
  - Revenue Distribution con split_lines dettagliate
  - Party Payout per ogni terzo (status Pending → execute via Stripe Connect Transfer)

Hetzner / Claude / OpenRouter / etc. sono modellati come Infrastructure Cost con
allocation_mode = "Per Active Case" (default) o altri schemi.
"""
import json
import frappe
from frappe import _
from frappe.utils import now_datetime, get_first_day, get_last_day, getdate

DEFAULT_THANATOS_PCT = 50.0
DEFAULT_MMOS_PCT = 50.0


def _split_pcts():
    t = float(frappe.conf.get("thanatos_profit_pct") or DEFAULT_THANATOS_PCT)
    m = float(frappe.conf.get("mmos_profit_pct") or DEFAULT_MMOS_PCT)
    if t + m <= 0:
        return DEFAULT_THANATOS_PCT, DEFAULT_MMOS_PCT
    return t, m


def compute_distribution(rd) -> dict:
    """Calcola net/infra/commissions/profit_pool/thanatos/mmos e popola split_lines."""
    rd.net_amount = round(float(rd.gross_amount or 0)
                          - float(rd.stripe_fee or 0)
                          - float(rd.vat_amount or 0), 2)

    rd.split_lines = []

    if rd.stripe_fee:
        rd.append("split_lines", {
            "line_type": "Stripe Fee", "label": "Stripe processing fee",
            "beneficiary_type": "Stripe", "beneficiary": "Stripe",
            "amount": float(rd.stripe_fee), "payout_status": "Not Applicable",
        })
    if rd.vat_amount:
        rd.append("split_lines", {
            "line_type": "VAT", "label": "IVA / VAT",
            "beneficiary_type": "Provider", "beneficiary": "Erario",
            "amount": float(rd.vat_amount), "payout_status": "Not Applicable",
        })

    infra_total = 0.0
    for line in _allocate_infrastructure_costs(rd):
        infra_total += line["amount"]
        rd.append("split_lines", line)
    rd.infra_cost_share = round(infra_total, 2)

    commiss_total = 0.0
    for line in _allocate_third_party_commissions(rd):
        commiss_total += line["amount"]
        rd.append("split_lines", line)
    rd.commissions_total = round(commiss_total, 2)

    pool = round(float(rd.net_amount) - infra_total - commiss_total, 2)
    if pool < 0:
        pool = 0.0
    rd.profit_pool = pool

    t_pct, m_pct = _split_pcts()
    t_amt = round(pool * t_pct / 100.0, 2)
    m_amt = round(pool - t_amt, 2)
    rd.thanatos_share = t_amt
    rd.mmos_share = m_amt

    rd.append("split_lines", {
        "line_type": "Thanatos Profit", "label": f"Thanatos {t_pct}%",
        "beneficiary_type": "Thanatos", "beneficiary": "Thanatos",
        "pct": t_pct, "amount": t_amt, "payout_status": "Pending",
    })
    rd.append("split_lines", {
        "line_type": "MMOS Profit", "label": f"MMOS {m_pct}%",
        "beneficiary_type": "MMOS", "beneficiary": "MMOS / OneKeyCo",
        "pct": m_pct, "amount": m_amt, "payout_status": "Pending",
    })

    rd.status = "Computed"
    rd.computed_at = now_datetime()
    return {
        "net": rd.net_amount, "infra": infra_total, "commissions": commiss_total,
        "pool": pool, "thanatos": t_amt, "mmos": m_amt,
    }


def _allocate_infrastructure_costs(rd) -> list:
    """Calcola la quota di costi infrastrutturali da sottrarre a questo revenue."""
    active = frappe.get_all("Infrastructure Cost",
                            filters={"is_active": 1},
                            fields=["name", "cost_code", "provider", "monthly_cost",
                                    "currency", "allocation_mode", "fixed_share_pct"])
    if not active:
        return []

    n_active_cases = max(1, frappe.db.count("Investigation Case",
                                            {"status": ["in", ["Open", "In Progress", "Investigation"]]}))
    n_active_subs = max(1, frappe.db.count("Stripe Subscription",
                                           {"status": ["in", ["active", "trialing"]]}))

    days = _days_in_current_month()
    lines = []
    for c in active:
        monthly = float(c.monthly_cost or 0)
        if monthly <= 0:
            continue
        if c.allocation_mode == "Fixed Share":
            amt = round(float(rd.net_amount) * float(c.fixed_share_pct or 0) / 100.0, 2)
        elif c.allocation_mode == "Per Active Subscription":
            amt = round(monthly / n_active_subs, 2)
        elif c.allocation_mode == "Per Usage Event":
            n_events = max(1, frappe.db.count("Usage Event",
                                              {"creation": [">=", get_first_day(now_datetime())]}))
            amt = round(monthly / n_events, 2)
        elif c.allocation_mode == "Per Revenue Share":
            month_revenue = float(frappe.db.sql(
                "SELECT COALESCE(SUM(net_amount),0) FROM `tabRevenue Distribution` "
                "WHERE creation >= %s", (get_first_day(now_datetime()),))[0][0] or 0)
            month_revenue = max(month_revenue + float(rd.net_amount), float(rd.net_amount))
            amt = round(monthly * float(rd.net_amount) / month_revenue, 2)
        else:  # Per Active Case (default)
            amt = round(monthly / n_active_cases, 2)
        if amt <= 0:
            continue
        lines.append({
            "line_type": "Infrastructure Cost",
            "label": f"{c.provider} · {c.cost_code} (alloc {c.allocation_mode})",
            "beneficiary_type": "MMOS", "beneficiary": c.provider,
            "amount": amt, "payout_status": "Not Applicable",
        })
    return lines


def _allocate_third_party_commissions(rd) -> list:
    if not rd.investigation_case:
        return []
    case = frappe.get_doc("Investigation Case", rd.investigation_case)
    rows = getattr(case, "case_assignments", None) or []
    if not rows:
        return []
    lines = []
    for a in rows:
        pct = float(a.commission_pct or 0)
        if pct <= 0:
            continue
        amt = round(float(rd.net_amount) * pct / 100.0, 2)
        if amt <= 0:
            continue
        lines.append({
            "line_type": "Third Party Commission",
            "label": f"{a.assignee_type} · {a.assignee}",
            "beneficiary_type": a.assignee_type,
            "beneficiary": a.assignee,
            "pct": pct,
            "amount": amt,
            "stripe_transfer_id": None,
            "payout_status": "Pending" if a.stripe_connect_account_id else "Manual",
        })
    return lines


def queue_third_party_payouts(rd) -> dict:
    """Crea Party Payout records per ogni commissione/MMOS/Thanatos da pagare."""
    created = 0
    for line in (rd.split_lines or []):
        if line.line_type not in ("Third Party Commission", "Thanatos Profit", "MMOS Profit"):
            continue
        if float(line.amount or 0) <= 0:
            continue
        connect_acct = None
        if line.line_type == "Third Party Commission" and rd.investigation_case:
            case = frappe.get_doc("Investigation Case", rd.investigation_case)
            for a in (getattr(case, "case_assignments", None) or []):
                if a.assignee == line.beneficiary and a.assignee_type == line.beneficiary_type:
                    connect_acct = a.stripe_connect_account_id
                    break

        po = frappe.get_doc({
            "doctype": "Party Payout",
            "beneficiary_type": line.beneficiary_type,
            "beneficiary_name": line.beneficiary or line.beneficiary_type,
            "stripe_connect_account_id": connect_acct,
            "revenue_distribution": rd.name,
            "investigation_case": rd.investigation_case,
            "amount": float(line.amount),
            "currency": rd.currency or "EUR",
            "status": "Queued" if connect_acct else "Manual Bonifico",
            "queued_at": now_datetime(),
        })
        po.insert(ignore_permissions=True)
        line.payout_status = "Queued" if connect_acct else "Manual"
        created += 1
    frappe.db.commit()
    return {"queued": created}


def execute_payout(po) -> dict:
    """Esegue un Party Payout: Stripe Connect Transfer se acct, altrimenti rimane Manual."""
    if po.status == "Transferred":
        return {"already": True}
    if not po.stripe_connect_account_id:
        po.status = "Manual Bonifico"
        po.save(ignore_permissions=True)
        return {"manual": True, "reason": "no_connect_account"}

    from thanatos_intel.integrations.stripe_bridge import _get_stripe
    stripe = _get_stripe()
    try:
        amount_cents = int(round(float(po.amount) * 100))
        tr = stripe.Transfer.create(
            amount=amount_cents,
            currency=(po.currency or "EUR").lower(),
            destination=po.stripe_connect_account_id,
            transfer_group=po.revenue_distribution or po.investigation_case or po.name,
            metadata={
                "thanatos_payout": po.name,
                "rd": po.revenue_distribution or "",
                "case": po.investigation_case or "",
            },
        )
        po.stripe_transfer_id = tr.id
        po.status = "Transferred"
        po.completed_at = now_datetime()
        po.save(ignore_permissions=True)
        return {"transfer_id": tr.id, "amount": po.amount}
    except Exception as e:
        po.status = "Failed"
        po.failure_reason = str(e)[:500]
        po.save(ignore_permissions=True)
        return {"error": str(e)}


def _days_in_current_month():
    from calendar import monthrange
    today = getdate(now_datetime())
    return monthrange(today.year, today.month)[1]


@frappe.whitelist()
def create_distribution_from_stripe_invoice(invoice_id: str) -> str:
    """Helper invocato dopo invoice.paid: crea Revenue Distribution e compute."""
    if frappe.db.exists("Revenue Distribution", {"stripe_charge_id": invoice_id}):
        return frappe.db.get_value("Revenue Distribution", {"stripe_charge_id": invoice_id}, "name")

    from thanatos_intel.integrations.stripe_bridge import _get_stripe
    stripe = _get_stripe()
    inv = stripe.Invoice.retrieve(invoice_id, expand=["customer", "subscription"])

    client_name = None
    md = inv.get("metadata") or {}
    if md.get("thanatos_client"):
        client_name = md["thanatos_client"]
    elif inv.customer:
        cust_id = inv.customer.id if hasattr(inv.customer, "id") else inv.customer
        client_name = frappe.db.get_value("Investigation Client",
                                          {"stripe_customer_id": cust_id}, "name")

    rd = frappe.get_doc({
        "doctype": "Revenue Distribution",
        "title": f"Stripe Invoice {invoice_id}",
        "source_doctype": "Stripe Subscription" if inv.get("subscription") else "Investigation Client",
        "source_name": inv.subscription if inv.get("subscription") else client_name,
        "investigation_client": client_name,
        "stripe_charge_id": invoice_id,
        "gross_amount": float(inv.amount_paid or 0) / 100.0,
        "stripe_fee": _estimate_stripe_fee(float(inv.amount_paid or 0) / 100.0),
        "vat_amount": float(inv.tax or 0) / 100.0,
        "currency": (inv.currency or "eur").upper(),
        "status": "Draft",
    })
    rd.insert(ignore_permissions=True)
    rd.compute_split()
    return rd.name


def _estimate_stripe_fee(gross: float) -> float:
    """Approssimazione 1.5% + 0.25 (EU cards). Per dati reali estrarre da BalanceTransaction."""
    return round(gross * 0.015 + 0.25, 2)
