"""Accordi legali MMOS ↔ Thanatos ↔ Clienti.

Fonte unica: usati dalla pagina /portal/legale e dal gate di compliance della
vendita self-serve. Versione 2026-07 (testo definitivo).
"""

VERSION = "2026-07"
DISCLAIMER = ("Versione %s. Per assistenza o segnalazioni relative al trattamento dei dati: "
              "admin@thanatos.agency." % VERSION)

# ── 1) Termini di Servizio Cliente (Thanatos ↔ Cliente) ──────────────────────
TOS_CLIENTE = """## Termini di Servizio
Thanatos Intelligence — Cliente
Versione 2026-07

**1. Oggetto.** Thanatos fornisce al Cliente l'accesso a dati e documenti da fonti
ufficiali e pubbliche (es. visure camerali, bilanci, certificati del Registro
Imprese) e, su mandato, servizi investigativi e di due diligence.

**2. Titolarità del trattamento.** Il Cliente è titolare autonomo del trattamento
(art. 4, n. 7, GDPR) per i dati personali che richiede e riceve tramite la
piattaforma: determina finalità e mezzi del trattamento successivo all'erogazione
del servizio e ne risponde in proprio verso gli interessati e le autorità di
controllo.

Thanatos tratta i dati necessari all'erogazione del servizio in qualità di titolare
autonomo per le finalità di gestione del rapporto contrattuale, fatturazione e
adempimenti di legge, e agisce come responsabile del trattamento (art. 28 GDPR)
limitatamente all'inoltro delle richieste alle fonti terze per conto del Cliente. I
rapporti di responsabile del trattamento sono regolati da apposito accordo (DPA),
disponibile su richiesta.

**3. Base giuridica.** Per i servizi su soggetti terzi rispetto al Cliente (es.
verifiche di negatività, patrimoniali, rintraccio), il Cliente dichiara, prima
dell'esecuzione, la base giuridica che legittima la richiesta ai sensi dell'art. 6
GDPR (interesse legittimo, esecuzione o tutela di un diritto in sede giudiziaria,
adempimento di un obbligo di legge, o consenso dell'interessato) e la finalità
perseguita. La dichiarazione è registrata con data, ora e riferimento alla
richiesta (Consent Record — v. Allegato A).

Thanatos può rifiutare o sospendere richieste prive di base giuridica adeguata o
palesemente incompatibili con le finalità dichiarate.

**4. Fonti e natura dei dati.** Visure, bilanci e certificati camerali sono dati
pubblici del Registro Imprese, liberamente accessibili. Per gli altri servizi,
Thanatos non garantisce completezza, esattezza o aggiornamento oltre quanto
fornito dalla fonte originaria.

**5. Uso consentito.** I dati forniti sono destinati all'uso interno del Cliente e
alla sola finalità dichiarata. Sono vietate la rivendita, la diffusione a terzi non
autorizzati e qualunque trattamento ulteriore incompatibile con il GDPR e la
normativa applicabile.

**6. Diritti dell'interessato.** Il Cliente, in quanto titolare autonomo, è
responsabile di dare seguito alle richieste di esercizio dei diritti (accesso,
rettifica, cancellazione, limitazione, portabilità, opposizione — artt. 15-22
GDPR) ricevute dagli interessati sui dati trattati. Thanatos fornisce assistenza
tecnica per le richieste relative ai dati custoditi sulla propria piattaforma e le
inoltra al Cliente entro termini ragionevoli.

**7. Conservazione e sicurezza.** I documenti acquistati restano disponibili
nell'archivio del Cliente sul portale per la durata del rapporto contrattuale e,
ove collegati a un caso, sono soggetti a catena di custodia. Thanatos adotta
misure tecniche e organizzative adeguate (art. 32 GDPR) a protezione dei dati,
inclusa la cifratura in transito e a riposo e il controllo degli accessi.

I dati sono conservati per il tempo necessario alle finalità del servizio e agli
obblighi di legge, salvo diverso accordo scritto.

**8. Trasferimenti extra-SEE.** Eventuali trasferimenti di dati verso Paesi
extra-SEE avvengono solo verso fornitori che garantiscono un livello di protezione
adeguato (decisione di adeguatezza, clausole contrattuali standard o altra
garanzia ex artt. 44-49 GDPR).

**9. Responsabilità.** Thanatos risponde della corretta esecuzione del servizio,
non dell'uso che il Cliente fa dei dati né di errori della fonte ufficiale. Il
Cliente manleva Thanatos da ogni responsabilità derivante da una base giuridica
dichiarata falsamente o da un uso dei dati difforme da quanto dichiarato.

**10. Corrispettivi.** I servizi a consumo sono prepagati tramite credito («wallet
servizi») secondo il listino vigente, consultabile sul portale. I servizi già
eseguiti non sono rimborsabili; il credito residuo non utilizzato è rimborsabile
secondo le condizioni pubblicate sul portale.

**11. Violazioni e sospensione.** Thanatos può sospendere l'accesso al servizio in
caso di violazione dei presenti Termini, di dichiarazioni di base giuridica non
veritiere o di uso dei dati non conforme alla finalità dichiarata, dandone
comunicazione al Cliente.

**12. Legge applicabile e foro.** Ai presenti Termini si applica la legge rumena.
Per ogni controversia è competente in via esclusiva il foro di Costanza
(Constanța), Romania, salvo norme inderogabili a tutela del consumatore
eventualmente applicabili al Cliente persona fisica.

**13. Titolare per contatti privacy.** Per l'esercizio dei diritti o segnalazioni
relative al trattamento dei dati: admin@thanatos.agency.
"""

