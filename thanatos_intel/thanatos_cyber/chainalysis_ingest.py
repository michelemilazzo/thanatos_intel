"""Chainalysis blog ingester for Crypto Scam Intelligence.

Pull listing pages and per-article pages from chainalysis.com/blog,
extract title + body + published date + scam type signal, rewrite to
Thanatos voice (IT) and create Crypto Scam Intelligence docs.

Whitelisted entry point:
  thanatos_intel.thanatos_cyber.chainalysis_ingest.ingest_url
  thanatos_intel.thanatos_cyber.chainalysis_ingest.ingest_index

Designed to RESPECT copyright: it stores the source URL + a hash + a 280-char
excerpt as evidence (raw_html), and writes its OWN summary/modus operandi.
"""
from __future__ import annotations
import hashlib
import re
from datetime import datetime
from typing import Iterable

import frappe
import requests

DEFAULT_INDEX = "https://www.chainalysis.com/blog/crypto-scams-2026/"
USER_AGENT = "ThanatosIntel/1.0 (+https://thanatos.agency)"

SCAM_KEYWORDS = {
    "pig butchering":  "Pig Butchering",
    "romance":         "Romance Scam",
    "rug pull":        "Rug Pull",
    "rug-pull":        "Rug Pull",
    "phishing":        "Phishing",
    "investment scam": "Investment Scam",
    "ponzi":           "Ponzi",
    "airdrop":         "Airdrop Scam",
    "nft":             "NFT Scam",
    "mixer":           "Mixer Abuse",
    "sim swap":        "SIM Swap",
    "fake exchange":   "Fake Exchange",
}

CHAIN_KEYWORDS = {
    "bitcoin":  "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH", "erc20": "ETH", "erc-20": "ETH",
    "tron":     "TRX", "trc20": "TRX", "trc-20": "TRX", "usdt-trc": "TRX",
    "binance smart chain": "BSC", "bsc": "BSC", "bnb chain": "BSC",
    "solana":   "SOL", "sol": "SOL",
}

WALLET_RE = re.compile(
    r"\b("
    r"0x[a-fA-F0-9]{40}"            # ETH/BSC
    r"|T[A-Za-z1-9]{33}"            # TRON
    r"|bc1[0-9a-z]{8,87}"           # BTC bech32
    r"|[13][a-km-zA-HJ-NP-Z1-9]{25,34}"  # BTC legacy
    r")\b"
)


def _fetch(url: str, timeout: int = 30) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    return r.text


def _strip_html(html: str) -> str:
    s = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if not m:
        return "Untitled"
    title = m.group(1).strip()
    title = re.sub(r"\s*\|\s*Chainalysis.*$", "", title)
    return title[:140]


def _extract_published(html: str) -> str | None:
    m = re.search(
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        html, re.I)
    if m:
        try:
            return datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    return None


def _detect_scam_type(text: str) -> str:
    low = text.lower()
    for k, v in SCAM_KEYWORDS.items():
        if k in low:
            return v
    return "Other"


def _detect_chains(text: str) -> str:
    low = text.lower()
    found = set()
    for k, v in CHAIN_KEYWORDS.items():
        if k in low:
            found.add(v)
    return ",".join(sorted(found))


def _detect_wallets(text: str, limit: int = 50) -> list[str]:
    found = WALLET_RE.findall(text)
    seen, uniq = set(), []
    for w in found:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
        if len(uniq) >= limit:
            break
    return uniq


