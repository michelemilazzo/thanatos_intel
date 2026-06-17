import frappe

no_cache = 1

PROCEDURES = [
    {
        "key": "DDD",
        "label": "Due Diligence Diplomatica (DDD)",
        "description": "Verifica di eligibilità per passaporti diplomatici. Processo strutturato con KYC/KYB, mandato, analisi passaporto e screening sanzioni.",
        "new_url": "/app/diplomatic-eligibility-case/new",
        "steps": [
            {"label": "Verifica identità (KYB/KYC)", "actor": "Operatore", "description": "Verifica documenti del richiedente: persone fisiche → KYC, aziende → KYB."},
            {"label": "Mandato d'incarico", "actor": "Operatore", "description": "Genera il PDF del mandato e invialo al cliente tramite MMOS Sign."},
            {"label": "Firma mandato", "actor": "Cliente", "description": "Il cliente firma elettronicamente il mandato d'incarico."},
            {"label": "Preventivo DDD", "actor": "Operatore", "description": "Emetti la proforma con l'importo del servizio DDD."},
            {"label": "Pagamento", "actor": "Cliente", "description": "Il cliente salda la proforma tramite portale."},
            {"label": "Analisi passaporto", "actor": "Operatore", "description": "Avvia l'analisi del documento di viaggio del richiedente."},
            {"label": "Verifica sanzioni", "actor": "Operatore", "description": "Esegui lo screening sanzioni internazionali sul soggetto."},
            {"label": "Report finale", "actor": "Operatore", "description": "Genera il report di eligibilità e caricalo nel caso."},
            {"label": "Pratica chiusa", "actor": "Operatore", "description": "Archivia il caso e i documenti."},
        ],
    },
    {
        "key": "Investigation",
        "label": "Indagine Investigativa",
        "description": "Indagini su persone, aziende o eventi. Include raccolta di evidenze con catena di custodia SHA-256 e report finale.",
        "new_url": "/app/investigation-case/new",
        "steps": [
            {"label": "Mandato d'incarico", "actor": "Operatore", "description": "Genera e invia il mandato d'incarico al cliente."},
            {"label": "Firma mandato", "actor": "Cliente", "description": "Il cliente firma il mandato."},
            {"label": "Preventivo", "actor": "Operatore", "description": "Emetti il preventivo per il servizio."},
            {"label": "Pagamento", "actor": "Cliente", "description": "Il cliente effettua il pagamento."},
            {"label": "Raccolta evidenze", "actor": "Operatore", "description": "Carica le evidenze raccolte con hash SHA-256 e catena di custodia."},
            {"label": "Report finale", "actor": "Operatore", "description": "Genera e consegna il report investigativo al cliente."},
            {"label": "Pratica chiusa", "actor": "Operatore", "description": "Chiudi il caso e archivia i documenti."},
        ],
    },
    {
        "key": "OSINT",
        "label": "OSINT / Intelligence Open Source",
        "description": "Ricerca informazioni da fonti aperte su persone, aziende, domini, indirizzi email e asset digitali.",
        "new_url": "/app/investigation-case/new?case_type=OSINT",
        "steps": [
            {"label": "Mandato d'incarico", "actor": "Operatore", "description": "Genera il mandato per il servizio OSINT."},
            {"label": "OSINT / Lookup", "actor": "Operatore", "description": "Avvia la ricerca OSINT: HIBP, RDAP, sanzioni, reti sociali, domini."},
            {"label": "Report", "actor": "Operatore", "description": "Genera il report con i risultati dell'analisi."},
            {"label": "Chiuso", "actor": "Operatore", "description": "Chiudi il caso."},
        ],
    },
    {
        "key": "Antifrode",
        "label": "Antifrode",
        "description": "Analisi di frodi finanziarie, transazioni sospette, verifica identità e screening blacklist.",
        "new_url": "/app/investigation-case/new?case_type=Antifrode",
        "steps": [
            {"label": "Mandato d'incarico", "actor": "Operatore", "description": "Genera il mandato per il servizio antifrode."},
            {"label": "Analisi antifrode", "actor": "Operatore", "description": "Avvia l'analisi delle transazioni o dei soggetti sospetti."},
            {"label": "Verifica blacklist", "actor": "Operatore", "description": "Controlla il soggetto nelle blacklist interne ed esterne."},
            {"label": "Report", "actor": "Operatore", "description": "Genera il report con le conclusioni dell'analisi."},
            {"label": "Chiuso", "actor": "Operatore", "description": "Chiudi il caso."},
        ],
    },
    {
        "key": "Corporate",
        "label": "Corporate Intelligence",
        "description": "Due diligence aziendale, analisi di controparte, verifica UBO e valutazione del rischio per M&A o partnership.",
        "new_url": "/app/investigation-case/new?case_type=Corporate",
        "steps": [
            {"label": "Mandato d'incarico", "actor": "Operatore", "description": "Genera e invia il mandato d'incarico."},
            {"label": "Firma mandato", "actor": "Cliente", "description": "Il cliente firma il mandato."},
            {"label": "Preventivo", "actor": "Operatore", "description": "Emetti il preventivo per il servizio."},
            {"label": "Pagamento", "actor": "Cliente", "description": "Il cliente effettua il pagamento."},
            {"label": "Raccolta evidenze", "actor": "Operatore", "description": "Analisi documentale, verifica UBO, screening sanzioni."},
            {"label": "Report finale", "actor": "Operatore", "description": "Genera e consegna il report di intelligence aziendale."},
            {"label": "Pratica chiusa", "actor": "Operatore", "description": "Chiudi il caso e archivia i documenti."},
        ],
    },
]


def get_context(context):
    user = frappe.session.user
    if user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/guide"
        raise frappe.Redirect

    roles = set(frappe.get_roles(user))
    is_operator = "Investigator" in roles or "Investigation Manager" in roles or "System Manager" in roles

    context.procedures = PROCEDURES
    context.is_operator = is_operator
    context.title = "Guida Procedurale — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
