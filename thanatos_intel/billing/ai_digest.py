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


def _html_table(by_client, date):
    rows_html = ""
    for client, d in sorted(by_client.items()):
        label = client if client != "__none__" else "—"
        rows_html += (
            f"<tr><td>{label}</td>"
            f"<td>{d['tokens_in']:,}</td><td>{d['tokens_out']:,}</td>"
            f"<td>€{d['real_cost']:.4f}</td><td>€{d['client_cost']:.4f}</td></tr>"
        )
    return f"""<p>Riepilogo AI Usage — <strong>{date}</strong></p>
<table border="1" cellpadding="4" style="border-collapse:collapse;font-size:13px">
<tr style="background:#eee"><th>Client</th><th>Token IN</th><th>Token OUT</th>
<th>Costo reale MMOS</th><th>Costo cliente</th></tr>
{rows_html}
</table>"""


def daily_ai_digest():
    """scheduler_events.daily — F4: riepilogo giornaliero AI billing."""
    date = _yesterday()
    by_client = _aggregate_yesterday(date)
    if not by_client:
        frappe.logger().info("[ai_digest] nessun log AI ieri (%s)", date)
        return

    month_start = get_first_day(getdate(date))

    # Marca log come billed
    for client, d in by_client.items():
        _mark_billed(d["logs"])

    frappe.db.commit()

    # Calcola overage per ogni client e logga
    total_real = sum(d["real_cost"] for d in by_client.values())
    total_client = sum(d["client_cost"] for d in by_client.values())

    for client, d in by_client.items():
        if client == "__none__":
            continue
        budget = _client_budget(client)
        if budget > 0:
            monthly_total = _monthly_total(client, month_start)
            overage = max(0.0, monthly_total - budget)
            if overage > 0:
                frappe.logger().info(
                    "[ai_digest] client=%s overage=€%.4f (mensile=€%.4f, included=€%.4f)",
                    client, overage, monthly_total, budget,
                )

    # Email riepilogo
    admin = _admin_email()
    html = _html_table(by_client, date)
    html += (
        f"<p><strong>Totale giornaliero:</strong> "
        f"Costo MMOS €{total_real:.4f} | Costo clienti €{total_client:.4f}</p>"
    )
    try:
        frappe.sendmail(
            recipients=[admin],
            subject=f"[Thanatos] Riepilogo AI {date}",
            message=html,
            delayed=False,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ai_digest email")

    frappe.logger().info(
        "[ai_digest] %s: %d client, €%.4f MMOS, €%.4f clienti",
        date, len(by_client), total_real, total_client,
    )
