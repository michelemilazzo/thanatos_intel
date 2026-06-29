"""Catalogo unificato di TUTTI gli strumenti investigativi a disposizione.

Fonde due mondi:
  • Fonti OSINT free/freemium  → osint/source_registry.SOURCES (47 fonti)
  • Servizi dati a pagamento   → osint/openapi_client.CATALOGO (8 famiglie openapi)

`capacita()` è la vista che conta per l'operatore: per ogni CAPACITÀ investigativa
dice qual è l'opzione completamente gratuita (se esiste) e quella a pagamento,
con il consiglio su cosa sfruttare prima.
"""
import frappe

# Mappa capacità → free vs paid. È la risposta a "cosa è gratis sfruttabile".
CAPACITA = [
    {"capacita": "Sanzioni / PEP / liste / adverse media", "categoria": "Compliance",
     "free": ["OpenSanctions (cache locale 285k)", "OFAC/UN/EU liste locali"],
     "paid": ["openapi risk · WW-kyc-pep/sanction/adverse"],
     "consiglio": "free", "nota": "Il free copre il 90%: aggrega OFAC/UN/EU/Interpol."},
    {"capacita": "Anagrafica azienda (esistenza, VAT, dati base)", "categoria": "Aziende",
     "free": ["VIES (validazione P.IVA UE)", "Wikidata", "OpenCorporates (free+key)"],
     "paid": ["openapi company · IT-advanced/full"],
     "consiglio": "misto", "nota": "Esistenza/VAT gratis; dati strutturati completi a pagamento."},
    {"capacita": "Soci e quote / Titolari effettivi (UBO) IT", "categoria": "Aziende",
     "free": [], "paid": ["openapi company · IT-shareholders / IT-ubo"],
     "consiglio": "paid", "nota": "Nessun free affidabile: Registro Imprese è a pagamento."},
    {"capacita": "Nome → P.IVA (risoluzione)", "categoria": "Aziende",
     "free": ["OpenCorporates (parziale, free+key)"],
     "paid": ["openapi company · IT-search → IT-start"],
     "consiglio": "paid", "nota": "Free incompleto per l'Italia; openapi è affidabile."},
    {"capacita": "Negatività / protesti / pregiudizievoli", "categoria": "Rischio",
     "free": [], "paid": ["openapi risk · IT-negativita"],
     "consiglio": "paid", "nota": "Dati CRIF/centrali rischi: solo a pagamento."},
    {"capacita": "Patrimoniale persona / beni", "categoria": "Rischio",
     "free": [], "paid": ["openapi risk · IT-patrimoniale-persona"],
     "consiglio": "paid", "nota": "Banche dati patrimoniali riservate: a pagamento."},
    {"capacita": "Catasto / immobili / ipoteche", "categoria": "Patrimonio",
     "free": [], "paid": ["openapi catasto · visura/ipotecarie"],
     "consiglio": "paid", "nota": "Agenzia Entrate: nessuna API gratuita."},
    {"capacita": "Veicoli per targa", "categoria": "Patrimonio",
     "free": [], "paid": ["openapi targa / automotive"],
     "consiglio": "paid", "nota": "PRA/Motorizzazione: solo a pagamento."},
    {"capacita": "Indirizzi / geocoding", "categoria": "Geo",
     "free": ["OpenStreetMap / Nominatim"], "paid": ["openapi geocoding"],
     "consiglio": "free", "nota": "Nominatim copre tutto: usare il free."},
    {"capacita": "Telefono (validità, operatore, paese)", "categoria": "Contatti",
     "free": ["Phone metadata offline (libphonenumber)"], "paid": ["openapi trust · phone/mobile"],
     "consiglio": "free", "nota": "Free per metadati; openapi solo se serve titolare."},
    {"capacita": "Email (validità, footprint)", "categoria": "Contatti",
     "free": ["Holehe (email→social)", "MX/SMTP check"], "paid": ["openapi trust · email", "HIBP (paid)"],
     "consiglio": "misto", "nota": "Validità gratis; reputazione/breach a pagamento."},
    {"capacita": "IBAN (validità, banca)", "categoria": "Antifrode",
     "free": ["Checksum IBAN locale", "openiban.com"], "paid": ["openapi trust · iban"],
     "consiglio": "misto", "nota": "Validità+banca gratis; titolare solo a pagamento."},
    {"capacita": "IP / URL / dominio / cyber", "categoria": "Cyber",
     "free": ["RDAP/WHOIS", "AbuseIPDB", "urlscan.io", "VirusTotal", "Shodan", "ViewDNS", "SecurityTrails"],
     "paid": ["openapi trust · ip/url"],
     "consiglio": "free", "nota": "Ecosistema free ricchissimo: usare quello."},
    {"capacita": "Wallet crypto / tracing", "categoria": "Crypto",
     "free": ["blockchain.info (BTC)", "TronScan (TRON/USDT)", "Etherscan (ETH)"],
     "paid": ["Arkham (attribution)"],
     "consiglio": "free", "nota": "Movimenti gratis; attribution identità a pagamento."},
    {"capacita": "Contenzioso / giudiziario", "categoria": "Giudiziario",
     "free": ["CourtListener (US)"], "paid": [],
     "consiglio": "free", "nota": "US gratis; IT solo via accesso manuale tribunali."},
    {"capacita": "Archivio web / storico siti", "categoria": "Media",
     "free": ["Wayback Machine", "CommonCrawl"], "paid": [],
     "consiglio": "free", "nota": "Completamente gratuito."},
    {"capacita": "Username / social / breach password", "categoria": "Social",
     "free": ["Username multi-piattaforma", "Pwned Passwords", "Sherlock/Maigret"], "paid": [],
     "consiglio": "free", "nota": "Gratuito."},
    {"capacita": "Navi / aerei (trasporti)", "categoria": "Trasporti",
     "free": ["OpenSky (aerei)", "Screening nave sanzioni"], "paid": ["Equasis/MarineTraffic (spec)"],
     "consiglio": "free", "nota": "Tracking base gratis."},
]


def _free_sources():
    try:
        from thanatos_intel.osint.source_registry import SOURCES
    except Exception:
        return []
    out = []
    for s in SOURCES:
        out.append({"name": s.get("name"), "tier": s.get("tier"), "status": s.get("status"),
                    "categoria": s.get("category"), "targets": s.get("targets")})
    return out


@frappe.whitelist()
def catalogo_completo():
    """Tutti gli strumenti: capacità (free vs paid), fonti free, famiglie openapi."""
    try:
        from thanatos_intel.osint.openapi_client import CATALOGO, _token
        openapi = CATALOGO
        connesso = bool(_token())
    except Exception:
        openapi, connesso = [], False
    fonti = _free_sources()
    free_n = len([f for f in fonti if f["tier"] in ("free_auto", "free_key")])
    return {
        "capacita": CAPACITA,
        "fonti_free": fonti,
        "openapi": openapi,
        "stats": {"capacita": len(CAPACITA), "fonti_totali": len(fonti),
                  "fonti_gratuite": free_n, "famiglie_openapi": len(openapi),
                  "openapi_connesso": connesso,
                  "capacita_con_free": len([c for c in CAPACITA if c["free"]])},
    }
