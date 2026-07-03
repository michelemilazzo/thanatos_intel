"""Idempotent: seed Risk Rule + Blacklist Entry per pattern crypto recovery scam.

Origine: audit di top GitHub repos per "crypto recovery" (2026-06-30) - 70%
risultati erano SEO/scam. Pattern: 'private key finder', 'non-spendable
spendable', 'flash USDT', completare mnemonic da indirizzo. Documentato in
crypto-self-custody/docs/SEGNALAZIONI.md.

Aggiornamento 2026-07-03: aggiunto pattern crypto-clipper / address-replacement
(malware che sostituisce l'indirizzo BTC in pagina, es. Tampermonkey userscript
zile42O/g2a-drainer che dirotta il QR di pagamento su g2a.com/payment verso
api.zile42o.dev).
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

# --- Crypto clipper / address-replacement (audit 2026-07-03) ---
# Malware che intercetta l'indirizzo crypto in pagina/clipboard e lo sostituisce
# con quello dell'attaccante, dirottando il pagamento. Distinto dal recovery
# scam: qui la vittima paga volontariamente ma verso l'indirizzo sbagliato.
CLIPPER_RULE_NAME = "Crypto Clipper / Address Replacement"
CLIPPER_DATASET_TAG = "MMOS Crypto Clipper audit 2026-07-03"

CLIPPER_SELECTOR = '''
import re
text = (doc.case_summary or "") + " " + (doc.case_description or "")
patterns = [
    r"clipper",
    r"(replac|swap|chang)\\w*\\s+(the\\s+)?(btc|bitcoin|wallet|crypto)\\s+address",
    r"address\\s+(was\\s+)?(replac|swap|chang)",
    r"(paid|sent).*(wrong|different|other)\\s+address",
    r"tampermonkey|userscript|greasemonkey",
    r"g2a[- ]?drainer|cryptoqr|zile42o",
    r"qr\\s+code.*(swap|replac|redirect|hijack)",
]
result = any(re.search(p, text, re.I) for p in patterns)
'''.strip()

CLIPPER_DOMAINS = [
    ("zile42o.dev", "Infra dell'autore del clipper zile42O (g2a-drainer). Dominio di controllo del malware di sostituzione indirizzo BTC."),
    ("api.zile42o.dev", "Endpoint C2/exfil del clipper g2a-drainer: serve il QR/indirizzo BTC dell'attaccante (/cryptoqr/api.php) sostituendolo in pagina su g2a.com/payment."),
]

CLIPPER_GITHUB_USERS = [
    ("zile42O", "Autore del repo g2a-drainer: userscript Tampermonkey che trova l'indirizzo BTC via regex sulla pagina di pagamento G2A e lo sostituisce con il proprio, dirottando il QR verso api.zile42o.dev. Clipper/payment-hijack."),
]


def _upsert_rule(rule_name, selector, score_delta, severity, match_message, notes):
    if not frappe.db.exists("DocType", "Risk Rule"):
        return None
    name = frappe.db.get_value("Risk Rule", {"rule_name": rule_name}, "name")
    d = frappe.get_doc("Risk Rule", name) if name else frappe.new_doc("Risk Rule")
    if not name:
        d.rule_name = rule_name
    d.enabled = 1
    d.category = "Cyber"
    d.applies_to = "Case"
    d.score_delta = score_delta
    d.severity = severity
    d.selector_expression = selector
    d.match_message = match_message
    d.notes = notes
    d.save(ignore_permissions=True)
    return d.name


def _upsert_blacklist(entry_type, entry_value, reason, dataset, source_url=""):
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
    d.source_dataset = dataset
    d.source_url = source_url
    d.reason = reason
    d.save(ignore_permissions=True)
    return d.name


def apply():
    _upsert_rule(
        RULE_NAME, SELECTOR, 80, "High",
        ("Il case contiene linguaggio tipico delle truffe di 'crypto recovery'. "
         "NON ingaggiare il cliente come servizio; valutare denuncia."),
        ("Seed da thanatos_intel.install._seed_crypto_recovery_scam_blacklist "
         "(2026-06-30). Pattern in crypto-self-custody/docs/SEGNALAZIONI.md."),
    )
    _upsert_rule(
        CLIPPER_RULE_NAME, CLIPPER_SELECTOR, 80, "High",
        ("Il case descrive un crypto-clipper / sostituzione indirizzo (pagamento "
         "dirottato). Trattare come vittima di malware; NON sviluppare strumenti "
         "analoghi. Raccogliere IOC (dominio C2, indirizzo attaccante)."),
        ("Seed 2026-07-03 da audit repo zile42O/g2a-drainer (clipper Tampermonkey "
         "su g2a.com/payment, exfil api.zile42o.dev)."),
    )
    for dom, reason in DOMAINS:
        _upsert_blacklist("Domain", dom, reason, DATASET_TAG, source_url=f"https://{dom}")
    for user, reason in GITHUB_USERS:
        _upsert_blacklist("Person", user, reason, DATASET_TAG,
                          source_url=f"https://github.com/{user}")
    for dom, reason in CLIPPER_DOMAINS:
        _upsert_blacklist("Domain", dom, reason, CLIPPER_DATASET_TAG,
                          source_url=f"https://{dom}")
    for user, reason in CLIPPER_GITHUB_USERS:
        _upsert_blacklist("Person", user, reason, CLIPPER_DATASET_TAG,
                          source_url=f"https://github.com/{user}")
    frappe.db.commit()
