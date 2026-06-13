"""
Pillar pages SEO per categoria di servizio — /soluzioni e /soluzioni/<slug>.

Fonte prezzi/servizi: Service Catalog (mai hardcoded). Copy editoriale per il
ranking organico. CTA verso checkout/registrazione.
"""
import frappe

no_cache = 0
sitemap = 1

# slug → (categoria Service Catalog, titolo, meta description, eyebrow, intro[])
CATEGORIES = {
    "verifiche-rapide": {
        "cat": "Verifiche Rapide", "icon": "⚡",
        "title": "Verifiche rapide — controlli OSINT in poche ore",
        "meta": "Verifiche rapide su aziende, persone, IBAN, IP, domini e wallet: controlli OSINT documentati e con valore legale, consegnati in poche ore.",
        "eyebrow": "Verifiche Rapide",
        "h1": "Verifiche rapide, prove documentate",
        "intro": [
            "Quando devi decidere in fretta se fidarti di una controparte, una verifica rapida Thanatos ti dà in poche ore un quadro affidabile su azienda, persona, IBAN, IP, dominio o wallet, attingendo a registri pubblici, liste sanzioni internazionali e fonti OSINT.",
            "Ogni controllo è documentato con catena di custodia SHA-256 e fonti certificate: non un semplice screenshot, ma un esito spendibile in due diligence, recupero crediti e contenzioso.",
        ],
    },
    "antifrode": {
        "cat": "Antifrode", "icon": "🛡",
        "title": "Antifrode — investigazioni su truffe, scam e frodi",
        "meta": "Servizi antifrode Thanatos: indagini su truffe crypto, investment scam, phishing e frodi finanziarie, con tracciamento wallet e dossier probatorio.",
        "eyebrow": "Antifrode",
        "h1": "Antifrode e recupero",
        "intro": [
            "Le frodi oggi corrono su wallet crypto, IBAN esteri e siti clone. I servizi antifrode di Thanatos ricostruiscono il flusso del denaro, identificano gli intermediari e documentano la truffa in un dossier utilizzabile per denuncia, sequestro e recupero.",
            "Uniamo crypto-forensics multi-chain, screening sanzioni e OSINT: dall'indicatore di rischio iniziale alla prova certificata.",
        ],
    },
    "cyber-intelligence": {
        "cat": "Cyber Intelligence", "icon": "⚙",
        "title": "Cyber Intelligence — threat intel, IOC, infrastrutture",
        "meta": "Cyber Intelligence Thanatos: analisi di domini, IP, malware e IOC, threat intelligence e mappatura infrastrutture per indagini e sicurezza.",
        "eyebrow": "Cyber Intelligence",
        "h1": "Cyber intelligence operativa",
        "intro": [
            "Dietro un attacco, una frode online o un sito sospetto c'è un'infrastruttura. La cyber intelligence di Thanatos analizza domini, IP, certificati, malware e indicatori di compromissione per attribuire e documentare l'attività malevola.",
            "Correliamo fonti di threat intelligence, scansioni e storici DNS per trasformare segnali tecnici in evidenze comprensibili e azionabili.",
        ],
    },
    "corporate-intelligence": {
        "cat": "Corporate Intelligence", "icon": "🏛",
        "title": "Corporate Intelligence — due diligence e UBO",
        "meta": "Corporate Intelligence Thanatos: due diligence su aziende, titolari effettivi (UBO), assetti societari e reputazione per decisioni e compliance.",
        "eyebrow": "Corporate Intelligence",
        "h1": "Conosci con chi tratti",
        "intro": [
            "Prima di un investimento, una fornitura o una partnership, devi sapere chi c'è davvero dietro un'azienda. La corporate intelligence di Thanatos ricostruisce assetti societari, titolari effettivi, collegamenti e reputazione su scala internazionale.",
            "Incrociamo registri imprese, banche dati offshore, sanzioni e media per un profilo completo e verificato.",
        ],
    },
    "financial-intelligence": {
        "cat": "Financial Intelligence", "icon": "₿",
        "title": "Financial Intelligence — asset tracing e crypto",
        "meta": "Financial Intelligence Thanatos: asset tracing, analisi patrimoniale, tracciamento wallet crypto e flussi finanziari per recupero e contenzioso.",
        "eyebrow": "Financial Intelligence",
        "h1": "Segui il denaro",
        "intro": [
            "Individuare beni e flussi è il cuore del recupero crediti e dei sequestri. La financial intelligence di Thanatos rintraccia patrimoni, conti, immobili e wallet crypto, ricostruendo i percorsi del denaro fino alla destinazione finale.",
            "Tracciamento blockchain, analisi societaria e fonti pubbliche convergono in una mappa patrimoniale documentata.",
        ],
    },
    "analisi-documenti": {
        "cat": "Analisi Documenti", "icon": "📄",
        "title": "Analisi documenti — autenticità e forensics",
        "meta": "Analisi documentale forense Thanatos: verifica autenticità, metadati, manipolazioni e perizie su documenti, immagini e file.",
        "eyebrow": "Analisi Documenti",
        "h1": "Documenti che dicono la verità",
        "intro": [
            "Un documento falso o alterato può ribaltare una trattativa o un processo. L'analisi documentale di Thanatos verifica autenticità, metadati, coerenza e manipolazioni di documenti, immagini e file digitali.",
            "Forensics dei metadati, error level analysis e verifica delle fonti, con esito perizia.",
        ],
    },
    "sequestri-confische": {
        "cat": "Sequestri e Confische", "icon": "⚖",
        "title": "Sequestri e confische — supporto investigativo",
        "meta": "Supporto a sequestri e confische: individuazione e tracciamento beni, asset crypto e patrimoni, dossier per autorità e legali.",
        "eyebrow": "Sequestri e Confische",
        "h1": "Dal tracciamento al sequestro",
        "intro": [
            "Individuare un bene non basta: serve documentarlo in modo che regga al sequestro. Thanatos supporta legali e autorità nell'identificazione e nel congelamento di patrimoni, conti e asset crypto.",
            "Dossier patrimoniali con catena di custodia, pronti per l'istanza e il provvedimento.",
        ],
    },
    "investigazioni-complete": {
        "cat": "Investigazioni Complete", "icon": "🔍",
        "title": "Investigazioni complete — indagini su misura",
        "meta": "Investigazioni complete Thanatos: indagini multidisciplinari su misura per studi legali, aziende e privati, con report giudiziario.",
        "eyebrow": "Investigazioni Complete",
        "h1": "Indagini end-to-end",
        "intro": [
            "Alcuni casi richiedono più di una verifica: un'indagine completa, multidisciplinare, condotta da analisti. Thanatos gestisce mandati investigativi end-to-end, dall'intake al report giudiziario.",
            "OSINT, financial e corporate intelligence coordinati in un unico fascicolo certificato.",
        ],
    },
    "enterprise-api": {
        "cat": "Enterprise & API", "icon": "🔗",
        "title": "Enterprise & API — intelligence integrata",
        "meta": "Soluzioni Enterprise e API Thanatos: integrazione dell'intelligence nei tuoi sistemi, monitoraggio continuo e volumi dedicati.",
        "eyebrow": "Enterprise & API",
        "h1": "Intelligence nei tuoi processi",
        "intro": [
            "Per banche, EMI e gruppi, l'intelligence deve entrare nei processi. Le soluzioni Enterprise & API di Thanatos integrano verifiche, screening e monitoraggio continuo direttamente nei tuoi sistemi.",
            "Accesso programmatico, volumi dedicati e account manager.",
        ],
    },
    "abbonamenti-academy": {
        "cat": "Abbonamenti e Academy", "icon": "🎓",
        "title": "Abbonamenti e Academy — intelligence continuativa",
        "meta": "Abbonamenti Thanatos e Academy: intelligence continuativa a canone e formazione su OSINT, antifrode e due diligence.",
        "eyebrow": "Abbonamenti e Academy",
        "h1": "Cresci con Thanatos",
        "intro": [
            "Chi verifica con continuità lavora meglio con un abbonamento: servizi inclusi, priorità e condizioni dedicate. E con l'Academy formi il tuo team su OSINT, antifrode e due diligence.",
            "Intelligence e competenze, in un unico percorso.",
        ],
    },
}

