# -*- coding: utf-8 -*-
"""Catalogo documenti SPID-recuperabili dal CLIENTE (self-service).

Il cliente si autentica LUI con SPID sul sito ufficiale, scarica il documento e
lo carica in pratica. Mai le sue credenziali (sostituzione di persona art. 494 c.p.).
Ogni voce guida il cliente su ente + URL + come ottenerlo.
"""

SPID_DOCS = {
    "cassetto_fiscale": {
        "label": "Cassetto fiscale",
        "ente": "Agenzia delle Entrate",
        "url": "https://www.agenziaentrate.gov.it/portale/area-riservata",
        "istruzioni": "Accedi con SPID all'Area riservata → «Cassetto fiscale» → "
                      "scarica/stampa in PDF (dichiarazioni, versamenti F24, comunicazioni).",
    },
    "estratto_inps": {
        "label": "Estratto conto contributivo (INPS)",
        "ente": "INPS",
        "url": "https://www.inps.it/",
        "istruzioni": "Accedi con SPID a MyINPS → «Estratto conto contributivo» → "
                      "scarica il PDF della posizione assicurativa.",
    },
    "anagrafe_anpr": {
        "label": "Certificati anagrafici (residenza / stato di famiglia)",
        "ente": "ANPR — Ministero dell'Interno",
        "url": "https://www.anpr.interno.it/",
        "istruzioni": "Accedi con SPID ad ANPR → «Certificati» → scarica in PDF il "
                      "certificato di residenza e/o stato di famiglia (gratuiti).",
    },
    "casellario": {
        "label": "Certificato del casellario giudiziale / carichi pendenti",
        "ente": "Ministero della Giustizia",
        "url": "https://certificaticgc.giustizia.it/certificati/",
        "istruzioni": "Accedi con SPID → richiedi il certificato del casellario "
                      "giudiziale (e/o dei carichi pendenti) → scarica il PDF.",
    },
    "visura_impresa": {
        "label": "Visura camerale della propria impresa",
        "ente": "Registro Imprese — impresa.italia.it",
        "url": "https://impresa.italia.it/",
        "istruzioni": "Accedi con SPID al Cassetto digitale dell'imprenditore → "
                      "scarica la visura camerale della tua impresa.",
    },
    "visura_catastale": {
        "label": "Visura catastale / ipotecaria dei propri immobili",
        "ente": "Agenzia delle Entrate — Territorio",
        "url": "https://www.agenziaentrate.gov.it/portale/area-riservata",
        "istruzioni": "Accedi con SPID all'Area riservata → «Consultazione rendite / "
                      "visure catastali» → scarica la visura dei tuoi immobili.",
    },
    "fascicolo_prev": {
        "label": "Estratto conto previdenziale certificato (ECOCERT)",
        "ente": "INPS",
        "url": "https://www.inps.it/",
        "istruzioni": "Accedi con SPID a MyINPS → «ECOCERT — Estratto conto certificato» → "
                      "richiedi e scarica il PDF.",
    },
    "altro": {
        "label": "Altro documento (specificato dall'operatore)",
        "ente": "—",
        "url": "",
        "istruzioni": "Recupera il documento indicato dall'operatore autenticandoti con "
                      "SPID sul portale del relativo ente, poi caricalo qui.",
    },
}


def doc_label(key):
    return (SPID_DOCS.get(key) or SPID_DOCS["altro"])["label"]


def doc_guidance(key):
    return SPID_DOCS.get(key) or SPID_DOCS["altro"]
