"""F4 — Job giornaliero AI billing Thanatos.
Aggrega AI Usage Log di ieri per Investigation Client, calcola overage su budget mensile
incluso, manda email riepilogo all'admin, marca i log come billed, aggiorna le Quotation
mensili per overage AI (se client ha ai_included impostato).
"""
import frappe
from frappe.utils import add_days, get_first_day, get_last_day, nowdate, getdate, flt


def _yesterday():
    return add_days(nowdate(), -1)


def _admin_email():
    return (
        frappe.db.get_single_value("System Settings", "allow_error_traceback") and None  # just to call
        or frappe.db.get_value("User", {"name": "Administrator"}, "email")
        or frappe.conf.get("admin_email")
        or "ops@thanatos.agency"
    )


def _aggregate_yesterday(date):
    rows = frappe.get_all(
        "AI Usage Log",
        filters={"usage_date": date, "billed": 0},
        fields=["name", "client", "provider", "model",
                "tokens_in", "tokens_out", "real_cost", "client_cost"],
    )
    by_client = {}
    for r in rows:
        c = r["client"] or "__none__"
        if c not in by_client:
            by_client[c] = {
                "logs": [], "tokens_in": 0, "tokens_out": 0,
                "real_cost": 0.0, "client_cost": 0.0,
            }
        by_client[c]["logs"].append(r["name"])
        by_client[c]["tokens_in"] += r.get("tokens_in") or 0
        by_client[c]["tokens_out"] += r.get("tokens_out") or 0
        by_client[c]["real_cost"] += flt(r.get("real_cost") or 0)
        by_client[c]["client_cost"] += flt(r.get("client_cost") or 0)
    return by_client


def _monthly_total(client, month_start):
    """Totale real_cost mensile (inclusi log billed) per stimare overage."""
    result = frappe.db.sql(
        """SELECT COALESCE(SUM(client_cost), 0) FROM `tabAI Usage Log`
           WHERE client=%s AND usage_date BETWEEN %s AND %s""",
        (client, str(month_start), str(get_last_day(month_start))),
    )
    return flt(result[0][0]) if result else 0.0


def _client_budget(client):
    if not client or client == "__none__":
        return 0.0
    val = frappe.db.get_value("Investigation Client", client, "ai_included")
    return flt(val or 0)


def _mark_billed(log_names, proforma=None):
    if not log_names:
        return
    for name in log_names:
        frappe.db.set_value("AI Usage Log", name, {
            "billed": 1,
            **({"proforma": proforma} if proforma else {}),
        }, update_modified=False)


def _billing_email():
    return (frappe.conf.get("ai_billing_email")
            or frappe.conf.get("admin_email")
            or "billing@thanatos.agency")


def _invoice_html(date, tokens, total, charged, balance, recharge_url):
    """Email MMOS→Thanatos: solo il totale del giorno da pagare. NESSUN costo
    interno MMOS (come Thanatos rifattura ai suoi clienti sono affari suoi)."""
    if charged:
        pay = (f"<p style='color:#1a7f37'><strong>✓ Addebitato dal wallet "
               f"prepagato:</strong> €{total:.2f}. Saldo residuo: "
               f"<strong>€{balance:.2f}</strong>.</p>")
    else:
        pay = (f"<p style='color:#b35900'><strong>Da saldare: €{total:.2f}.</strong> "
               f"Wallet prepagato insufficiente (saldo €{balance:.2f}). "
               f"Ricarica con carta: <a href='{recharge_url}'>{recharge_url}</a></p>")
    return f"""<div style="font-family:Arial,sans-serif;font-size:14px;color:#111">
<p><strong>MMOS</strong> — riepilogo consumo AI della piattaforma Thanatos Intel.</p>
<table cellpadding="6" style="border-collapse:collapse;font-size:14px">
<tr><td style="color:#666">Giorno</td><td><strong>{date}</strong></td></tr>
<tr><td style="color:#666">Token elaborati</td><td>{tokens:,}</td></tr>
<tr><td style="color:#666">Importo dovuto a MMOS</td><td><strong>€{total:.2f}</strong></td></tr>
</table>
{pay}
<p style="color:#888;font-size:12px">Fatturazione a consumo AI. Il dettaglio per
singolo caso/cliente resta nella tua console; questo è il totale della piattaforma.</p>
</div>"""


def daily_ai_digest():
    """scheduler_events.daily — MMOS fattura a Thanatos il consumo AI del giorno:
    addebita il wallet prepagato e invia la mail con il totale (carta se il
    wallet non basta). NIENTE costo interno MMOS nella comunicazione."""
    date = _yesterday()
    by_client = _aggregate_yesterday(date)
    if not by_client:
        frappe.logger().info("[ai_digest] nessun log AI ieri (%s)", date)
        return

    # Marca log come billed
    for client, d in by_client.items():
        _mark_billed(d["logs"])
    frappe.db.commit()

    # Totale globale piattaforma = ciò che Thanatos deve a MMOS
    total = round(sum(d["client_cost"] for d in by_client.values()), 2)
    tokens = int(sum(d["tokens_in"] + d["tokens_out"] for d in by_client.values()))
    if total <= 0:
        frappe.logger().info("[ai_digest] %s: totale 0, nessuna fattura", date)
        return

    # Addebita il wallet prepagato Thanatos (già predisposto)
    charged = False
    balance = 0.0
    try:
        from thanatos_intel.billing.mmos_wallet import mmos_balance, mmos_charge
        if mmos_balance() >= total:
            balance = mmos_charge(total, notes=f"Consumo AI {date} ({tokens:,} token)")
            charged = True
        else:
            balance = mmos_balance()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ai_digest wallet charge")
        try:
            from thanatos_intel.billing.mmos_wallet import mmos_balance
            balance = mmos_balance()
        except Exception:
            balance = 0.0

    recharge_url = (frappe.conf.get("ai_billing_recharge_url")
                    or "https://thanatos.onekeyco.com/portal/wallet")
    html = _invoice_html(date, tokens, total, charged, balance, recharge_url)
    try:
        frappe.sendmail(
            recipients=[_billing_email()],
            subject=f"[MMOS] Consumo AI {date} — €{total:.2f}",
            message=html,
            delayed=False,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ai_digest email")

    frappe.logger().info(
        "[ai_digest] %s: €%.2f (%d token) — wallet_charged=%s saldo=€%.2f",
        date, total, tokens, charged, balance,
    )
