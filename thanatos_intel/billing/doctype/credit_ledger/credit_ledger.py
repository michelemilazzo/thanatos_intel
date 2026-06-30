import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


SIGN = {
    "Earned": 1,
    "Adjustment": 1,
    "Spent": -1,
    "Commission": -1,
    "Payout": -1,
}

PROTECTED_PARTY_TYPES = {"Client"}


class CreditLedger(Document):
    def validate(self):
        delta = SIGN[self.kind] * flt(self.amount)
        prev = _last_entry(self.party_type, self.party, exclude=self.name)
        current = flt(prev.balance_after) if prev else 0.0
        new_balance = current + delta

        if (
            self.party_type in PROTECTED_PARTY_TYPES
            and new_balance < 0
            and not frappe.flags.get("allow_negative_credit_balance")
        ):
            frappe.throw(
                _("Saldo {0} insufficiente per {1}: saldo {2:.2f} + delta {3:.2f} = {4:.2f}").format(
                    self.party_type, self.party, current, delta, new_balance
                ),
                title=_("Negative balance"),
            )

        self.balance_after = new_balance
        self.prev_hash = prev.entry_hash if prev else ""
        self.entry_hash = _compute_entry_hash(self)

    def on_trash(self):
        successors = frappe.db.exists(
            "Credit Ledger",
            {"prev_hash": self.entry_hash, "name": ("!=", self.name)},
        )
        if successors:
            frappe.throw(
                _("Cancellazione bloccata: la entry e' agganciata alla chain. Usa una Adjustment per stornare."),
                title=_("Tamper-evident audit"),
            )


def _last_entry(party_type, party, exclude=None):
    filters = {"party_type": party_type, "party": party}
    if exclude:
        filters["name"] = ("!=", exclude)
    rows = frappe.get_all(
        "Credit Ledger",
        filters=filters,
        fields=["name", "balance_after", "entry_hash"],
        order_by="creation desc, name desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def _compute_entry_hash(doc):
    payload = "|".join([
        str(doc.prev_hash or ""),
        str(doc.party_type or ""),
        str(doc.party or ""),
        str(doc.kind or ""),
        f"{flt(doc.amount):.6f}",
        f"{flt(doc.balance_after):.6f}",
        str(doc.reference_doctype or ""),
        str(doc.reference_name or ""),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@frappe.whitelist()
def verify_chain(party_type, party):
    """Walk the chain in order and return ok/broken + first broken entry."""
    rows = frappe.get_all(
        "Credit Ledger",
        filters={"party_type": party_type, "party": party},
        fields=["name", "party_type", "party", "kind", "amount", "balance_after",
                "reference_doctype", "reference_name", "prev_hash", "entry_hash"],
        order_by="creation asc, name asc",
    )
    prev_hash = ""
    running = 0.0
    for r in rows:
        d = frappe._dict(r)
        running += SIGN[d.kind] * flt(d.amount)
        if d.prev_hash != prev_hash:
            return {"ok": False, "broken_at": d.name, "reason": "prev_hash mismatch"}
        if d.entry_hash != _compute_entry_hash(d):
            return {"ok": False, "broken_at": d.name, "reason": "entry_hash mismatch"}
        if abs(running - flt(d.balance_after)) > 0.005:
            return {"ok": False, "broken_at": d.name, "reason": f"balance drift {running:.4f} != {d.balance_after:.4f}"}
        prev_hash = d.entry_hash
    return {"ok": True, "entries": len(rows), "final_balance": running}