ORDER = ["verifiche-rapide", "antifrode", "cyber-intelligence", "corporate-intelligence",
         "financial-intelligence", "analisi-documenti", "sequestri-confische",
         "investigazioni-complete", "enterprise-api", "abbonamenti-academy"]


def get_context(context):
    slug = (frappe.form_dict.get("slug") or "").strip("/")
    context.logged_in = frappe.session.user != "Guest"

    if not slug:
        context.is_hub = True
        context.cards = [{"slug": k, **CATEGORIES[k]} for k in ORDER if k in CATEGORIES]
        return context

    conf = CATEGORIES.get(slug)
    if not conf:
        frappe.local.flags.redirect_location = "/soluzioni"
        raise frappe.Redirect

    context.is_hub = False
    context.slug = slug
    context.conf = conf
    context.services = frappe.get_all(
        "Service Catalog",
        filters={"category": conf["cat"], "is_active": 1},
        fields=["service_code", "service_name", "price", "price_min", "currency",
                "delivery_hours", "requires_analyst", "description"],
        order_by="price_min asc, price asc",
    )
    # navigazione tra categorie
    context.others = [{"slug": k, "label": CATEGORIES[k]["eyebrow"]}
                      for k in ORDER if k != slug]
    context.related_news = frappe.get_all(
        "News Article", filters={"published": 1}, fields=["title", "slug"],
        order_by="published_at desc", limit=4,
    )
