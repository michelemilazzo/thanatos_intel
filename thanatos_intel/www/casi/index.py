import frappe

no_cache = 0
sitemap = 1

CASES = [
    {
        "tag": "Antifrode · Crypto",
        "title": "Investment scam in USDT: dal wallet al congelamento",
        "problem": "Un investitore privato versa l'equivalente di €180.000 in USDT a una "
                   "piattaforma di trading rivelatasi fraudolenta. I fondi spariscono in poche ore.",
        "approach": "Tracciamento multi-chain del wallet ricevente, ricostruzione del flusso "
                    "attraverso i passaggi intermedi e identificazione del punto di cash-out su "
                    "un exchange con obblighi KYC. Screening sanzioni e dossier probatorio con "
                    "catena di custodia SHA-256.",
        "outcome": "Dossier consegnato ai legali e all'exchange: congelamento dei fondi residui "
                   "e base documentale per l'istanza di recupero.",
    },
    {
        "tag": "Corporate Intelligence · Compliance",
        "title": "Onboarding bloccato da un EMI: remediation in 72 ore",
        "problem": "Un istituto di moneta elettronica sospende l'onboarding di una società per "
                   "un alert su un presunto titolare effettivo collegato a liste di rischio.",
        "approach": "Ricostruzione completa dell'assetto societario e della catena UBO su più "
                    "giurisdizioni, verifica del match contro le liste reali e analisi reputazionale. "
                    "Distinzione documentata tra falso positivo e rischio effettivo.",
        "outcome": "Relazione di remediation che chiarisce l'assetto e neutralizza il falso "
                   "positivo: rapporto ripristinato, compliance soddisfatta.",
    },
    {
        "tag": "Due Diligence · M&A",
        "title": "Due diligence pre-acquisizione: frode evitata",
        "problem": "Prima di un'acquisizione, l'acquirente chiede una verifica indipendente sulla "
                   "target e sui suoi amministratori.",
        "approach": "Corporate e financial intelligence sulla target: assetti, collegamenti "
                    "occulti, procedimenti giudiziari, esposizione patrimoniale e media negativi, "
                    "il tutto certificato in un fascicolo unico.",
        "outcome": "Emerge un titolare occulto collegato a procedimenti rilevanti: l'operazione "
                   "viene interrotta prima del closing, evitando una perdita stimata in sette cifre.",
    },
]


def get_context(context):
    context.cases = CASES
