"""Catalogo unificato di TUTTI gli strumenti investigativi a disposizione.

Fonde due mondi:
  • Fonti OSINT free/freemium  → osint/source_registry.SOURCES (47 fonti)
  • Servizi dati a pagamento   → osint/openapi_client.CATALOGO (8 famiglie openapi)

`capacita()` è la vista che conta per l'operatore: per ogni CAPACITÀ investigativa
dice qual è l'opzione completamente gratuita (se esiste) e quella a pagamento,
con il consiglio su cosa sfruttare prima.
"""
import frappe

# Modello di business: il cliente paga SEMPRE il servizio di indagine (Thanatos),
# e MMOS fattura a Thanatos il consumo openapi (a costo+markup). Quindi la scelta
# free-vs-paid NON è solo costo: conta la COMPLETEZZA del dato. Regola:
#  • usa free quando il dato è completo quanto il paid (sanzioni, geo, telefono base, crypto, cyber, web)
#  • usa paid quando aggiunge dati decisivi e fatturabili (bilanci/soci/UBO, IBAN titolare, liveness, catasto, patrimoniale)
MODELLO_BILLING = {
    "catena": "Cliente → Thanatos (servizio indagine) → MMOS (consumo openapi, costo+markup)",
    "principio": "Il cliente paga comunque: scegli per completezza del dato, non per il nostro costo.",
}

