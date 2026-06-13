"""
OSINT Source Registry & Recommender — Thanatos Intel.

Software che cataloga le fonti OSINT, le classifica per modalità di accesso
e le SUGGERISCE per ogni tipo di target, eseguendo automaticamente quelle
gratuite e automatiche.

Tier (modalità di accesso):
  free_auto   — gratis e automatica (nessuna auth, gira subito)
  free_key    — registrazione senza carta di credito (API key gratuita)
  trial       — periodo di prova (poi a pagamento)
  specialist  — specialistica: da valutare se serve o sostituibile con più tool
  manual      — gratis ma solo web/CLI, nessuna API server-side
  paid        — a pagamento

Status (stato integrazione):
  live          — connettore integrato, gira ora senza chiave
  needs_key     — connettore integrato, serve una key gratuita (altrimenti stub)
  evaluation    — sotto valutazione (vedi `substitutes`/`note`)
  substitutable — copribile da una combinazione di altre fonti già integrate
  manual_only   — nessuna API: uso solo da interfaccia web / CLI
  planned       — connettore da costruire
"""
import frappe

# ── Catalogo classificato ──────────────────────────────────────────────────
# connector = dotted path whitelisted; None se non eseguibile server-side.
SOURCES = [
    # ===== FREE + AUTOMATICHE (gira subito, no auth) =====
    dict(key="rdap", name="RDAP (WHOIS)", tier="free_auto", status="live",
         category="cyber", targets=["Domain", "Url"],
         connector="thanatos_intel.osint.engine.lookup_domain",
         url="https://rdap.org", note="Registrazione dominio, no key."),
    dict(key="opensanctions_local", name="OpenSanctions (cache locale 285k)",
         tier="free_auto", status="live", category="sanzioni",
         targets=["Company", "Person", "Username", "Wallet"],
         connector="thanatos_intel.osint.free_sources.screen_sanctions",
         url="https://opensanctions.org",
         note="Aggrega OFAC/UN/EU/Interpol; refresh 24h; offline, istantaneo."),
    dict(key="ofac_un_eu_local", name="OFAC/UN/EU liste (blacklist locale)",
         tier="free_auto", status="live", category="sanzioni",
         targets=["Company", "Person"],
         connector=None, note="Ingest XML/CSV offline rinfrescato ogni 24h "
         "(integrations.blacklist_ingest). Consultato via blacklist e opensanctions_local."),
    dict(key="wayback", name="Wayback Machine", tier="free_auto", status="live",
         category="media", targets=["Domain", "Url"],
         connector="thanatos_intel.osint.free_sources.lookup_wayback",
         url="https://web.archive.org", note="Snapshot storici, no key."),
    dict(key="commoncrawl", name="CommonCrawl", tier="free_auto", status="live",
         category="media", targets=["Domain"],
         connector="thanatos_intel.osint.free_sources.lookup_commoncrawl",
         url="https://commoncrawl.org", note="URL indicizzati del dominio."),
    dict(key="courtlistener", name="CourtListener (PACER free)", tier="free_auto",
         status="live", category="giudiziario", targets=["Company", "Person"],
         connector="thanatos_intel.osint.free_sources.lookup_courtlistener",
         url="https://courtlistener.com", note="Procedimenti federali USA, no key."),
    dict(key="wikidata", name="Wikidata", tier="free_auto", status="live",
         category="aziende", targets=["Company", "Person"],
         connector="thanatos_intel.osint.free_sources.lookup_wikidata",
         url="https://wikidata.org", note="Entità collegate, no key."),
    dict(key="wallet_btc", name="Blockchain.info (BTC)", tier="free_auto",
         status="live", category="crypto", targets=["Wallet"],
         connector="thanatos_intel.osint.free_sources.lookup_btc_wallet",
         url="https://blockchain.com", note="Saldo/tx BTC, no key."),
    dict(key="wallet_tron", name="TronScan (TRON/USDT)", tier="free_auto",
         status="live", category="crypto", targets=["Wallet"],
         connector="thanatos_intel.osint.free_sources.lookup_tron_wallet",
         url="https://tronscan.org", note="Saldo/tx TRC-20, no key."),
    dict(key="username", name="Username multi-piattaforma", tier="free_auto",
         status="live", category="social", targets=["Username"],
         connector="thanatos_intel.osint.free_sources.lookup_username",
         url="", note="Check presenza su 6 piattaforme pubbliche."),
    dict(key="phone_meta", name="Phone metadata (offline)", tier="free_auto",
         status="live", category="persone", targets=["Phone"],
         connector="thanatos_intel.osint.free_sources.lookup_phone",
         url="", note="Paese/validità/rischio da prefisso E.164, offline."),
    dict(key="opensky", name="OpenSky (aircraft DB)", tier="free_auto",
         status="live", category="trasporti", targets=["Aircraft"],
         connector="thanatos_intel.osint.free_sources.lookup_flight",
         url="https://opensky-network.org", note="Anagrafica aeromobile da ICAO24."),
    dict(key="vessel_sanctions", name="Screening nave (sanzioni)", tier="free_auto",
         status="live", category="trasporti", targets=["Vessel"],
         connector="thanatos_intel.osint.free_sources.lookup_vessel",
         url="", note="Nave vs liste sanzioni, offline."),
    dict(key="pwnedpasswords", name="Pwned Passwords (k-anon)", tier="free_auto",
         status="live", category="breach", targets=["Password"],
         connector="thanatos_intel.osint.free_sources.lookup_pwned_password",
         url="https://haveibeenpwned.com/Passwords",
         note="Quante volte una password è nei breach (k-anonymity, no key)."),
    dict(key="nominatim", name="OpenStreetMap / Nominatim", tier="free_auto",
         status="live", category="geo", targets=["Address"],
         connector="thanatos_intel.osint.free_sources.lookup_address",
         url="https://nominatim.openstreetmap.org", note="Geocoding indirizzo→coordinate, no key."),

    # ===== REGISTRAZIONE SENZA CARTA (key gratuita) =====
    dict(key="hibp", name="Have I Been Pwned (breach API)", tier="paid",
         status="evaluation", category="breach", targets=["Email"],
         connector="thanatos_intel.osint.engine.lookup_email",
         needs="hibp_api_key", url="https://haveibeenpwned.com",
         substitutes=["pwnedpasswords", "intelx", "holehe"],
         note="API breach a pagamento (costosa) — ESCLUSA per ora. Le password "
         "restano gratis via Pwned Passwords; per email valutare Holehe/IntelX."),
    dict(key="abuseipdb", name="AbuseIPDB", tier="free_key", status="needs_key",
         category="cyber", targets=["IP"],
         connector="thanatos_intel.osint.engine.lookup_ip",
         needs="abuseipdb_api_key", url="https://abuseipdb.com"),
    dict(key="ipinfo", name="IPinfo", tier="free_key", status="needs_key",
         category="cyber", targets=["IP"],
         connector="thanatos_intel.osint.engine.lookup_ipinfo",
         needs="ipinfo_token", url="https://ipinfo.io"),
    dict(key="virustotal", name="VirusTotal", tier="free_key", status="needs_key",
         category="cyber", targets=["Hash", "IP", "Domain", "Url"],
         connector="thanatos_intel.osint.engine.lookup_virustotal",
         needs="virustotal_api_key", url="https://virustotal.com"),
    dict(key="urlscan", name="urlscan.io", tier="free_key", status="needs_key",
         category="cyber", targets=["Url", "Domain"],
         connector="thanatos_intel.osint.engine.lookup_urlscan",
         needs="urlscan_api_key", url="https://urlscan.io"),
    dict(key="shodan", name="Shodan", tier="free_key", status="needs_key",
         category="cyber", targets=["IP"],
         connector="thanatos_intel.osint.engine.lookup_shodan",
         needs="shodan_api_key", url="https://shodan.io"),
    dict(key="censys", name="Censys", tier="free_key", status="needs_key",
         category="cyber", targets=["IP"],
         connector="thanatos_intel.osint.engine.lookup_censys",
         needs="censys_api_id", url="https://censys.io"),
    dict(key="securitytrails", name="SecurityTrails", tier="free_key", status="needs_key",
         category="cyber", targets=["Domain"],
         connector="thanatos_intel.osint.engine.lookup_dns_history",
         needs="securitytrails_api_key", url="https://securitytrails.com"),
    dict(key="opencorporates", name="OpenCorporates", tier="free_key", status="needs_key",
         category="aziende", targets=["Company"],
         connector="thanatos_intel.osint.engine.lookup_company",
         needs="opencorporates_api_key", url="https://opencorporates.com"),
    dict(key="etherscan", name="Etherscan (ETH)", tier="free_key", status="needs_key",
         category="crypto", targets=["Wallet"],
         connector="thanatos_intel.osint.free_sources.lookup_eth_wallet",
         needs="etherscan_api_key", url="https://etherscan.io"),
    dict(key="viewdns", name="ViewDNS", tier="free_key", status="needs_key",
         category="cyber", targets=["Domain"],
         connector="thanatos_intel.osint.free_sources.lookup_viewdns_iphistory",
         needs="viewdns_api_key", url="https://viewdns.info"),
    dict(key="companies_house", name="Companies House UK", tier="free_key",
         status="evaluation", category="aziende", targets=["Company"],
         connector=None,
         needs="companies_house_api_key", url="https://find-and-update.company-information.service.gov.uk",
         note="kyb_lookup richiede un'Investigation Entity esistente + company number UK "
         "→ non auto-eseguibile su nome libero; integrare un connettore generico per nome."),
    dict(key="greynoise", name="GreyNoise Community", tier="free_key", status="needs_key",
         category="cyber", targets=["IP"],
         connector="thanatos_intel.osint.free_sources.lookup_greynoise",
         needs="greynoise_api_key", url="https://greynoise.io",
         note="Distingue rumore internet da attività targetizzata."),
    dict(key="otx", name="OTX AlienVault", tier="free_key", status="needs_key",
         category="cyber", targets=["IP", "Domain", "Hash"],
         connector="thanatos_intel.osint.free_sources.lookup_otx",
         needs="otx_api_key", url="https://otx.alienvault.com"),
    dict(key="pulsedive", name="Pulsedive", tier="free_key", status="needs_key",
         category="cyber", targets=["IP", "Domain", "Url"],
         connector="thanatos_intel.osint.free_sources.lookup_pulsedive",
         needs="pulsedive_api_key", url="https://pulsedive.com"),
    dict(key="mapillary", name="Mapillary", tier="free_key", status="needs_key",
         category="geo", targets=["Address"],
         connector="thanatos_intel.osint.free_sources.lookup_mapillary",
         needs="mapillary_token", url="https://mapillary.com"),

    # ===== IN PROVA (trial, poi a pagamento) =====
    dict(key="sentinel_hub", name="Sentinel Hub (satellite)", tier="trial",
         status="evaluation", category="geo", targets=["Address"], connector=None,
         url="https://sentinel-hub.com",
         note="Trial 30gg. Sostituibile per molti casi da EO Browser manuale."),
    dict(key="serpapi", name="SerpAPI (Google News)", tier="trial",
         status="evaluation", category="media", targets=["Company", "Person"],
         connector=None, needs="serpapi_key", url="https://serpapi.com",
         note="100 ricerche/mese free. Valutare vs scraping Google News diretto."),
    dict(key="intelx", name="Intelligence X", tier="trial", status="evaluation",
         category="breach", targets=["Email", "Domain"], connector=None,
         needs="intelx_key", url="https://intelx.io",
         note="Tier free molto limitato; valutare per dark/paste."),

    # ===== SPECIALISTICHE (valutare se servono o sostituibili) =====
    dict(key="arkham", name="Arkham (attribution wallet)", tier="specialist",
         status="evaluation", category="crypto", targets=["Wallet"],
         connector="thanatos_intel.osint.arkham.attribute",
         needs="arkham_api_key", url="https://arkhamintelligence.com",
         substitutes=["wallet_btc", "wallet_tron", "etherscan", "opensanctions_local"],
         note="Attribution avanzata. Per il base copribile da explorer + sanzioni."),
    dict(key="equasis", name="Equasis (ship safety)", tier="specialist",
         status="evaluation", category="trasporti", targets=["Vessel"], connector=None,
         url="https://equasis.org", substitutes=["vessel_sanctions", "opensky"],
         note="Richiede login. Per ownership/PSC; valutare scraping autenticato."),
    dict(key="maltego", name="Maltego", tier="specialist", status="evaluation",
         category="aziende", targets=["Company", "Person", "Domain"], connector=None,
         url="https://maltego.com", substitutes=["opencorporates", "wikidata", "courtlistener"],
         note="Graph analysis. Sostituibile con grafo interno + connettori esistenti."),
    dict(key="breadcrumbs_oxt", name="Breadcrumbs / OXT (crypto graph)",
         tier="specialist", status="substitutable", category="crypto",
         targets=["Wallet"], connector=None, url="https://breadcrumbs.app",
         substitutes=["wallet_btc", "blockchain_deep"],
         note="Clustering BTC. Copribile da blockchain_deep.trace_funds interno."),

    # ===== MANUALI (gratis ma solo web/CLI) =====
    dict(key="dnsdumpster", name="DNSDumpster", tier="manual", status="manual_only",
         category="cyber", targets=["Domain"], connector=None,
         url="https://dnsdumpster.com", substitutes=["securitytrails", "viewdns"]),
    dict(key="sherlock", name="Sherlock/Maigret (CLI)", tier="manual",
         status="substitutable", category="social", targets=["Username"], connector=None,
         url="https://github.com/sherlock-project/sherlock",
         substitutes=["username"], note="CLI 400+ siti; il connettore username copre i principali."),
    dict(key="holehe", name="Holehe (email→social)", tier="manual",
         status="needs_key", category="social", targets=["Email"],
         connector="thanatos_intel.osint.free_sources.lookup_holehe",
         url="https://github.com/megadose/holehe", note="Connettore pronto; serve CLI holehe installata."),
    dict(key="ghunt", name="GHunt (Google account CLI)", tier="manual",
         status="evaluation", category="social", targets=["Email"], connector=None,
         url="https://github.com/mxrch/ghunt", note="Richiede cookie Google."),
    dict(key="exiftool", name="ExifTool (metadata)", tier="free_auto",
         status="live", category="immagini", targets=["File"],
         connector="thanatos_intel.osint.free_sources.lookup_exiftool",
         url="https://exiftool.org", note="Binario exiftool installato sul bench OSINT."),
    dict(key="tineye", name="TinEye (reverse image)", tier="manual", status="manual_only",
         category="immagini", targets=["File"], connector=None, url="https://tineye.com"),
    dict(key="google_earth", name="Google Earth Pro", tier="manual", status="manual_only",
         category="geo", targets=["Address"], connector=None, url="https://earth.google.com"),
    dict(key="marinetraffic", name="MarineTraffic/VesselFinder", tier="manual",
         status="substitutable", category="trasporti", targets=["Vessel"], connector=None,
         url="https://marinetraffic.com", substitutes=["vessel_sanctions"],
         note="AIS live web; tracking real-time non automatizzato free."),
    dict(key="flightradar24", name="FlightRadar24", tier="manual", status="substitutable",
         category="trasporti", targets=["Aircraft"], connector=None,
         url="https://flightradar24.com", substitutes=["opensky"]),
]

