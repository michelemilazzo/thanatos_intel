"""Mini-DSL split rule Numscript-style.

Sintassi:
    "<pct>% to @<beneficiario> [, <pct>% to @<beneficiario>]*"
        oppure
    "remaining to @<beneficiario>"   come ultimo elemento

Esempi:
    parse_split("70% to @operator, 30% to @platform", 100)
        -> [{beneficiary: 'operator', pct: 70.0, amount: 70.00},
            {beneficiary: 'platform', pct: 30.0, amount: 30.00}]

    parse_split("50% to @thanatos, 30% to @mmos, remaining to @reseller", 100)
        -> [70/30/20 con compenso esatto degli arrotondamenti sul terzo]
"""
import re
from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe import _


_CLAUSE = re.compile(
    r"\s*(?P<token>(?P<pct>\d+(?:\.\d+)?%)|remaining)\s+to\s+@(?P<benef>[A-Za-z0-9_\-\.]+)\s*",
    re.IGNORECASE,
)


def parse_split(dsl: str, gross_amount):
    """Parse 'pct% to @benef, ...' e calcola gli importi netti dal gross.

    Ritorna lista di dict: {beneficiary, pct, amount}. La somma == gross_amount
    esattamente (la clausola 'remaining' assorbe gli errori di arrotondamento).
    """
    if not dsl or not str(dsl).strip():
        frappe.throw(_("Split DSL vuoto"))
    gross = _Q(gross_amount)
    parts = [p for p in str(dsl).split(",") if p.strip()]
    parsed = []
    has_remaining = False
    explicit_pct_sum = Decimal("0")

    for raw in parts:
        m = _CLAUSE.fullmatch(raw)
        if not m:
            frappe.throw(_("Clausola split non valida: {0}").format(raw.strip()))
        benef = m.group("benef")
        token = m.group("token").lower()
        if token == "remaining":
            if has_remaining:
                frappe.throw(_("'remaining' puo' comparire una sola volta"))
            has_remaining = True
            parsed.append({"beneficiary": benef, "pct": None})
        else:
            pct = Decimal(m.group("pct").rstrip("%"))
            explicit_pct_sum += pct
            parsed.append({"beneficiary": benef, "pct": pct})

    if not has_remaining and explicit_pct_sum != Decimal("100"):
        frappe.throw(_("Le percentuali devono sommare a 100 (sono {0})").format(explicit_pct_sum))
    if has_remaining and explicit_pct_sum > Decimal("100"):
        frappe.throw(_("Le percentuali esplicite superano il 100% ({0})").format(explicit_pct_sum))

    result = []
    allocated = Decimal("0")
    remaining_idx = None
    for i, p in enumerate(parsed):
        if p["pct"] is None:
            remaining_idx = i
            result.append({"beneficiary": p["beneficiary"], "pct": None, "amount": None})
            continue
        amount = _Q(gross * p["pct"] / Decimal("100"))
        allocated += amount
        result.append({
            "beneficiary": p["beneficiary"],
            "pct": float(p["pct"]),
            "amount": float(amount),
        })

    if remaining_idx is not None:
        remainder = _Q(gross - allocated)
        leftover_pct = Decimal("100") - explicit_pct_sum
        result[remaining_idx]["pct"] = float(leftover_pct)
        result[remaining_idx]["amount"] = float(remainder)
    else:
        # compensa il drift di arrotondamento sull'ultima clausola
        drift = _Q(gross - allocated)
        if drift != Decimal("0"):
            result[-1]["amount"] = float(_Q(Decimal(str(result[-1]["amount"])) + drift))

    return result


def _Q(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
