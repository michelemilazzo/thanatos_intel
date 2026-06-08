"""Currency converter Thanatos — EUR base + corrispettivo multi-valuta.

Sorgente: ECB (Banca Centrale Europea), feed XML ufficiale aggiornato giornalmente
alle 16:00 CET — https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml

Strategia:
- EUR è la valuta principale (base)
- Cache rates in Frappe Cache (TTL 6h) + persist su DocType "Thanatos FX Rate"
- API: convert(amount, to_ccy) / convert_all(amount, ccys=None)
- Jinja helper: {{ thanatos_fx(amount, "USD") }} / {{ thanatos_fx_block(amount) }}
- Hook scheduled hourly: fetch_rates() aggiorna cache + DocType
- Fallback locale se ECB irraggiungibile (usa ultimo valore salvato)

Tutte le valute principali OneKeyCo / Thanatos:
- USD, GBP, CHF, RON, BGN, RUB, UAH, TRY, AED, SAR, CNY, JPY, INR,
- AUD, CAD, BRL, ZAR, NOK, SEK, DKK, PLN, CZK, HUF, ALL, RSD
"""
from __future__ import annotations
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, Optional

import frappe
import requests

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
USER_AGENT = "ThanatosIntel/1.0 (+https://thanatos.agency)"
CACHE_KEY = "thanatos_fx_rates_eur"
CACHE_TTL = 21600  # 6h

DEFAULT_DISPLAY = [
    "USD", "GBP", "CHF",
    "RON", "BGN", "RUB", "UAH", "TRY",
    "AED", "SAR", "CNY", "JPY", "INR",
    "AUD", "CAD", "BRL", "ZAR",
    "NOK", "SEK", "DKK",
    "PLN", "CZK", "HUF", "ALL", "RSD",
]

SYMBOLS = {
    "EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF",
    "RON": "lei", "BGN": "лв", "RUB": "₽", "UAH": "₴", "TRY": "₺",
    "AED": "د.إ", "SAR": "﷼", "CNY": "¥", "JPY": "¥", "INR": "₹",
    "AUD": "A$", "CAD": "C$", "BRL": "R$", "ZAR": "R",
    "NOK": "kr", "SEK": "kr", "DKK": "kr",
    "PLN": "zł", "CZK": "Kč", "HUF": "Ft",
    "ALL": "L", "RSD": "din",
}


# Peg fissi vs EUR (per valute non più in lista ECB perché eurozona o eurolinked)
FIXED_PEGS = {
    "BGN": 1.95583,   # Bulgaria entrata in eurozona; peg storico mantenuto come riferimento
    "DKK": 7.46038,   # peg ERM II (banda ±2.25%)
}


def _fetch_from_ecb() -> Dict[str, float]:
    """Scarica XML ECB e ritorna dict CCY → rate vs EUR (+ peg fissi)."""
    r = requests.get(ECB_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
    r.raise_for_status()
    rates = {"EUR": 1.0}
    for m in re.finditer(r"currency='([A-Z]{3})'\s+rate='([\d.]+)'", r.text):
        rates[m.group(1)] = float(m.group(2))
    for ccy, peg in FIXED_PEGS.items():
        rates.setdefault(ccy, peg)
    return rates


def _persist(rates: Dict[str, float]) -> None:
    """Salva snapshot su DocType (se esiste) per audit/fallback."""
    if not frappe.db.exists("DocType", "Thanatos FX Rate"):
        return
    try:
        snap = frappe.new_doc("Thanatos FX Rate")
        snap.source = "ECB"
        snap.base = "EUR"
        snap.payload = frappe.as_json(rates)
        snap.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"FX persist: {e}", "thanatos_fx")


def fetch_rates(force: bool = False) -> Dict[str, float]:
    """Get rates (cache → ECB → fallback DB)."""
    if not force:
        cached = frappe.cache().get_value(CACHE_KEY)
        if cached:
            return cached
    try:
        rates = _fetch_from_ecb()
        frappe.cache().set_value(CACHE_KEY, rates, expires_in_sec=CACHE_TTL)
        _persist(rates)
        return rates
    except Exception as e:
        frappe.log_error(f"FX fetch failed: {e}", "thanatos_fx")
        # Fallback: ultimo snapshot DB
        if frappe.db.exists("DocType", "Thanatos FX Rate"):
            last = frappe.db.sql(
                "SELECT payload FROM `tabThanatos FX Rate` "
                "ORDER BY creation DESC LIMIT 1")
            if last:
                try:
                    return frappe.parse_json(last[0][0])
                except Exception:
                    pass
        # Last-resort hardcoded fallback (mid-2026 ballpark, mai accurato)
        return {"EUR": 1.0, "USD": 1.08, "GBP": 0.85, "RON": 4.98, "BGN": 1.9558}


def convert(amount, to_ccy: str, from_ccy: str = "EUR") -> float:
    """Converte amount da from_ccy a to_ccy (default base EUR)."""
    if amount is None:
        return 0.0
    rates = fetch_rates()
    from_ccy = from_ccy.upper()
    to_ccy = to_ccy.upper()
    if from_ccy not in rates or to_ccy not in rates:
        return 0.0
    amt = Decimal(str(amount))
    eur_amount = amt / Decimal(str(rates[from_ccy])) if from_ccy != "EUR" else amt
    result = eur_amount * Decimal(str(rates[to_ccy]))
    return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# BNR — Banca Națională a României (cambio ufficiale per contabilità ANAF)
# XML: https://www.bnr.ro/nbrfxrates.xml — base RON, <Rate currency multiplier>valore</Rate>
# ---------------------------------------------------------------------------
BNR_URL = "https://www.bnr.ro/nbrfxrates.xml"
BNR_CACHE_KEY = "thanatos_bnr_rates_ron"


