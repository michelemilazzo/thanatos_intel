# -*- coding: utf-8 -*-
"""Catalogo documenti SPID-recuperabili dal CLIENTE (self-service).

Il cliente si autentica LUI con SPID sul sito ufficiale, scarica il documento e
lo carica in pratica. Mai le sue credenziali (sostituzione di persona art. 494 c.p.).
Ogni voce guida il cliente: ente + URL + istruzione breve + passi dettagliati.
"""

# Aiuto generale SPID, mostrato a chi non sa cos'è / non ce l'ha / non sa accedere.
SPID_HELP = {
    "cosa": ("SPID è la tua identità digitale: un'unica username e password per "
             "accedere ai siti della Pubblica Amministrazione. È gratuito e sicuro."),
    "no_spid": [
        "Non hai SPID? Puoi ottenerlo gratis in circa 15 minuti su spid.gov.it "
        "scegliendo un gestore (Poste, Aruba, InfoCert, ecc.).",
        "In alternativa a SPID puoi usare la CIE (Carta d'Identità Elettronica) "
        "con il suo PIN e l'app «CieID»: è accettata sugli stessi siti.",
        "Se non te la senti o hai difficoltà, premi «Ho bisogno di aiuto» qui "
        "sotto: ti ricontattiamo noi e lo facciamo insieme.",
    ],
    "come_accedere": [
        "Apri il link del sito indicato per il documento.",
        "Clicca «Entra con SPID» (o «Accedi») e scegli il tuo gestore.",
        "Inserisci username e password SPID e conferma sull'app del gestore "
        "(ti arriva una notifica sul telefono).",
        "Cerca la sezione indicata nei passi e scarica il documento in PDF.",
        "Torna qui, spunta il consenso e carica il PDF.",
    ],
    "spid_url": "https://www.spid.gov.it/",
}

SPID_DOCS = {
    "cassetto_fiscale": {
        "label": "Cassetto fiscale",
        "ente": "Agenzia delle Entrate",
        "url": "https://www.agenziaentrate.gov.it/portale/area-riservata",
        "istruzioni": "Area riservata → «Cassetto fiscale» → scarica in PDF "
                      "(dichiarazioni, versamenti F24, comunicazioni).",
        "steps": [
            "Apri agenziaentrate.gov.it e clicca «Area riservata».",
            "Accedi con SPID (o CIE).",
            "Nel menu scegli «Cassetto fiscale».",
            "Apri la sezione che ti serve (Dichiarazioni, Versamenti, ecc.) e "
            "usa «Stampa/Scarica» per ottenere il PDF.",
        ],
    },
    "estratto_inps": {
        "label": "Estratto conto contributivo (INPS)",
        "ente": "INPS",
        "url": "https://www.inps.it/",
        "istruzioni": "MyINPS → «Estratto conto contributivo» → scarica il PDF.",
        "steps": [
            "Apri inps.it e clicca «Accedi» / «MyINPS».",
            "Accedi con SPID (o CIE).",
            "Cerca «Estratto conto contributivo» nella barra di ricerca del sito.",
            "Apri l'estratto e scaricalo/stampalo in PDF.",
        ],
    },
    "anagrafe_anpr": {
        "label": "Certificati anagrafici (residenza / stato di famiglia)",
        "ente": "ANPR — Ministero dell'Interno",
        "url": "https://www.anpr.interno.it/",
        "istruzioni": "ANPR → «Certificati» → scarica residenza e/o stato di "
                      "famiglia (gratuiti).",
        "steps": [
            "Apri anpr.interno.it e clicca «Accedi ai servizi al cittadino».",
            "Accedi con SPID (o CIE).",
            "Scegli «Certificati» e seleziona «Residenza» o «Stato di famiglia».",
            "Seleziona te stesso, conferma e scarica il PDF (è gratuito).",
        ],
    },
    "casellario": {
        "label": "Certificato del casellario giudiziale / carichi pendenti",
        "ente": "Ministero della Giustizia",
        "url": "https://certificaticgc.giustizia.it/certificati/",
        "istruzioni": "Accedi con SPID → richiedi il certificato → scarica il PDF.",
        "steps": [
            "Apri certificaticgc.giustizia.it/certificati e clicca «Accedi».",
            "Accedi con SPID (o CIE).",
            "Scegli «Certificato del casellario giudiziale» (e/o «carichi pendenti»).",
            "Conferma i dati e scarica il certificato in PDF.",
        ],
    },
    "visura_impresa": {
        "label": "Visura camerale della propria impresa",
        "ente": "Registro Imprese — impresa.italia.it",
        "url": "https://impresa.italia.it/",
        "istruzioni": "Cassetto digitale dell'imprenditore → scarica la visura "
                      "della tua impresa.",
        "steps": [
            "Apri impresa.italia.it e clicca «Entra».",
            "Accedi con SPID (o CIE).",
            "Apri il «Cassetto digitale» della tua impresa.",
            "Scarica la «Visura» in PDF.",
        ],
    },
    "visura_catastale": {
        "label": "Visura catastale / ipotecaria dei propri immobili",
        "ente": "Agenzia delle Entrate — Territorio",
        "url": "https://www.agenziaentrate.gov.it/portale/area-riservata",
        "istruzioni": "Area riservata → «Consultazione rendite / visure catastali» "
                      "→ scarica la visura.",
        "steps": [
            "Apri agenziaentrate.gov.it e clicca «Area riservata».",
            "Accedi con SPID (o CIE).",
            "Cerca «Visure catastali» o «Consultazione rendite».",
            "Seleziona i tuoi immobili e scarica la visura in PDF.",
        ],
    },
    "fascicolo_prev": {
        "label": "Estratto conto previdenziale certificato (ECOCERT)",
        "ente": "INPS",
        "url": "https://www.inps.it/",
        "istruzioni": "MyINPS → «ECOCERT» → richiedi e scarica il PDF.",
        "steps": [
            "Apri inps.it e clicca «Accedi» / «MyINPS».",
            "Accedi con SPID (o CIE).",
            "Cerca «ECOCERT» (Estratto conto certificato).",
            "Richiedi il documento e scaricalo in PDF quando è pronto.",
        ],
    },
    "altro": {
        "label": "Altro documento (specificato dall'operatore)",
        "ente": "—",
        "url": "",
        "istruzioni": "Recupera il documento indicato dall'operatore "
                      "autenticandoti con SPID sul portale del relativo ente.",
        "steps": [
            "Segui le indicazioni dell'operatore (vedi le note della richiesta).",
            "Accedi al portale dell'ente con SPID (o CIE) e scarica il documento.",
            "Se non sai come fare, premi «Ho bisogno di aiuto».",
        ],
    },
}


def doc_label(key):
    return (SPID_DOCS.get(key) or SPID_DOCS["altro"])["label"]


def doc_guidance(key):
    return SPID_DOCS.get(key) or SPID_DOCS["altro"]
