"""Batch runner Party Payout — schedulato daily.

Prende tutti i Party Payout in status Pending/Queued/Failed con
stripe_connect_account_id valorizzato ed esegue Stripe Transfer. Guard
idempotente (execute_payout controlla status==Transferred).

Le entries in "Manual Bonifico" sono ignorate (regolate fuori Stripe).
"""
import frappe
from frappe.utils import now


MAX_PER_RUN = 50
RETRY_FAILED = True  # ritenta anche i Failed (max 3 tentativi via failure_reason contains "attempt=")


def daily_execute_pending_payouts():
    from thanatos_intel.billing.revenue_engine import execute_payout

    statuses = ["Pending", "Queued"]
    if RETRY_FAILED:
        statuses.append("Failed")

    rows = frappe.get_all(
        "Party Payout",
        filters={
            "status": ("in", statuses),
            "stripe_connect_account_id": ("!=", ""),
            "amount": (">", 0),
        },
        fields=["name", "amount", "beneficiary_type", "beneficiary_name", "failure_reason"],
        order_by="creation asc",
        limit=MAX_PER_RUN,
    )

    ok, err, skip = 0, 0, 0
    results = []
    for r in rows:
        # anti-loop: se failed 3+ volte, skip
        if r.failure_reason and r.failure_reason.count("attempt=") >= 3:
            skip += 1
            continue
        try:
            doc = frappe.get_doc("Party Payout", r.name)
            res = execute_payout(doc)
            if res.get("transfer_id"):
                ok += 1
                results.append({"po": r.name, "transfer": res["transfer_id"], "amount": r.amount})
            elif res.get("already"):
                skip += 1
            else:
                err += 1
                # incrementa il counter
                doc.failure_reason = (doc.failure_reason or "") + f" attempt={now()};"
                doc.save(ignore_permissions=True)
                results.append({"po": r.name, "error": res.get("error") or "unknown"})
        except Exception as e:
            err += 1
            frappe.log_error(frappe.get_traceback(), f"party_payout_runner {r.name}")
            results.append({"po": r.name, "error": str(e)[:200]})

    frappe.db.commit()
    frappe.logger("party_payout_runner").info(
        f"[{now()}] checked={len(rows)} ok={ok} err={err} skip={skip}"
    )
    return {"checked": len(rows), "transferred": ok, "errors": err, "skipped": skip, "results": results}
