"""Idempotent: seed Risk Rule + Blacklist Entry per pattern crypto recovery scam.

Origine: audit di top GitHub repos per "crypto recovery" (2026-06-30) - 70%
risultati erano SEO/scam. Pattern: 'private key finder', 'non-spendable
spendable', 'flash USDT', completare mnemonic da indirizzo. Documentato in
crypto-self-custody/docs/SEGNALAZIONI.md.
"""
import frappe

RULE_NAME = "Crypto Recovery Scam Pattern"
DATASET_TAG = "MMOS Crypto Recovery Scam audit 2026-06-30"

SELECTOR = '''
import re
text = (doc.case_summary or "") + " " + (doc.case_description or "")
patterns = [
    r"private\\s+key\\s+(finder|generator|recover)",
    r"non[- ]?spendable\\s+(funds|usdt)",
    r"flash\\s+usdt|flash\\s+token",
    r"recover.*from\\s+(only\\s+)?(the\\s+)?(wallet\\s+)?address",
    r"make\\s+non[- ]?spendable\\s+spendable",
    r"complete\\s+mnemonic\\s+from\\s+address",
    r"btckeyrecovery|datrekrecovery|cryptofinder",
]
result = any(re.search(p, text, re.I) for p in patterns)
'''.strip()

DOMAINS = [
    ("btckeyrecovery.com", "Sito 'recovery service' linkato da Bitmonk-Education/Bitmonk: promette di trovare chiavi private da indirizzi, recuperare fondi 'non-spendable'. Schema furto/anticipi."),
    ("datrekrecovery.com", "Promotore Datrek Recovery (jironmarlon562). Self-promo come servizio recupero fondi da investimenti truffaldini."),
]

GITHUB_USERS = [
    ("MinightDev", "Repo BTC-Wallet-Recover (94 stelle sospette): chiede mnemonic per 'check balance' = vettore furto."),
    ("Bitmonk-Education", "Repo 'Bitmonk' (private key finder), SEO 'private key of any crypto address', linka btckeyrecovery.com."),
    ("sh1naX", "Repo 'cryptofinder' (Lost Crypto Wallets Finder), pattern SEO scam."),
    ("kampers3", "Repo 'crypto-token-recovery' e 'crypto-wallet-recovery' vuoti, solo SEO."),
    ("vertyxanserial376", "Repo 'Crypto-Wallet-Recovery' vuoto SEO."),
    ("jironmarlon562", "Repo Bitcoin-and-Other-Crypto-Assets-Investments-Recovery, advertorial Datrek Recovery."),
    ("CryptoApex23", "Repo recovery-phrase-finder: pretende di completare mnemonic da indirizzo+parti. Vettore raccolta seed."),
    ("booboomrtwix", "Repo 'Solana-FarmBot-2026': nome ingannevole, descrizione = recovery BIP-39, profilo SEO."),
]


def _upsert_rule():
    if not frappe.db.exists("DocType", "Risk Rule"):
        return None
    name = frappe.db.get_value("Risk Rule", {"rule_name": RULE_NAME}, "name")
    d = frappe.get_doc("Risk Rule", name) if name else frappe.new_doc("Risk Rule")
    if not name:
        d.rule_name = RULE_NAME
    d.enabled = 1
    d.category = "Cyber"
    d.applies_to = "Case"
    d.score_delta = 80
    d.severity = "High"
    d.selector_expression = SELECTOR
    d.match_message = ("Il case contiene linguaggio tipico delle truffe di "
                       "'crypto recovery'. NON ingaggiare il cliente come "
                       "servizio; valutare denuncia.")
    d.notes = ("Seed da thanatos_intel.install._seed_crypto_recovery_scam_blacklist "
               "(2026-06-30). Pattern in crypto-self-custody/docs/SEGNALAZIONI.md.")
    d.save(ignore_permissions=True)
    return d.name


def _upsert_blacklist(entry_type, entry_value, reason, source_url=""):
    if not frappe.db.exists("DocType", "Blacklist Entry"):
        return None
    name = frappe.db.get_value(
        "Blacklist Entry",
        {"entry_type": entry_type, "entry_value": entry_value},
        "name",
    )
    d = (frappe.get_doc("Blacklist Entry", name) if name
         else frappe.new_doc("Blacklist Entry"))
    if not name:
        d.entry_type = entry_type
        d.entry_value = entry_value
    d.risk_level = "Critical"
    d.is_active = 1
    d.verified = 1
    d.source = "Internal"
    d.source_dataset = DATASET_TAG
    d.source_url = source_url
    d.reason = reason
    d.save(ignore_permissions=True)
    return d.name


def apply():
    _upsert_rule()
    for dom, reason in DOMAINS:
        _upsert_blacklist("Domain", dom, reason, source_url=f"https://{dom}")
    for user, reason in GITHUB_USERS:
        _upsert_blacklist("Person", user, reason,
                          source_url=f"https://github.com/{user}")
    frappe.db.commit()