TIER_LABEL = {
    "free_auto": "Gratis & automatica",
    "free_key": "Registrazione senza carta",
    "trial": "In prova",
    "specialist": "Specialistica (valutare)",
    "manual": "Manuale (web/CLI)",
    "paid": "A pagamento",
}
TIER_ORDER = ["free_auto", "free_key", "trial", "specialist", "manual", "paid"]


def _by_key():
    return {s["key"]: s for s in SOURCES}


# Credenziali aggiuntive richieste oltre `needs` (es. Censys id+secret).
_EXTRA_NEEDS = {"censys": ["censys_api_secret"]}


def _operational(s: dict) -> bool:
    """True se la fonte è eseguibile ORA: ha un connettore e
    (è gratis+automatica live) OPPURE (richiede una key che È configurata)."""
    if not s.get("connector"):
        return False
    needs = s.get("needs")
    if needs:
        if not frappe.conf.get(needs):
            return False
        for extra in _EXTRA_NEEDS.get(s["key"], []):
            if not frappe.conf.get(extra):
                return False
        return True
    # nessuna key richiesta: operativa se marcata live (free_auto o CLI installata)
    return s.get("status") == "live"


@frappe.whitelist()
def suggest(target_type: str, target_value: str = "") -> dict:
    """Suggerisce le fonti per un target, raggruppate per tier.

    Ritorna per ogni tier la lista fonti, con flag:
      runnable_now  → free_auto + status live (eseguibile subito)
      needs_setup   → serve una key gratuita
    """
    tt = (target_type or "").strip()
    relevant = [s for s in SOURCES if tt in s.get("targets", [])]
    groups = []
    for tier in TIER_ORDER:
        items = [_decorate(s) for s in relevant if s["tier"] == tier]
        if items:
            groups.append({"tier": tier, "label": TIER_LABEL[tier], "sources": items})
    return {
        "target_type": tt,
        "target_value": target_value,
        "total": len(relevant),
        "runnable_now": [s["key"] for s in relevant if _operational(s)],
        "needs_setup": [s["key"] for s in relevant
                        if s.get("needs") and not _operational(s)],
        "evaluation": [s["key"] for s in relevant if s["status"] == "evaluation"],
        "groups": groups,
    }


