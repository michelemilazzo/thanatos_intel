"""Audit periodico delle chain Credit Ledger.

Scorre tutte le coppie (party_type, party) con almeno una entry e chiama
verify_chain. Se qualcuna risulta rotta:
- logga su System Console
- crea una Comment di tipo Bug sul DocType (visibile da desk)
- manda email al settings.alert_email_to (riusa SMTP no-replies)

Schedulato daily da hooks.py.
"""
import frappe
from frappe.utils import now

from thanatos_intel.billing.doctype.credit_ledger.credit_ledger import verify_chain


def daily_chain_audit():
    pairs = frappe.db.sql(
        """select distinct party_type, party from `tabCredit Ledger`""",
        as_dict=True,
    )
    broken = []
    for p in pairs:
        try:
            r = verify_chain(p["party_type"], p["party"])
        except Exception as e:
            broken.append({"party_type": p["party_type"], "party": p["party"], "reason": f"audit error: {e}"})
            continue
        if not r.get("ok"):
            broken.append({
                "party_type": p["party_type"],
                "party": p["party"],
                "broken_at": r.get("broken_at"),
                "reason": r.get("reason"),
            })

    frappe.logger("credit_ledger_audit").info(
        f"[{now()}] checked={len(pairs)} broken={len(broken)}"
    )

    if not broken:
        return {"checked": len(pairs), "broken": 0}

    # alert
    body_lines = [
        f"AUDIT CREDIT LEDGER — {len(broken)} chain rotte su {len(pairs)} controllate\n",
    ]
    for b in broken:
        body_lines.append(
            f"  - {b['party_type']}/{b['party']}: {b.get('reason')} @ {b.get('broken_at') or 'N/A'}"
        )
    body = "\n".join(body_lines)

    settings = frappe.get_single("Thanatos Billing Settings") if frappe.db.exists("DocType", "Thanatos Billing Settings") else None
    recipient = (settings and getattr(settings, "alert_email_to", None)) or frappe.conf.get("alert_email_to")
    if recipient:
        try:
            frappe.sendmail(
                recipients=[recipient],
                subject=f"[Thanatos] Credit Ledger: {len(broken)} chain rotte",
                message=body.replace("\n", "<br>"),
            )
        except Exception as e:
            frappe.logger("credit_ledger_audit").error(f"sendmail failed: {e}")

    return {"checked": len(pairs), "broken": len(broken), "details": broken}
