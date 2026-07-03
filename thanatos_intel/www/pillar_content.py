"""Contenuti strutturati per le 9 pillar SEO servizi Thanatos, IT + EN.
Servito da www/servizi/<slug>/ e www/en/services/<slug>/ tramite lo stesso template.
"""

PILLARS = {
    "compliance-kyc": {
        "it": {
            "cat": "Compliance",
            "h1": "Compliance KYC/AML: verifiche sanzioni, PEP e adverse media",
            "sub": "Screening reputazionale professionale per aziende e persone: liste sanzioni EU/OFAC/UN, PEP internazionali, notizie negative.",
            "when": [
                "Onboarding cliente ad alto rischio (Legge 231/2007 antiriciclaggio)",
                "Selezione fornitore/partner con esposizione internazionale",
                "Investimento o M&A: due diligence reputazionale di soggetti e beneficiari effettivi",
                "Verifica preventiva pre-mandato professionale (avvocati, commercialisti, notai)",
            ],
            "deliverables": [
                "Report PDF con fonti certificate e digest SHA-256 (art. 234-bis c.p.p.)",
                "Match strutturati OpenSanctions + OFAC + UN + EU + Interpol",
                "Classificazione PEP con ruolo, giurisdizione, storico",
                "Adverse media indicizzata con evidenze web archived",
                "Valutazione rischio ponderata (verde/giallo/arancio/rosso)",
            ],
            "faq": [
                ("Che differenza c'è tra KYC e Adverse Media?",
                 "Il KYC verifica identità e conformità normativa (sanzioni/PEP), l'Adverse Media identifica menzioni negative pubbliche del soggetto (notizie di reato, contenziosi, scandali). Nel nostro report li integriamo entrambi."),
                ("Il report ha valore legale?",
                 "Il fascicolo è certificato con hash SHA-256 dei documenti sorgente e catena di custodia OSINT, utilizzabile come prova ex art. 234-bis c.p.p. e conforme al GDPR."),
                ("Quanto tempo richiede una verifica?",
                 "Il segnale semaforico è immediato (30 secondi via /verifica-rischio). Il report completo con fonti tra 4 e 24 ore lavorative."),
            ],
            "cta": "Richiedi una verifica KYC",
        },
        "en": {
            "cat": "Compliance",
            "h1": "KYC/AML Compliance: sanctions, PEP and adverse media checks",
            "sub": "Professional reputational screening for companies and individuals: EU/OFAC/UN sanctions lists, international PEPs, adverse media.",
            "when": [
                "High-risk client onboarding (EU 5AMLD)",
                "Supplier or partner selection with international exposure",
                "Investment or M&A: reputational due diligence of parties and UBOs",
                "Pre-mandate check for legal, accounting, notarial firms",
            ],
            "deliverables": [
                "PDF report with certified sources and SHA-256 digest",
                "Structured matches: OpenSanctions + OFAC + UN + EU + Interpol",
                "PEP classification with role, jurisdiction, history",
                "Indexed adverse media with archived web evidence",
                "Weighted risk assessment (green/yellow/orange/red)",
            ],
            "faq": [
                ("What's the difference between KYC and Adverse Media?",
                 "KYC verifies identity and regulatory compliance (sanctions/PEP), Adverse Media identifies negative public mentions (criminal news, disputes, scandals). Our report integrates both."),
                ("Is the report legally admissible?",
                 "The dossier is SHA-256 certified with OSINT chain of custody, usable as evidence and GDPR-compliant."),
                ("How long does a check take?",
                 "The traffic-light signal is instant (30 seconds via /en/verify-risk). Full report with sources within 4-24 business hours."),
            ],
            "cta": "Request a KYC check",
        },
    },
    "verifica-aziende": {
        "it": {
            "cat": "Aziende",
            "h1": "Verifica aziende: visure camerali, soci, UBO e strutture societarie",
            "sub": "Anagrafica completa di aziende italiane e internazionali: bilanci, quote sociali, titolari effettivi, gruppi societari.",
            "when": [
                "Nuovo cliente/fornitore: verifica esistenza, solvibilità, azionariato",
                "Contenzioso: identificazione beneficiario effettivo (UBO) e struttura di controllo",
                "M&A: mappatura gruppo societario prima dell'operazione",
                "Investigazioni patrimoniali: quote in altre società intestate al soggetto",
            ],
            "deliverables": [
                "Visura camerale ordinaria/storica (PDF ufficiale Registro Imprese)",
                "Elenco soci con % quota + codici fiscali",
                "Titolari effettivi (UBO) persona fisica con nascita e residenza",
                "Amministratori e sindaci con storico incarichi",
                "Bilancio ottico (last 3-5 anni) con KPI patrimoniali",
                "Grafo società collegate (director comune, sede condivisa)",
            ],
            "faq": [
                ("Quali giurisdizioni coprite?",
                 "Italia (Registro Imprese, catasto), UK (Companies House), UE (VIES, registri nazionali via API), oltre 190 paesi via OpenCorporates per anagrafica base."),
                ("Il UBO è sempre identificabile?",
                 "In società italiane sopra il 25% di quote è nominato UBO; per strutture opache offshore usiamo screening ICIJ Offshore Leaks + Panama/Paradise/Pandora Papers."),
                ("Fornite anche analisi bilanci?",
                 "Sì: KPI di redditività (ROE/ROI), solvibilità (DSCR/DSO), efficienza operativa, con confronto settore."),
            ],
            "cta": "Verifica un'azienda",
        },
        "en": {
            "cat": "Companies",
            "h1": "Company checks: registry, shareholders, UBO and group structures",
            "sub": "Complete records of Italian and international companies: balance sheets, shareholding, ultimate beneficial owners, group structures.",
            "when": [
                "New client/supplier: existence, solvency, ownership check",
                "Litigation: UBO identification and control structure",
                "M&A: group mapping before the deal",
                "Asset investigations: shareholdings in other entities",
            ],
            "deliverables": [
                "Ordinary/historical registry excerpt (official PDF)",
                "Shareholders with % + tax codes",
                "UBOs (natural persons) with birth date and residence",
                "Directors and auditors with appointment history",
                "Optical balance sheet (last 3-5 years) with financial KPIs",
                "Related companies graph (common directors, shared registered office)",
            ],
            "faq": [
                ("Which jurisdictions do you cover?",
                 "Italy (Companies Register, land registry), UK (Companies House), EU (VIES + national registers via API), plus 190+ countries via OpenCorporates for basic records."),
                ("Is the UBO always identifiable?",
                 "In Italian companies above 25% ownership a UBO must be declared; for opaque offshore structures we use ICIJ Offshore Leaks + Panama/Paradise/Pandora Papers."),
                ("Do you provide financial statement analysis?",
                 "Yes: profitability KPIs (ROE/ROI), solvency (DSCR/DSO), operational efficiency, benchmarked against sector."),
            ],
            "cta": "Check a company",
        },
    },
    "due-diligence-rischio": {
        "it": {
            "cat": "Rischio",
            "h1": "Due diligence rischio: negatività, protesti, procedimenti giudiziari",
            "sub": "Screening esposizione al rischio di persone fisiche e giuridiche: protesti, pregiudizievoli, contenziosi, procedure concorsuali.",
            "when": [
                "Concessione credito o dilazione pagamento",
                "Verifica cliente ad alto valore (contratti > €50k)",
                "Recupero crediti: valutazione preventiva della solvibilità",
                "Insurance/underwriting: profilazione rischio controparte",
            ],
            "deliverables": [
                "Protesti e pregiudizievoli (CRIF/Cerved)",
                "Procedure concorsuali (fallimenti, concordati, liquidazioni)",
                "Contenziosi in corso e passati (fonti open + Portale Servizi Telematici)",
                "Beni intestati (immobili, veicoli, quote societarie)",
                "Score rischio composito (verde/giallo/arancio/rosso)",
            ],
            "faq": [
                ("La negatività è pubblica?",
                 "In parte sì (Bollettini Protesti online), il resto è tramite banche dati specializzate CRIF/Cerved a cui accediamo su tuo mandato."),
                ("Quanto è aggiornato il dato?",
                 "Real-time dal registro protesti (24h max di ritardo dalla protestazione); i procedimenti giudiziari sono aggiornati settimanalmente dalle fonti aperte."),
            ],
            "cta": "Valuta il rischio di una controparte",
        },
        "en": {
            "cat": "Risk",
            "h1": "Risk due diligence: adverse credit, protests, judicial proceedings",
            "sub": "Risk screening of individuals and companies: protests, adverse events, litigation, insolvency proceedings.",
            "when": [
                "Credit granting or payment deferral",
                "High-value client verification (contracts > €50k)",
                "Debt recovery: preliminary solvency assessment",
                "Insurance underwriting: counterparty risk profiling",
            ],
            "deliverables": [
                "Protests and adverse events (CRIF/Cerved)",
                "Insolvency proceedings (bankruptcy, restructuring, liquidation)",
                "Ongoing and past litigation (open sources + Italian judicial portal)",
                "Registered assets (real estate, vehicles, shareholdings)",
                "Composite risk score (green/yellow/orange/red)",
            ],
            "faq": [
                ("Are adverse events public?",
                 "Partially yes (online Protests Bulletin), the rest via specialized databases (CRIF/Cerved) we access under your mandate."),
                ("How up-to-date is the data?",
                 "Real-time from the protests registry (24h max lag); judicial proceedings updated weekly from open sources."),
            ],
            "cta": "Assess a counterparty's risk",
        },
    },
    "indagini-patrimoniali": {
        "it": {
            "cat": "Patrimonio",
            "h1": "Indagini patrimoniali: catasto, veicoli, immobili e beni",
            "sub": "Ricognizione del patrimonio di persone fisiche e giuridiche: immobili, veicoli, imbarcazioni, partecipazioni societarie.",
            "when": [
                "Divorzio: individuazione beni del coniuge",
                "Recupero crediti: aggredibilità patrimoniale del debitore",
                "Successione: mappatura eredità e riparto",
                "Sequestro/pignoramento preventivo: identificazione bersagli",
            ],
            "deliverables": [
                "Visura catastale (immobili intestati per soggetto)",
                "Ispezione ipotecaria nazionale (pesi, gravami, pignoramenti)",
                "Elenco veicoli intestati (PRA/Motorizzazione)",
                "Imbarcazioni RID/Aeromobili civili",
                "Quote societarie e partecipazioni",
                "Timeline acquisizioni/cessioni ultimi 5 anni",
            ],
            "faq": [
                ("Che differenza c'è tra visura catastale e ispezione ipotecaria?",
                 "La visura catastale identifica gli immobili intestati; l'ispezione ipotecaria rivela pesi, ipoteche, pignoramenti sui singoli immobili."),
                ("È legale investigare il patrimonio di terzi?",
                 "Sì, se sussiste interesse legittimo (contenzioso in corso, credito da recuperare, mandato professionale). Verifichiamo la base giuridica in fase di intake."),
            ],
            "cta": "Avvia indagine patrimoniale",
        },
        "en": {
            "cat": "Assets",
            "h1": "Asset investigations: real estate, vehicles, holdings",
            "sub": "Asset recognition of individuals and companies: real estate, vehicles, vessels, shareholdings.",
            "when": [
                "Divorce: spouse's asset identification",
                "Debt recovery: debtor's asset attackability",
                "Inheritance: estate mapping and allocation",
                "Preventive seizure: target identification",
            ],
            "deliverables": [
                "Land registry search (real estate by owner)",
                "National mortgage inspection (encumbrances, foreclosures)",
                "Vehicle registry list",
                "Vessel/aircraft ownership",
                "Corporate shareholdings",
                "5-year acquisition/disposal timeline",
            ],
            "faq": [
                ("What's the difference between land registry and mortgage inspection?",
                 "Land registry identifies owned real estate; mortgage inspection reveals encumbrances on specific properties."),
                ("Is it legal to investigate a third party's assets?",
                 "Yes, if legitimate interest exists (ongoing litigation, debt to recover, professional mandate). We verify the legal basis at intake."),
            ],
            "cta": "Start asset investigation",
        },
    },
    "antifrode-pagamenti": {
        "it": {
            "cat": "Antifrode",
            "h1": "Antifrode pagamenti: verifica IBAN, email, telefono, identità",
            "sub": "Prevenzione frodi nei pagamenti B2B/B2C: verifica intestatario IBAN, deliverability email, HLR telefono, identità.",
            "when": [
                "Cambio IBAN fornitore: verifica intestatario prima del bonifico",
                "Onboarding cliente e-commerce: identity verification",
                "Recupero crediti: verifica contattabilità del debitore",
                "Antiriciclaggio: matching intestatario/IBAN dichiarato",
            ],
            "deliverables": [
                "Verifica intestatario IBAN (banca + BIC + intestatario)",
                "Email: sintassi + MX + reputazione + breach history (HIBP)",
                "Telefono: HLR live + operatore + portabilità + tipo linea",
                "Identity verification (IDV) con selfie liveness",
                "Score antifrode (verde/giallo/arancio/rosso)",
            ],
            "faq": [
                ("L'intestatario IBAN è verificabile?",
                 "Sì, tramite openapi trust (fonte primaria banca emittente). Alternativa gratuita: checksum + banca via openiban.com senza intestatario."),
                ("Quanto costa una verifica antifrode?",
                 "Da €3 per verifica email base a €12 per identity verification con selfie. Prezzi listino su /portal/servizi."),
            ],
            "cta": "Verifica un pagamento",
        },
        "en": {
            "cat": "Anti-fraud",
            "h1": "Payment anti-fraud: IBAN, email, phone, identity verification",
            "sub": "Fraud prevention in B2B/B2C payments: IBAN holder verification, email deliverability, phone HLR, identity.",
            "when": [
                "Supplier IBAN change: verify holder before transfer",
                "E-commerce customer onboarding: identity verification",
                "Debt recovery: debtor contactability",
                "AML: holder/declared IBAN matching",
            ],
            "deliverables": [
                "IBAN holder verification (bank + BIC + name)",
                "Email: syntax + MX + reputation + HIBP breach history",
                "Phone: live HLR + carrier + portability + line type",
                "Identity verification with selfie liveness",
                "Anti-fraud score (green/yellow/orange/red)",
            ],
            "faq": [
                ("Is IBAN holder verifiable?",
                 "Yes, via openapi trust (issuing bank as primary source). Free alternative: checksum + bank via openiban.com without holder."),
                ("How much does an anti-fraud check cost?",
                 "From €3 for basic email verification to €12 for identity verification with selfie."),
            ],
            "cta": "Verify a payment",
        },
    },
    "osint-crypto": {
        "it": {
            "cat": "Crypto",
            "h1": "OSINT crypto: attribuzione wallet, tracciamento fondi, cluster",
            "sub": "Investigazione blockchain: attribuzione wallet BTC/ETH/altre chain, tracciamento fondi, mappatura cluster, blacklist scam.",
            "when": [
                "Vittima truffa crypto: tracciamento fondi verso exchange target di sequestro",
                "Antiriciclaggio crypto: due diligence controparti Web3",
                "Recovery: identificazione mixer/tornado usati per offuscare",
                "Contenzioso crypto: perizia CTU per procedimenti civili/penali",
            ],
            "deliverables": [
                "Attribuzione wallet Arkham/Chainalysis (exchange, fondi, entità nota)",
                "Grafo transazioni fino a 5 hop di distanza",
                "Score rischio (interazione con mixer, sanctioned addresses)",
                "Report vittima truffa con blacklist ricoveri comuni",
                "Perizia CTU firmata digitalmente ex mmos_sign",
            ],
            "faq": [
                ("Recuperate crypto rubate?",
                 "No: tracciamo i fondi e forniamo la perizia per il sequestro giudiziario. Il recupero materiale avviene tramite exchange/autorità competenti."),
                ("Quali chain coprite?",
                 "BTC, ETH, Polygon, BSC, Arbitrum, Optimism, Solana, TRON (USDT), più L2 su richiesta."),
            ],
            "cta": "Traccia un wallet",
        },
        "en": {
            "cat": "Crypto",
            "h1": "Crypto OSINT: wallet attribution, fund tracing, clustering",
            "sub": "Blockchain investigation: wallet attribution across BTC/ETH/other chains, fund tracing, cluster mapping, scam blacklists.",
            "when": [
                "Crypto scam victim: fund tracing to seizable exchange targets",
                "Crypto AML: Web3 counterparty due diligence",
                "Recovery: mixer/tornado identification",
                "Crypto litigation: CTU forensics for civil/criminal proceedings",
            ],
            "deliverables": [
                "Wallet attribution via Arkham/Chainalysis (exchange, funds, known entity)",
                "Transaction graph up to 5 hops",
                "Risk score (mixer/sanctioned address interaction)",
                "Victim report with common recovery scam blacklist",
                "Court-ready forensic report signed via mmos_sign",
            ],
            "faq": [
                ("Do you recover stolen crypto?",
                 "No: we trace funds and provide the forensic report for judicial seizure. Material recovery is via exchanges/authorities."),
                ("Which chains do you cover?",
                 "BTC, ETH, Polygon, BSC, Arbitrum, Optimism, Solana, TRON (USDT), plus L2s on request."),
            ],
            "cta": "Trace a wallet",
        },
    },
    "cyber-domain-intelligence": {
        "it": {
            "cat": "Cyber",
            "h1": "Cyber & domain intelligence: verifica siti, IP, breach, phishing",
            "sub": "Threat intelligence su domini, IP, hash: reputazione, data breach, phishing, dark web mentions.",
            "when": [
                "Verifica fornitore prima di condividere dati sensibili",
                "Domain due diligence pre-M&A (data breach del target?)",
                "Vittima phishing: identificazione impersonatore",
                "Corporate: monitoraggio del proprio brand nel dark web",
            ],
            "deliverables": [
                "Reputazione IP/dominio (GreyNoise, VirusTotal, AbuseIPDB)",
                "Data breach history (Have I Been Pwned Enterprise)",
                "WHOIS + storico owner + Wayback snapshot",
                "Threat intel feed (OTX, Pulsedive, URLScan)",
                "Dark web monitoring (menzioni del target)",
            ],
            "faq": [
                ("Trovate dati leaked del mio dominio?",
                 "Sì, tramite HIBP Enterprise (accesso completo). Se ci sono breach vi diamo la data + numero record + fonte."),
                ("È legale il dark web monitoring?",
                 "Il monitoraggio passivo (lettura mercati/forum accessibili via Tor) è legale in Italia. Non partecipiamo a transazioni illegali."),
            ],
            "cta": "Verifica un dominio o IP",
        },
        "en": {
            "cat": "Cyber",
            "h1": "Cyber & domain intelligence: sites, IPs, breaches, phishing",
            "sub": "Threat intelligence on domains, IPs, hashes: reputation, data breach, phishing, dark web mentions.",
            "when": [
                "Vendor verification before sharing sensitive data",
                "Domain due diligence pre-M&A (target breached?)",
                "Phishing victim: impersonator identification",
                "Corporate: dark web brand monitoring",
            ],
            "deliverables": [
                "IP/domain reputation (GreyNoise, VirusTotal, AbuseIPDB)",
                "Data breach history (HIBP Enterprise)",
                "WHOIS + historical owner + Wayback snapshots",
                "Threat intel feeds (OTX, Pulsedive, URLScan)",
                "Dark web monitoring (target mentions)",
            ],
            "faq": [
                ("Do you find leaked data of my domain?",
                 "Yes, via HIBP Enterprise. If breaches exist we provide date + record count + source."),
                ("Is dark web monitoring legal?",
                 "Passive monitoring (reading Tor-accessible markets/forums) is legal in Italy. We do not participate in illegal transactions."),
            ],
            "cta": "Check a domain or IP",
        },
    },
    "rintraccio-persone": {
        "it": {
            "cat": "Contatti",
            "h1": "Rintraccio persone: indirizzo, telefono, email verificati",
            "sub": "Reperimento dati di contatto di persone in Italia e all'estero: indirizzo di residenza, telefono, email, footprint digitale.",
            "when": [
                "Notifica atti giudiziari: destinatario irreperibile",
                "Recupero crediti: contattare debitore latitante",
                "Familiare disperso: rintraccio parenti biologici",
                "Vecchi amici/adoption: reunification",
            ],
            "deliverables": [
                "Indirizzo di residenza attuale (fonti anagrafiche)",
                "Numeri di telefono attivi (HLR + operatore)",
                "Email verificate + presenza social/professionale",
                "Footprint digitale (LinkedIn, Facebook, media locali)",
                "Report finale con evidenze data-stamped",
            ],
            "faq": [
                ("Come rintracciate le persone?",
                 "Fonti anagrafiche pubbliche (Wikidata, IMDb), social pubblici (LinkedIn), rintraccio openapi (anagrafica italiana), telefono HLR."),
                ("Rispetta la privacy?",
                 "Sì: interesse legittimo verificato + GDPR compliant. Il soggetto ha diritto di conoscere l'origine del rintraccio dopo il primo contatto."),
            ],
            "cta": "Rintraccia una persona",
        },
        "en": {
            "cat": "Contacts",
            "h1": "People search: verified address, phone, email",
            "sub": "Contact data recovery in Italy and abroad: residence, phone, email, digital footprint.",
            "when": [
                "Judicial service: unreachable recipient",
                "Debt recovery: contact an evasive debtor",
                "Missing relatives: biological family reunification",
                "Old friends/adoption: reunification",
            ],
            "deliverables": [
                "Current residence address (public sources)",
                "Active phone numbers (HLR + carrier)",
                "Verified emails + social/professional presence",
                "Digital footprint (LinkedIn, Facebook, local media)",
                "Final report with time-stamped evidence",
            ],
            "faq": [
                ("How do you find people?",
                 "Public data sources (Wikidata, IMDb), public social (LinkedIn), openapi people search (Italian registries), phone HLR."),
                ("Is it GDPR compliant?",
                 "Yes: legitimate interest verified + GDPR compliant. Subject has right to know the source after first contact."),
            ],
            "cta": "Find a person",
        },
    },
    "osint-giudiziario": {
        "it": {
            "cat": "Giudiziario",
            "h1": "OSINT giudiziario: procedimenti, condanne, contenziosi",
            "sub": "Ricerca procedimenti giudiziari civili e penali di persone e aziende: contenziosi in corso, condanne, provvedimenti pubblici.",
            "when": [
                "Selezione candidato ad alto profilo (executive, C-suite)",
                "Antiriciclaggio: verifica condanne per reati presupposto",
                "M&A: mappatura contenziosi del target",
                "Difesa reputazione: monitoraggio menzioni giudiziarie del proprio brand",
            ],
            "deliverables": [
                "Procedimenti civili (Portale Servizi Telematici)",
                "Condanne penali definitive (Casellario giudiziale + fonti aperte)",
                "Provvedimenti amministrativi (CONSOB, Banca d'Italia, AGCM)",
                "CourtListener (jurisprudenza USA per aziende internazionali)",
                "Report con timeline e classificazione per gravità",
            ],
            "faq": [
                ("Accedete al casellario giudiziale?",
                 "Non direttamente (accesso riservato al soggetto o autorità). Combiniamo fonti aperte (giurisprudenza pubblica, media, provvedimenti CONSOB/BankItaly)."),
                ("Coprite giurisdizioni internazionali?",
                 "Sì: USA (CourtListener), UK (registri pubblici), UE via portali giudiziari nazionali."),
            ],
            "cta": "Verifica procedimenti",
        },
        "en": {
            "cat": "Judicial",
            "h1": "Judicial OSINT: proceedings, convictions, litigation",
            "sub": "Judicial research on individuals and companies: ongoing litigation, convictions, public rulings.",
            "when": [
                "High-profile candidate selection (executive, C-suite)",
                "AML: predicate offense conviction check",
                "M&A: target litigation mapping",
                "Brand reputation: judicial mention monitoring",
            ],
            "deliverables": [
                "Civil proceedings (Italian judicial portal)",
                "Final criminal convictions (public records + open sources)",
                "Administrative rulings (CONSOB, Banca d'Italia, AGCM)",
                "CourtListener (US case law for international companies)",
                "Report with timeline and severity classification",
            ],
            "faq": [
                ("Do you access the criminal record?",
                 "Not directly (restricted access). We combine open sources (public case law, media, CONSOB/BankItaly rulings)."),
                ("Do you cover international jurisdictions?",
                 "Yes: US (CourtListener), UK (public registers), EU via national judicial portals."),
            ],
            "cta": "Check proceedings",
        },
    },
}


def get_pillar(slug, lang="it"):
    """Ritorna dati pillar per slug + lingua, con struttura piatta pronta per template."""
    entry = PILLARS.get(slug)
    if not entry:
        return None
    return entry.get(lang, entry.get("it"))


def all_pillars(lang="it"):
    return [{"slug": k, **v[lang if lang in v else "it"]} for k, v in PILLARS.items()]