def _decorate(s: dict) -> dict:
    d = dict(s)
    d["tier_label"] = TIER_LABEL.get(s["tier"], s["tier"])
    op = _operational(s)
    d["operational"] = op
    d["runnable"] = op
    # stato effettivo per la UI: una needs_key configurata risulta 'active'
    d["effective_status"] = "active" if (op and s.get("needs")) else s["status"]
    subs = s.get("substitutes") or []
    by = _by_key()
    d["substitutes_names"] = [by[k]["name"] for k in subs if k in by]
    return d


@frappe.whitelist()
def auto_run(target_type: str, target_value: str) -> dict:
    """Esegue TUTTE le fonti OPERATIVE per il target: gratis+automatiche e
    quelle a chiave già configurata. Aggrega i risultati.

    Le fonti che richiedono una key non ancora configurata o da valutare
    NON vengono eseguite: restano come suggerimenti.
    """
    tt = (target_type or "").strip()
    val = (target_value or "").strip()
    if not val:
        frappe.throw("target_value mancante")
    results = {}
    ran = []
    for s in SOURCES:
        if tt not in s.get("targets", []):
            continue
        if not _operational(s):
            continue
        try:
            fn = frappe.get_attr(s["connector"])
            results[s["key"]] = fn(val)
            ran.append(s["key"])
        except Exception as e:
            results[s["key"]] = {"error": str(e)[:200], "source": s["key"]}
    sugg = suggest(tt, val)
    return {
        "target_type": tt, "target_value": val,
        "executed": ran, "results": results,
        "suggested_with_key": sugg["needs_setup"],
        "under_evaluation": sugg["evaluation"],
    }


@frappe.whitelist()
def overview() -> dict:
    """Quadro gestione: conteggi per tier e stato, e voci da valutare."""
    by_tier, by_status = {}, {}
    for s in SOURCES:
        by_tier[s["tier"]] = by_tier.get(s["tier"], 0) + 1
        by_status[s["status"]] = by_status.get(s["status"], 0) + 1
    evaluation = [_decorate(s) for s in SOURCES
                  if s["status"] in ("evaluation", "substitutable", "planned")]
    operational = sum(1 for s in SOURCES if _operational(s))
    keyed_active = sum(1 for s in SOURCES if s.get("needs") and _operational(s))
    return {
        "total": len(SOURCES),
        "operational": operational,
        "keyed_active": keyed_active,
        "by_tier": [{"tier": t, "label": TIER_LABEL[t], "count": by_tier.get(t, 0)}
                    for t in TIER_ORDER if by_tier.get(t)],
        "by_status": by_status,
        "to_evaluate": evaluation,
    }
