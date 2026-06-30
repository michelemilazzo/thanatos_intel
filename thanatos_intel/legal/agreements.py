"""Accordi legali MMOS ↔ Thanatos ↔ Clienti — BOZZE.

⚠️ DRAFT: testi generati come bozza operativa, DA VALIDARE con un legale prima
dell'uso vincolante. Fonte unica: usati dalla pagina /portal/legale e dal gate
di compliance della vendita self-serve.
"""

VERSION = "2026-06-DRAFT"
DISCLAIMER = ("⚠️ BOZZA — da validare con un legale prima dell'uso vincolante. "
              "Versione %s." % VERSION)

# ── 1) Termini di Servizio Cliente (Thanatos ↔ Cliente) ──────────────────────
TOS_CLIENTE = """## Termini di Servizio — Thanatos Intelligence

**1. Oggetto.** Thanatos fornisce al Cliente servizi di accesso a dati e documenti
da fonti ufficiali e pubbliche (es. visure camerali, bilanci, certificati del
Registro Imprese) e, su mandato, servizi investigativi e di due diligence.

**2. Acquisto e wallet.** I servizi a consumo sono prepagati tramite credito
(«wallet servizi»). Il Cliente ricarica il wallet con carta; al credito si applica
la commissione di pagamento (3% + 0,40 €). Ogni servizio scala il relativo importo
dal wallet al momento dell'esecuzione. Il prezzo è quello esposto a listino.

**3. Documenti pubblici.** Visure, bilanci e certificati camerali sono **dati
pubblici** del Registro Imprese: il Cliente può richiederli liberamente. Thanatos
non garantisce completezza/aggiornamento oltre quanto fornito dalla fonte.

**4. Servizi su soggetti terzi.** Per servizi che riguardano persone diverse dal
Cliente (es. negatività, patrimoniale, rintraccio), il Cliente **dichiara di avere
una base giuridica legittima** (interesse legittimo, tutela di un diritto, obbligo
di legge) e si assume ogni responsabilità per l'uso dei dati. Thanatos registra la
dichiarazione e può rifiutare o sospendere richieste prive di base giuridica.

**5. Uso consentito.** I dati e i documenti forniti sono per uso interno del Cliente
e per la finalità dichiarata. È vietata la rivendita, la diffusione indebita e ogni
uso in violazione del GDPR (Reg. UE 2016/679) e della normativa applicabile.

**6. Responsabilità.** Thanatos risponde della corretta esecuzione del servizio, non
dell'uso che il Cliente fa dei dati né degli errori della fonte ufficiale. Nessuna
responsabilità per finalità illecite dichiarate falsamente dal Cliente.

**7. Conservazione.** I documenti acquistati restano disponibili nell'archivio del
Cliente (portale) e, ove agganciati a un caso, soggetti a catena di custodia.

**8. Recesso e rimborsi.** I servizi a consumo già eseguiti non sono rimborsabili
(la fonte è già stata interrogata a pagamento). Il credito non utilizzato è
rimborsabile al netto delle commissioni.

**9. Legge e foro.** [DA DEFINIRE con il legale — coerente con la giurisdizione
dell'entità che fattura: Italia/ARES o Romania/Thanatos].
"""

# ── 2) Dichiarazione di interesse legittimo (gate servizi su terzi) ───────────
DICHIARAZIONE_INTERESSE = """## Dichiarazione di base giuridica

Il sottoscritto Cliente, in relazione alla richiesta del servizio **«{servizio}»**
sul soggetto **«{target}»**, dichiara sotto la propria responsabilità di:

- avere una **base giuridica legittima** al trattamento dei dati richiesti (una tra:
  interesse legittimo ex art. 6.1.f GDPR, esecuzione/tutela di un diritto in sede
  giudiziaria, adempimento di obbligo di legge, consenso dell'interessato);
- utilizzare i dati **esclusivamente** per la finalità dichiarata e nel rispetto del
  GDPR e della normativa applicabile;
- manlevare Thanatos da ogni responsabilità derivante da un uso difforme o da una
  base giuridica dichiarata falsamente.

Finalità dichiarata: __________________________________________________

Accettando, il Cliente conferma quanto sopra. La dichiarazione è registrata
(Consent Record) con data, ora e riferimento alla richiesta.
"""

# ── 3) Accordo wholesale MMOS ↔ Thanatos ─────────────────────────────────────
ACCORDO_MMOS_THANATOS = """## Accordo di rivendita all'ingrosso — MMOS ↔ Thanatos

**1. Oggetto.** MMOS fornisce a Thanatos, in modalità wholesale, l'accesso ai
servizi dati di terze parti (openapi.it e affini) e all'infrastruttura cloud.

**2. Prezzo wholesale.** MMOS fattura a Thanatos il **costo della fonte × 3**
(markup di piattaforma fisso, uguale per tutti i rivenditori). Il prezzo finale al
cliente è stabilito autonomamente da Thanatos (rivendita).

**3. Wallet di piattaforma.** Thanatos mantiene un **credito prepagato** presso MMOS
(portale cloud.onekeyco.com). Ogni consumo di un servizio scala dal wallet MMOS
l'importo wholesale al momento dell'esecuzione. Thanatos ricarica con carta (più
commissione di pagamento 3% + 0,40 €).

**4. Niente sospensione retroattiva.** Un servizio già eseguito è dovuto a MMOS anche
se il wallet va in negativo entro il fido concordato; oltre il fido i nuovi consumi
sono bloccati fino a ricarica.

**5. Audit.** I movimenti del wallet sono tracciati su ledger immutabile (hash-chain)
e riconciliati. Eventuale fatturazione mensile a saldo opera sul consumato.

**6. Responsabilità.** MMOS risponde della disponibilità tecnica del servizio e del
corretto inoltro alla fonte; non risponde dell'uso che Thanatos/Cliente fanno dei
dati né degli errori della fonte ufficiale.

**7. Durata e legge.** [DA DEFINIRE con il legale].
"""

DOCS = {
    "tos_cliente": {"titolo": "Termini di Servizio — Cliente", "testo": TOS_CLIENTE},
    "dichiarazione": {"titolo": "Dichiarazione di base giuridica", "testo": DICHIARAZIONE_INTERESSE},
    "accordo_mmos": {"titolo": "Accordo wholesale MMOS ↔ Thanatos", "testo": ACCORDO_MMOS_THANATOS},
}


def get_doc(key, **fmt):
    d = DOCS.get(key)
    if not d:
        return None
    testo = d["testo"].format(**fmt) if fmt else d["testo"]
    return {"key": key, "titolo": d["titolo"], "testo": testo, "version": VERSION, "draft": True}


def all_docs():
    return [{"key": k, "titolo": v["titolo"], "testo": v["testo"]} for k, v in DOCS.items()]
