"""Analisi wallet TRON via TronGrid API (mainnet).

Espone address_snapshot(address) → saldo TRX, USDT-TRC20, check permessi
(pattern classico furto USDT-TRC20: attaccante peso 2 / titolare peso 1 =
wallet dirottato via multisig forzato — il titolare non puo firmare da solo).

Key TronGrid: site_config \"trongrid_api_key\".
"""
from __future__ import annotations
import json
import frappe
import requests

BASE = "https://api.trongrid.io"
USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def _headers():
    k = frappe.conf.get("trongrid_api_key")
    h = {"Content-Type": "application/json", "User-Agent": "thanatos-osint"}
    if k:
        h["TRON-PRO-API-KEY"] = k
    return h


def _post(path, body):
    r = requests.post(BASE + path, headers=_headers(), data=json.dumps(body), timeout=12)
    r.raise_for_status()
    return r.json()


def _get(path):
    r = requests.get(BASE + path, headers=_headers(), timeout=12)
    r.raise_for_status()
    return r.json()


def address_snapshot(address: str) -> dict:
    """Ritorna saldi + permessi + eventuali warning."""
    if not address or not address.startswith("T") or len(address) < 30:
        frappe.throw("indirizzo TRON non valido (deve iniziare per T, len >= 30)")

    acc = _post("/wallet/getaccount", {"address": address, "visible": True})
    trx_balance = (acc.get("balance") or 0) / 1e6

    owner_p = acc.get("owner_permission") or {}
    threshold = owner_p.get("threshold", 1)
    keys = owner_p.get("keys", [])
    my_key_weight, total_weight = 0, 0
    attacker_keys = []
    for k in keys:
        w = k.get("weight", 0)
        total_weight += w
        if k.get("address") == address:
            my_key_weight = w
        else:
            attacker_keys.append({"address": k.get("address"), "weight": w})
    permission_ok = my_key_weight >= threshold if keys else True

    warnings = []
    if keys and not permission_ok:
        warnings.append({
            "type": "hijacked_permission", "severity": "critical",
            "msg": (f"WALLET DIROTTATO: soglia {threshold}, tuo peso {my_key_weight}. "
                    f"{len(attacker_keys)} chiavi terze (peso "
                    f"{sum(w['weight'] for w in attacker_keys)}). "
                    "Pattern classico furto TRON."),
            "attacker_keys": attacker_keys,
        })

    usdt = 0.0
    try:
        info = _get(f"/v1/accounts/{address}")
        for d in (info.get("data") or []):
            for t in (d.get("trc20") or []):
                if USDT_TRC20 in t:
                    usdt = int(t[USDT_TRC20]) / 1e6
                    break
    except Exception:
        pass

    return {
        "chain": "tron",
        "address": address,
        "trx_balance": round(trx_balance, 6),
        "usdt_trc20_balance": round(usdt, 2),
        "permission": {
            "threshold": threshold, "your_weight": my_key_weight,
            "total_weight": total_weight, "healthy": permission_ok,
            "attacker_keys": attacker_keys,
        },
        "trongrid_authenticated": bool(frappe.conf.get("trongrid_api_key")),
        "warnings": warnings,
        "healthy": permission_ok and not warnings,
    }


@frappe.whitelist()
def snapshot(address: str):
    return address_snapshot(address)