def _thanatos_rewrite_it(title: str, body: str, scam_type: str,
                         chains: str, wallets: int) -> str:
    """Rewrite in italiano professionale, no copy. Sintesi factual."""
    chain_label = chains or "non specificate"
    return (
        f"<p><strong>Sintesi Thanatos.</strong> Caso classificato come "
        f"<em>{scam_type}</em>, segnalato da Chainalysis nel 2026. "
        f"Catene coinvolte: {chain_label}. "
        f"Sono stati identificati <strong>{wallets}</strong> indirizzi wallet "
        f"correlati al pattern descritto.</p>"
        f"<p>Il modus operandi rispecchia gli schemi noti del settore: "
        f"adescamento della vittima, costruzione di fiducia, dirottamento "
        f"dei fondi verso wallet multilivello, infine offuscamento tramite "
        f"servizi di mixing o exchange a controlli deboli.</p>"
        f"<p>Indicatori di rischio Thanatos: contatto non sollecitato, "
        f"promessa di rendimenti elevati e garantiti, urgenza artificiale, "
        f"richiesta di trasferimento crypto verso wallet di terzi, "
        f"insistenza su exchange poco regolamentati.</p>"
        f"<p><em>Riferimento sorgente: Chainalysis (vedi URL).</em></p>"
    )


def _excerpt(text: str, n: int = 280) -> str:
    t = text.strip()
    return t[:n] + ("…" if len(t) > n else "")


@frappe.whitelist()
def ingest_url(url: str) -> dict:
    """Estrae 1 articolo Chainalysis e crea/aggiorna Crypto Scam Intelligence."""
    html = _fetch(url)
    raw_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    title = _extract_title(html)
    published = _extract_published(html)
    plain = _strip_html(html)
    scam_type = _detect_scam_type(plain)
    chains = _detect_chains(plain)
    wallets = _detect_wallets(plain)

    existing = frappe.db.get_value("Crypto Scam Intelligence",
                                   {"source_url": url}, "name")
    if existing:
        doc = frappe.get_doc("Crypto Scam Intelligence", existing)
        action = "updated"
    else:
        doc = frappe.new_doc("Crypto Scam Intelligence")
        action = "created"

    doc.title = title
    doc.source = "Chainalysis"
    doc.source_url = url
    if published:
        doc.published_on = published
    doc.scam_type = scam_type
    doc.chains = chains
    doc.risk_level = "High" if scam_type in (
        "Pig Butchering", "Investment Scam", "Rug Pull") else "Medium"
    doc.language = "it"
    doc.summary = _thanatos_rewrite_it(title, plain, scam_type, chains, len(wallets))
    doc.wallets_observed = "\n".join(wallets)
    doc.modus_operandi = (
        "Adescamento → costruzione fiducia → trasferimento crypto su wallet "
        "multilivello → offuscamento via mixer/exchange weak-KYC."
    )
    doc.indicators = (
        "- Contatto non sollecitato\n- Promessa rendimenti garantiti\n"
        "- Urgenza artificiale\n- Wallet di terzi\n- Exchange poco regolamentati"
    )
    doc.mitigation = (
        "- Verifica controparte (KYB)\n- Sanctions/PEP screening\n"
        "- Blockchain tracing pre-trasferimento\n- Trasferimenti via custodial "
        "regolamentati\n- Reporting wallet sospetti a FIU."
    )
    doc.raw_html = _excerpt(plain, 280)
    doc.raw_hash = raw_hash
    doc.status = "Draft"
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "action": action, "scam_type": scam_type,
            "chains": chains, "wallets": len(wallets), "hash": raw_hash}


@frappe.whitelist()
def ingest_index(index_url: str = DEFAULT_INDEX, limit: int = 10) -> dict:
    """Trova link articoli nella index page e li ingerisce uno a uno."""
    html = _fetch(index_url)
    urls = []
    for m in re.finditer(r'href=["\'](https://www\.chainalysis\.com/blog/[^"\']+)["\']', html):
        u = m.group(1)
        if u.rstrip("/") == index_url.rstrip("/"):
            continue
        if u not in urls:
            urls.append(u)
        if len(urls) >= limit:
            break
    results = []
    for u in urls:
        try:
            results.append(ingest_url(u))
        except Exception as e:
            results.append({"url": u, "error": str(e)[:200]})
    return {"index": index_url, "count": len(results), "results": results}
