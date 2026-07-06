"""Client Blockchain.info Explorer API — enrichment on-chain multichain.

Fonte: https://api.blockchain.info/explorer-gateway-kt (BTC/BCH/ETH/SOL).
Auth: header X-Explorer-Auth-Key = key configurata in site_config.
Rate limit (Free): 1000 req/day, 5 req/sec.

Usato dai flussi OSINT crypto: verifica indirizzo target, snapshot tx count +
volumi ricevuti/inviati per un Wallet Address in indagine.
"""
from __future__ import annotations
import json
import frappe
import requests

BASE = "https://api.blockchain.info/explorer-gateway-kt"

CHAIN_MAP = {"bitcoin": "BTC", "btc": "BTC", "bch": "BCH",
             "ethereum": "ETH", "eth": "ETH", "solana": "SOL", "sol": "SOL"}
ENDPOINT_MAP = {"BTC": "/btc/address", "BCH": "/bch/address",
                "ETH": "/eth/address", "SOL": "/sol/address"}


def _key():
    k = frappe.conf.get("blockchain_explorer_api_key")
    if not k:
        frappe.throw("blockchain_explorer_api_key non configurata in site_config")
    return k


def _post(path: str, body: dict) -> dict:
    r = requests.post(
        BASE + path,
        headers={"X-Explorer-Auth-Key": _key(), "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def address_snapshot(address: str, chain: str = "bitcoin") -> dict:
    """Snapshot rapido di un indirizzo (tx count, ricevuto, saldo)."""
    net = CHAIN_MAP.get((chain or "").lower(), "BTC")
    ep = ENDPOINT_MAP[net]
    data = _post(ep, {"network": net, "address": address, "page": 0})
    return {
        "chain": net,
        "address": address,
        "tx_count": data.get("txCount") or data.get("tx_count") or 0,
        "confirmed_sat": data.get("confirmed") or 0,
        "unconfirmed_sat": data.get("unconfirmed") or 0,
        "received_sat": data.get("received") or 0,
        "utxo_count": data.get("utxo") or 0,
    }


@frappe.whitelist()
def snapshot(address: str, chain: str = "bitcoin"):
    """Endpoint chiamabile dal desk / portale per un enrichment on-demand."""
    return address_snapshot(address, chain)