# ── 2) Allegato A — Dichiarazione di base giuridica (gate servizi su terzi) ──
DICHIARAZIONE_INTERESSE = """## Allegato A — Dichiarazione di base giuridica

Da compilare dal Cliente prima dell'esecuzione di ogni servizio su soggetto terzo.

Il sottoscritto Cliente, in relazione alla richiesta del servizio **«{servizio}»**
sul soggetto **«{target}»**, dichiara sotto la propria responsabilità di:

- avere una **base giuridica legittima** ai sensi dell'art. 6 GDPR (interesse
  legittimo, esecuzione o tutela di un diritto in sede giudiziaria, adempimento di
  un obbligo di legge, o consenso dell'interessato);
- utilizzare i dati **esclusivamente** per la finalità dichiarata, nel rispetto del
  GDPR e della normativa applicabile;
- manlevare Thanatos da ogni responsabilità derivante da un uso difforme o da una
  base giuridica dichiarata falsamente.

Finalità dichiarata: __________________________________________________

L'accettazione genera un Consent Record con data, ora e riferimento alla
richiesta.
"""

# ── 3) Allegato B — Rapporti MMOS ↔ Thanatos (wholesale) ─────────────────────
ACCORDO_MMOS_THANATOS = """## Allegato B — Rapporti MMOS ↔ Thanatos (wholesale)

MMOS fornisce a Thanatos, in modalità wholesale, l'accesso a servizi dati di terze
parti e all'infrastruttura cloud necessaria all'erogazione del servizio.

Nell'ambito di tali rapporti, MMOS tratta dati per conto di Thanatos limitatamente
all'inoltro tecnico delle richieste alle fonti terze e opera quale responsabile
del trattamento ai sensi dell'art. 28 GDPR, secondo DPA separato che ne
disciplina istruzioni, misure di sicurezza, subresponsabili e notifica di data
breach.

Le condizioni economiche (prezzi, commissioni, modalità di ricarica) sono
definite nel listino e nel contratto commerciale separato tra le parti.

Legge applicabile e foro: legge rumena, foro esclusivo di Costanza (Constanța),
Romania.
"""

DOCS = {
    "tos_cliente": {"titolo": "Termini di Servizio — Cliente", "testo": TOS_CLIENTE},
    "dichiarazione": {"titolo": "Allegato A — Dichiarazione di base giuridica", "testo": DICHIARAZIONE_INTERESSE},
    "accordo_mmos": {"titolo": "Allegato B — Rapporti MMOS ↔ Thanatos", "testo": ACCORDO_MMOS_THANATOS},
}


def get_doc(key, **fmt):
    d = DOCS.get(key)
    if not d:
        return None
    testo = d["testo"].format(**fmt) if fmt else d["testo"]
    return {"key": key, "titolo": d["titolo"], "testo": testo, "version": VERSION, "draft": False}


def all_docs():
    return [{"key": k, "titolo": v["titolo"], "testo": v["testo"]} for k, v in DOCS.items()]