def _fetch_from_bnr() -> Dict[str, float]:
    """BNR XML → dict CCY → RON per 1 unità (base RON)."""
    r = requests.get(BNR_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
    r.raise_for_status()
    rates = {"RON": 1.0}
    for m in re.finditer(r'<Rate\s+currency="([A-Z]{3})"(?:\s+multiplier="(\d+)")?\s*>([\d.]+)</Rate>', r.text):
        mult = float(m.group(2) or 1)
        rates[m.group(1)] = float(m.group(3)) / mult
    return rates


def bnr_rates(force: bool = False) -> Dict[str, float]:
    """Cambi ufficiali BNR (cache → BNR → fallback snapshot DB → ECB)."""
    if not force:
        cached = frappe.cache().get_value(BNR_CACHE_KEY)
        if cached:
            return cached
    try:
        rates = _fetch_from_bnr()
        frappe.cache().set_value(BNR_CACHE_KEY, rates, expires_in_sec=CACHE_TTL)
        if frappe.db.exists("DocType", "Thanatos FX Rate"):
            try:
                snap = frappe.new_doc("Thanatos FX Rate")
                snap.source = "BNR"
                snap.base = "RON"
                snap.payload = frappe.as_json(rates)
                snap.insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception as e:
                frappe.log_error(f"BNR persist: {e}", "thanatos_fx")
        return rates
    except Exception as e:
        frappe.log_error(f"BNR fetch failed: {e}", "thanatos_fx")
        if frappe.db.exists("DocType", "Thanatos FX Rate"):
            last = frappe.db.sql(
                "SELECT payload FROM `tabThanatos FX Rate` WHERE source='BNR' "
                "ORDER BY creation DESC LIMIT 1")
            if last:
                try:
                    return frappe.parse_json(last[0][0])
                except Exception:
                    pass
        # ultimo fallback: usa il cross ECB EUR→RON
        return {"RON": 1.0, "EUR": fetch_rates().get("RON", 4.98)}


def to_ron_bnr(amount, from_ccy: str = "EUR") -> float:
    """Valore in RON al cambio ufficiale BNR. Per valute non BNR usa cross ECB."""
    if amount is None:
        return 0.0
    from_ccy = (from_ccy or "EUR").upper()
    if from_ccy == "RON":
        return float(amount)
    rate = bnr_rates().get(from_ccy)
    if not rate:
        return convert(amount, "RON", from_ccy)
    result = Decimal(str(amount)) * Decimal(str(rate))
    return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def convert_all(eur_amount, ccys: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    """Per importo EUR ritorna dict CCY → {amount, symbol, formatted}."""
    if eur_amount is None:
        eur_amount = 0
    ccys = list(ccys) if ccys else DEFAULT_DISPLAY
    rates = fetch_rates()
    out = {}
    eur_dec = Decimal(str(eur_amount))
    for c in ccys:
        c = c.upper()
        if c not in rates:
            continue
        v = float((eur_dec * Decimal(str(rates[c]))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP))
        sym = SYMBOLS.get(c, c)
        out[c] = {"amount": v, "symbol": sym,
                  "formatted": _format(v, c, sym)}
    return out


def _format(amount: float, ccy: str, symbol: str) -> str:
    """Formatta numero con separatori (1,234.56) + simbolo."""
    s = f"{amount:,.2f}"
    if ccy in ("USD", "GBP", "AUD", "CAD", "BRL", "CHF"):
        return f"{symbol}{s}"
    if ccy == "EUR":
        return f"€{s}"
    return f"{s} {symbol}"


# ---------- Jinja / API whitelisted ----------------------------------------
@frappe.whitelist(allow_guest=True)
def get_rates() -> dict:
    """REST: GET /api/method/...converter.get_rates"""
    return fetch_rates()


@frappe.whitelist(allow_guest=True)
def quote(amount: float, ccy: str = "EUR") -> dict:
    """REST: quote(100, "EUR") → tutte le altre valute."""
    return {
        "input": {"amount": float(amount), "ccy": ccy.upper()},
        "eur_equivalent": convert(amount, "EUR", ccy),
        "conversions": convert_all(convert(amount, "EUR", ccy)),
    }


# ---------- Jinja helpers (per print format Mandate/Proforma/Dossier) ------
def jinja_fx(amount, to_ccy: str = "USD", from_ccy: str = "EUR") -> str:
    """{{ amount | thanatos_fx("USD") }}"""
    v = convert(amount, to_ccy, from_ccy)
    sym = SYMBOLS.get(to_ccy.upper(), to_ccy.upper())
    return _format(v, to_ccy.upper(), sym)


def jinja_fx_block(amount, ccys: Optional[list] = None,
                   from_ccy: str = "EUR") -> str:
    """Renderizza tabella HTML con conversioni multi-valuta."""
    eur_amount = convert(amount, "EUR", from_ccy)
    data = convert_all(eur_amount, ccys)
    rows = "".join(
        f"<tr><td style='padding:3px 8px;'>{c}</td>"
        f"<td style='padding:3px 8px;text-align:right;font-family:monospace'>"
        f"{d['formatted']}</td></tr>"
        for c, d in data.items()
    )
    return (
        "<table style='border-collapse:collapse;font-size:11px;"
        "border:1px solid #c8a96e;'>"
        f"<thead><tr style='background:#0A0E1A;color:#c8a96e'>"
        f"<th style='padding:4px 8px'>Currency</th>"
        f"<th style='padding:4px 8px'>Amount</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