# free_dati/paid_dati = cosa restituisce ciascuno; gap = cosa MANCA nel free.
CAPACITA = [
    {"capacita": "Sanzioni / PEP / liste / adverse media", "categoria": "Compliance",
     "free": ["OpenSanctions (cache locale 285k)", "OFAC/UN/EU liste locali"],
     "paid": ["openapi risk · WW-kyc-pep/sanction/adverse"],
     "free_dati": "nome, alias, nascita, nazionalità, ruolo PEP, liste/sanzioni, dataset, score",
     "paid_dati": "stessi campi + foto + organization_details + locations strutturate",
     "gap": "solo foto e dettagli organizzazione — irrilevanti per lo screening",
     "consiglio": "free", "nota": "Free ≈ paid: aggrega OFAC/UN/EU/Interpol. Usa il free."},
    {"capacita": "Anagrafica azienda (bilanci, struttura)", "categoria": "Aziende",
     "free": ["VIES (validazione P.IVA UE)", "Wikidata"],
     "paid": ["openapi company · IT-advanced/full"],
     "free_dati": "VIES: solo esistenza + denominazione + indirizzo",
     "paid_dati": "70+ campi: bilanci (fatturato/utile/PN/dipendenti), KPI, soci, amministratori, ATECO, PEC, gruppi societari, gare pubbliche, debiti/crediti, web&social",
     "gap": "TUTTO tranne nome/indirizzo: bilanci, soci, amministratori, KPI, gruppi",
     "consiglio": "paid", "nota": "Free solo per check esistenza. Per la DD serve il paid."},
    {"capacita": "Soci e quote / Titolari effettivi (UBO) IT", "categoria": "Aziende",
     "free": [], "paid": ["openapi company · IT-shareholders / IT-ubo"],
     "free_dati": "—", "paid_dati": "soci con % quota + CF; UBO persona fisica con CF, data/luogo nascita, indirizzo",
     "gap": "nessun free affidabile (Registro Imprese a pagamento)",
     "consiglio": "paid", "nota": "Indispensabile per il cluster/gruppo. Solo paid."},
    {"capacita": "Nome → P.IVA (risoluzione)", "categoria": "Aziende",
     "free": ["OpenCorporates (parziale, free+key)"],
     "paid": ["openapi company · IT-search → IT-start"],
     "free_dati": "OpenCorporates: copertura IT parziale e non sempre aggiornata",
     "paid_dati": "match affidabile denominazione → P.IVA/CF + sede",
     "gap": "affidabilità e copertura completa IT",
     "consiglio": "paid", "nota": "Free incompleto per l'Italia; openapi è affidabile."},
    {"capacita": "Negatività / protesti / pregiudizievoli", "categoria": "Rischio",
     "free": [], "paid": ["openapi risk · IT-negativita"],
     "free_dati": "—", "paid_dati": "protesti, pregiudizievoli, procedure, eventi negativi",
     "gap": "nessun free (dati CRIF/centrali rischi)",
     "consiglio": "paid", "nota": "Solo a pagamento."},
    {"capacita": "Patrimoniale persona / beni", "categoria": "Rischio",
     "free": [], "paid": ["openapi risk · IT-patrimoniale-persona"],
     "free_dati": "—", "paid_dati": "beni intestati, immobili, partecipazioni, cariche",
     "gap": "nessun free (banche dati riservate)",
     "consiglio": "paid", "nota": "Solo a pagamento."},
    {"capacita": "Catasto / immobili / ipoteche", "categoria": "Patrimonio",
     "free": [], "paid": ["openapi catasto · visura/ipotecarie"],
     "free_dati": "—", "paid_dati": "visura catastale, ispezione ipotecaria, note, mappe",
     "gap": "nessun free (Agenzia Entrate)",
     "consiglio": "paid", "nota": "Solo a pagamento."},
    {"capacita": "Veicoli per targa", "categoria": "Patrimonio",
     "free": [], "paid": ["openapi targa / automotive"],
     "free_dati": "—", "paid_dati": "marca/modello, intestatario, assicurazione, revisioni",
     "gap": "nessun free (PRA/Motorizzazione)",
     "consiglio": "paid", "nota": "Solo a pagamento."},
    {"capacita": "Indirizzi / geocoding", "categoria": "Geo",
     "free": ["OpenStreetMap / Nominatim"], "paid": ["openapi geocoding"],
     "free_dati": "coordinate, indirizzo normalizzato, componenti (via/città/CAP/paese)",
     "paid_dati": "stessi dati",
     "gap": "nessuno", "consiglio": "free", "nota": "Identici. Usa Nominatim (free)."},
    {"capacita": "Telefono (validità, operatore, paese)", "categoria": "Contatti",
     "free": ["Phone metadata offline (libphonenumber)"], "paid": ["openapi trust · phone/mobile"],
     "free_dati": "validità formato, paese, tipo linea, operatore d'origine",
     "paid_dati": "+ HLR live (attivo/raggiungibile), portabilità, roaming",
     "gap": "liveness/HLR (numero attivo) e portabilità",
     "consiglio": "misto", "nota": "Free per metadati; paid se serve sapere se è attivo."},
    {"capacita": "Email (validità, footprint)", "categoria": "Contatti",
     "free": ["Holehe (email→social)", "MX/SMTP check"], "paid": ["openapi trust · email", "HIBP (paid)"],
     "free_dati": "validità sintassi+MX, presenza su servizi (Holehe)",
     "paid_dati": "+ reputazione, deliverability, data breach (HIBP)",
     "gap": "reputazione e breach history",
     "consiglio": "misto", "nota": "Validità gratis; reputazione/breach a pagamento."},
    {"capacita": "IBAN (validità, banca, titolare)", "categoria": "Antifrode",
     "free": ["Checksum IBAN locale", "openiban.com"], "paid": ["openapi trust · iban"],
     "free_dati": "validità checksum, banca, BIC, paese",
     "paid_dati": "+ TITOLARE del conto, stato conto",
     "gap": "il titolare del conto (il dato investigativo chiave)",
     "consiglio": "misto", "nota": "Validità+banca gratis; per il titolare serve il paid."},
    {"capacita": "IP / URL / dominio / cyber", "categoria": "Cyber",
     "free": ["RDAP/WHOIS", "AbuseIPDB", "urlscan.io", "VirusTotal", "Shodan", "ViewDNS", "SecurityTrails"],
     "paid": ["openapi trust · ip/url"],
     "free_dati": "owner/ASN, geo, abuse score, porte/servizi, storico DNS, reputazione URL",
     "paid_dati": "risk score + proxy/VPN detection",
     "gap": "punteggio di rischio aggregato (ricostruibile dai free)",
     "consiglio": "free", "nota": "Ecosistema free ricchissimo: usare quello."},
    {"capacita": "Wallet crypto / tracing", "categoria": "Crypto",
     "free": ["blockchain.info (BTC)", "TronScan (TRON/USDT)", "Etherscan (ETH)"],
     "paid": ["Arkham (attribution)"],
     "free_dati": "saldo, transazioni, controparti, token",
     "paid_dati": "+ attribuzione identità reale del wallet (exchange/entità)",
     "gap": "l'attribuzione a un'identità reale",
     "consiglio": "misto", "nota": "Movimenti gratis; attribution identità a pagamento."},
    {"capacita": "Contenzioso / giudiziario", "categoria": "Giudiziario",
     "free": ["CourtListener (US)"], "paid": [],
     "free_dati": "cause e atti USA (PACER)", "paid_dati": "—",
     "gap": "IT non coperto da API (accesso manuale tribunali)",
     "consiglio": "free", "nota": "US gratis; IT solo manuale."},
    {"capacita": "Archivio web / storico siti", "categoria": "Media",
     "free": ["Wayback Machine", "CommonCrawl"], "paid": [],
     "free_dati": "snapshot storici, contenuti archiviati", "paid_dati": "—",
     "gap": "nessuno", "consiglio": "free", "nota": "Completamente gratuito."},
    {"capacita": "Username / social / breach password", "categoria": "Social",
     "free": ["Username multi-piattaforma", "Pwned Passwords", "Sherlock/Maigret"], "paid": [],
     "free_dati": "presenza username su N piattaforme, password compromesse (k-anon)", "paid_dati": "—",
     "gap": "nessuno", "consiglio": "free", "nota": "Gratuito."},
    {"capacita": "Navi / aerei (trasporti)", "categoria": "Trasporti",
     "free": ["OpenSky (aerei)", "Screening nave sanzioni"], "paid": ["Equasis/MarineTraffic (spec)"],
     "free_dati": "posizione/tracce aerei, screening nave su liste", "paid_dati": "+ storico rotte dettagliato, dati di sicurezza nave",
     "gap": "storico rotte e dettagli tecnici nave",
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
        "modello": MODELLO_BILLING,
        "stats": {"capacita": len(CAPACITA), "fonti_totali": len(fonti),
                  "fonti_gratuite": free_n, "famiglie_openapi": len(openapi),
                  "openapi_connesso": connesso,
                  "capacita_con_free": len([c for c in CAPACITA if c["free"]])},
    }

# ── Listino operativo (X free / Y paid) + pertinenza al caso + override Z ──
_CAP_PREZZO_Y = {
    "Sanzioni / PEP / liste / adverse media": 6.0,
    "Anagrafica azienda (bilanci, struttura)": 7.5,
    "Soci e quote / Titolari effettivi (UBO) IT": 4.5,
    "Nome \u2192 P.IVA (risoluzione)": 1.5,
    "Negativit\u00e0 / protesti / pregiudizievoli": 6.0,
    "Patrimoniale persona / beni": 9.0,
    "Catasto / immobili / ipoteche": 5.0,
    "Veicoli per targa": 3.0,
    "Indirizzi / geocoding": 1.0,
    "Telefono (validit\u00e0, operatore, paese)": 1.8,
    "Email (validit\u00e0, footprint)": 1.8,
    "IBAN (validit\u00e0, banca, titolare)": 2.4,
    "IP / URL / dominio / cyber": 3.0,
    "Wallet crypto / tracing": 4.0,
    "Contenzioso / giudiziario": 2.0,
    "Archivio web / storico siti": 1.0,
    "Username / social / breach password": 2.0,
    "Navi / aerei (trasporti)": 3.0,
}

_CASETYPE_CAT = {
    "Fraud": {"Crypto", "Antifrode", "Compliance", "Cyber", "Aziende", "Rischio"},
    "Cyber": {"Cyber", "Crypto", "Contatti", "Social", "Media"},
    "Asset Recovery": {"Crypto", "Patrimonio", "Rischio", "Aziende", "Antifrode"},
    "Due Diligence": {"Aziende", "Compliance", "Rischio", "Patrimonio"},
    "Corporate": {"Aziende", "Compliance", "Rischio"},
    "Family": {"Contatti", "Patrimonio", "Social", "Rischio"},
}
_ENTITY_CAT = {"Wallet": "Crypto", "Company": "Aziende", "Person": "Rischio",
               "Email": "Contatti", "Domain": "Cyber", "IP": "Cyber", "Phone": "Contatti"}


def _relevant_caps(case):
    if not case:
        return set()
    ct = frappe.db.get_value("Investigation Case", case, "case_type")
    rel = set(_CASETYPE_CAT.get(ct, set()))
    try:
        ents = frappe.db.sql("""select ie.entity_type from `tabCase Entity` ce
            join `tabInvestigation Entity` ie on ie.name = ce.entity where ce.parent = %s""",
            (case,), as_dict=True)
        for e in ents:
            if e.entity_type in _ENTITY_CAT:
                rel.add(_ENTITY_CAT[e.entity_type])
    except Exception:
        pass
    return rel


@frappe.whitelist()
def catalogo_due(case=None):
    """Listino unico (base = listino ERP) + prezzo rivendita cliente calcolato
    da una regola per-caso (moltiplicatore / percentuale / prezzo fisso) con
    override per singola voce. Voci pertinenti al caso in cima."""
    overrides = {}
    if case:
        raw = frappe.db.get_value("Investigation Case", case, "service_price_overrides")
        overrides = frappe.parse_json(raw) if raw else {}
    rule = overrides.get("_rule") or {"mode": "multiplier", "value": 1}
    rel = _relevant_caps(case)

    def _resale(base, slug):
        ovr = overrides.get(slug)
        if ovr is not None:
            return round(float(ovr), 2), True
        m = rule.get("mode", "multiplier")
        val = float(rule.get("value", 1) or 0)
        if m == "percent":
            return round(base * (1 + val / 100.0), 2), False
        if m == "fixed":
            return round(val, 2), False
        return round(base * val, 2), False

    voci = []
    for c in CAPACITA:
        name = c["capacita"]
        slug = frappe.scrub(name)
        base = round(_CAP_PREZZO_Y.get(name, 5.0), 2)
        riv, ovr = _resale(base, slug)
        voci.append({"id": slug, "capacita": name, "categoria": c.get("categoria"),
                     "tipo": "free" if c.get("consiglio") in ("free", "misto") else "paid",
                     "base": base, "rivendita": riv, "override": ovr,
                     "relevant": c.get("categoria") in rel,
                     "sorgenti": ", ".join((c.get("free") or []) + (c.get("paid") or []))})
    voci.sort(key=lambda x: (not x["relevant"], x["capacita"]))
    label = frappe.utils.now_datetime().strftime("%m/%Y")
    return {"voci": voci, "rule": rule, "listino_label": label,
            "stats": {"totali": len(voci), "pertinenti": len([1 for x in voci if x["relevant"]])}}


@frappe.whitelist()
def set_resale_rule(case, mode, value):
    """Regola di rivendita per-caso: moltiplicatore | percent | fixed."""
    if not case or not frappe.has_permission("Investigation Case", "write", doc=case):
        frappe.throw("Permessi insufficienti.")
    raw = frappe.db.get_value("Investigation Case", case, "service_price_overrides")
    data = frappe.parse_json(raw) if raw else {}
    data["_rule"] = {"mode": mode, "value": round(float(value or 0), 2)}
    frappe.db.set_value("Investigation Case", case, "service_price_overrides", frappe.as_json(data))
    return {"ok": True, "rule": data["_rule"]}


@frappe.whitelist()
def set_service_price(case, service_id, prezzo=None):
    """Override prezzo Z per (caso, servizio). Vuoto = ripristina listino base."""
    if not case or not frappe.has_permission("Investigation Case", "write", doc=case):
        frappe.throw("Permessi insufficienti.")
    raw = frappe.db.get_value("Investigation Case", case, "service_price_overrides")
    data = frappe.parse_json(raw) if raw else {}
    if prezzo in (None, "", "null"):
        data.pop(service_id, None)
    else:
        data[service_id] = round(float(prezzo), 2)
    frappe.db.set_value("Investigation Case", case, "service_price_overrides", frappe.as_json(data))
    return {"ok": True, "service_id": service_id, "prezzo": data.get(service_id)}


_TOOL_CAP = {
    "negativita": "Negatività / protesti / pregiudizievoli",
    "patrimoniale": "Patrimoniale persona / beni",
    "soci": "Soci e quote / Titolari effettivi (UBO) IT",
    "visura": "Anagrafica azienda (bilanci, struttura)",
    "catasto": "Catasto / immobili / ipoteche",
    "veicolo": "Veicoli per targa",
}


def tool_price(case, tool_key):
    """Prezzo di rivendita cliente per uno strumento, dal listino del caso."""
    name = _TOOL_CAP.get(tool_key)
    if not name:
        return 0.0
    slug = frappe.scrub(name)
    for v in catalogo_due(case).get("voci", []):
        if v["id"] == slug:
            return float(v["rivendita"])
    return 0.0
