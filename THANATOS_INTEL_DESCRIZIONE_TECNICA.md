# THANATOS INTEL
## Piattaforma Integrata di Intelligence Investigativa
### Documento Tecnico per Deposito Marchio e Brevetto

---

**Titolare:** OneKeyCo S.r.l.  
**Autore tecnico:** Michele Milazzo  
**Data di redazione:** 9 giugno 2026  
**Versione:** 1.0  
**Riservatezza:** Confidenziale — uso esclusivo per procedura IP  

---

## 1. DENOMINAZIONE E MARCHIO

### 1.1 Nome

**THANATOS INTEL** (marchio denominativo)

Il nome deriva dalla figura mitologica greca di **Thanatos** (Θάνατος), personificazione della morte non violenta e simbolo di inevitabilità e certezza. Nel contesto della piattaforma, il nome evoca la certezza del risultato investigativo: ogni verifica conduce a una risposta definitiva.

**INTEL** richiama la tradizione del termine nel settore dell'intelligence operativa, indicando la raccolta, l'elaborazione e la produzione di informazioni strategicamente rilevanti.

### 1.2 Marchio figurativo

Il logotipo è composto da:
- Simbolo grafico: immagine stilizzata che evoca precisione e analisi
- Palette cromatica: blu scuro (#0A0E1A, #0D1B3E) e oro (#C8A96E)
- Tipografia: Georgia serif per denominazioni + sistema sans-serif per interfacce
- File logo: `thanatos-logo-mark.png` (marca) + `thanatos-icon-192.png` (favicon)

### 1.3 Classi merceologiche (Classificazione di Nizza)

- **Classe 42** — Servizi di ricerca e sviluppo scientifico; servizi informatici; software as a service (SaaS); piattaforme di analisi dati; due diligence digitale; intelligence investigativa.
- **Classe 45** — Servizi legali e investigativi; servizi di verifica identità; compliance KYC/KYB; servizi di due diligence diplomatica; gestione pratiche investigative.
- **Classe 35** — Servizi di analisi aziendale; monitoraggio sanzioni internazionali; gestione rischio reputazionale; elaborazione dati per attività anti-frode.

---

## 2. DESCRIZIONE DEL SISTEMA

### 2.1 Definizione

**THANATOS INTEL** è una piattaforma software integrata per la gestione completa di attività di intelligence investigativa privata. Il sistema integra in un'unica architettura: la gestione dei casi investigativi, la raccolta e custodia delle prove digitali, l'analisi OSINT (Open Source Intelligence), la due diligence documentale e diplomatica, il controllo sanzioni internazionali, il motore anti-frode, e la fatturazione automatizzata con adempimenti di e-fattura EU.

Il sistema è progettato per operatori investigativi professionali, agenzie legali, e organizzazioni soggette a obblighi di compliance KYC/KYB/AML.

### 2.2 Ambito di applicazione

- Investigazioni private (persone fisiche e giuridiche)
- Due diligence diplomatica (DDD) per pratiche di cittadinanza e passaporti
- Compliance anti-riciclaggio (AML) e controllo sanzioni
- Analisi cyber e intelligence su minacce digitali
- Verifica identità e autenticità documentale
- Gestione e distribuzione dei proventi tra investigatori e affiliati

---

## 3. ARCHITETTURA TECNICA

### 3.1 Stack tecnologico

| Componente | Tecnologia |
|------------|------------|
| Framework backend | Frappe v16 (Python 3.14) |
| ORM e database | MariaDB 10.x via Frappe ORM |
| Cache e code | Redis |
| Frontend | Vue.js 3 + JavaScript vanilla per portali |
| Web server | nginx + gunicorn |
| Containerizzazione | Docker (ambienti utente) + supervisord (bench diretto) |
| Infrastruttura cloud | Hetzner Cloud + Cloudflare CDN/DNS |
| Storage condiviso | NFS 100GB su rete WireGuard privata |
| AI gateway | Modello linguistico locale su rete interna (10.10.0.10:8800) |

### 3.2 Moduli principali

Il sistema è strutturato in **14 moduli funzionali** distinti:

```
thanatos_intel/
├── thanatos_core/          # Nucleo: casi, clienti, prove, report, investigatori
├── thanatos_ddd/           # Due Diligence Diplomatica
├── thanatos_cyber/         # Cyber intelligence: IOC, IP, domini, hash
├── thanatos_corporate/     # Intelligence societaria e corporate
├── thanatos_documents/     # Analisi documentale: passaporti, OCR, confronto
├── thanatos_fraud/         # Motore anti-frode: alert, regole rischio
├── thanatos_osint/         # OSINT: entità, relazioni, job di ricerca
├── thanatos_portal/        # Portale clienti: pratiche visto, checklist
├── fraud_engine/           # Blacklist, pattern fraudolenti
├── osint/                  # Engine OSINT (12 provider integrati)
├── billing/                # Fatturazione, crediti, distribuzioni
├── pipeline/               # State machine dei workflow investigativi
├── rules/                  # Motore regole rischio e scoring
├── integrations/           # Integrazioni esterne (Drive, Helpdesk, WABA, ecc.)
├── news/                   # Ingestion news e digest automatici
└── ai/                     # Modulo AI per analisi e sommari
```

---

## 4. ELEMENTI TECNICI INNOVATIVI

### 4.1 Pipeline Investigativa Adattiva (Brevettabile)

**Descrizione dell'invenzione:**

Il sistema implementa una **macchina a stati adattiva multi-tipo** per la gestione del flusso investigativo. A differenza dei sistemi tradizionali a workflow fisso, la pipeline di THANATOS INTEL:

1. **Determina dinamicamente lo step corrente** in base allo stato effettivo del documento (non a un flag manuale), interrogando in tempo reale i dati del caso
2. **Si adatta al tipo di pratica**: DDD (Due Diligence Diplomatica), Investigation (investigazione standard), OSINT (ricerca digitale), Antifrode (analisi truffa)
3. **Distingue l'attore responsabile** (cliente vs. operatore) per ogni step, generando notifiche differenziate e aggiornando l'interfaccia di conseguenza
4. **È resettabile automaticamente**: ogni modifica ai dati del caso fa ricalcolare l'intera pipeline senza stato persistente intermedio

**Struttura dell'algoritmo:**

```
get_pipeline(case) → lista_step_ordinata

Per ogni step S nella sequenza definita dal pipeline_key:
  S.status = done     se la condizione di completamento è verificata
  S.status = current  se è il primo step non completato
  S.status = pending  se segue lo step current
  S.status = blocked  se dipende da step non completati

Output: [{key, label, actor, status, desk_url, portal_url, description}, ...]
```

Questa architettura consente di:
- Visualizzare in real-time il collo di bottiglia operativo su qualsiasi caso
- Inviare notifiche mirate solo all'attore responsabile dello step corrente
- Calcolare KPI operativi (casi in attesa cliente, casi in attesa operatore) senza query complesse

**File di riferimento:** `thanatos_intel/pipeline/pipeline.py`

---

### 4.2 Motore di Risk Scoring Multi-Dimensionale (Brevettabile)

**Descrizione dell'invenzione:**

Il motore di scoring del rischio di THANATOS INTEL produce una valutazione quantitativa e qualitativa di un soggetto su **4 dimensioni indipendenti**, aggregabili in un indice composito.

**Segnali di rischio catalogati (24 categorie):**

| Categoria | Esempi di segnali |
|-----------|------------------|
| Documenti | MRZ checksum invalido, documento scaduto, fotografia non corrispondente |
| Identità | Liveness check fallito, incompletezza KYC |
| Compliance | Match sanzioni confermato, PEP ad alta confidenza, media avversa |
| Finanziario | Fonte fondi non dichiarata, conto bancario chiuso |
| Geopolitico | Giurisdizione ad alto rischio |
| Comportamentale | Risposte inconsistenti al questionario |
| Frode | Pattern EN590 (truffa advance-fee), crypto senza provenienza |

**Meccanismo di scoring:**

```
score_finale = min(100, Σ(peso_segnale_i))
livello = {
    0-20:   "low"
    21-50:  "medium"  
    51-75:  "high"
    76-99:  "critical"
    100:    "blocked"  # segnali bloccanti (sanctions_match, pattern EN590)
}
```

I segnali "bloccanti" (sanctions_match_confirmed, high_risk_pattern_en590) portano automaticamente lo score a 100 e bloccano il caso indipendentemente dagli altri segnali.

**File di riferimento:** `thanatos_intel/rules/risk_rules.py`

---

### 4.3 Sistema di Blacklist Multi-Fonte con Fusione Automatica (Brevettabile)

**Descrizione dell'invenzione:**

THANATOS INTEL implementa un sistema di gestione della blacklist che:

1. **Aggrega automaticamente** dati da fonti istituzionali internazionali gratuite (OFAC SDN, EU Financial Sanctions, UN Consolidated, Interpol Red Notices)
2. **Deduplica** tramite `external_id` univoco per fonte (es. `OFAC:7547`, `UN:6908161`, `EU:NK-226GXBd`)
3. **Promuove automaticamente** i risultati negativi degli OSINT lookup (AbuseIPDB score ≥ 25%, HIBP breach trovato) nella blacklist interna senza intervento manuale
4. **Mantiene la catena di provenienza** (source, source_url, source_dataset) per ogni voce, garantendo l'ammissibilità come prova documentale
5. **Si arricchisce quotidianamente** via job schedulato senza operatori

**Fonti integrate (aggiornamento giornaliero):**

| Fonte | Tipo dati | Ente |
|-------|-----------|------|
| OFAC SDN Enhanced XML | Persone e aziende sanzionate USA | US Treasury OFAC |
| EU Financial Sanctions (via OpenSanctions) | Sanzionati UE | Commissione Europea |
| UN Security Council Consolidated | Sanzionati ONU | Nazioni Unite |
| Interpol Red Notices | Ricercati internazionali | Interpol / OpenSanctions |
| OpenSanctions cache | Aggregato 100+ liste | OpenSanctions.org |

**Fonti reattive (per soggetto specifico):**

| Fonte | Dati | Note |
|-------|------|------|
| GLEIF LEI Registry | Ragione sociale, paese, stato LEI | Gratuito, no limiti |
| GDELT Project | Articoli di adverse media | Gratuito |
| AbuseIPDB | Reputazione IP | Free tier 1000/day |
| HaveIBeenPwned | Email in data breach | Richiede API key |

**File di riferimento:** `thanatos_intel/integrations/blacklist_ingest.py`

---

### 4.4 Modulo Due Diligence Diplomatica (DDD) — Metodologia Proprietaria

**Descrizione:**

Il modulo DDD implementa il processo di verifica di eleggibilità per pratiche di cittadinanza e passaporti diplomatici, integrando in un unico flusso:

- **Profilo richiedente (Applicant Profile):** dati anagrafici, passaporti multipli, KYC/KYB
- **Analisi passaporto:** verifica OCR, controllo MRZ, confronto fotografie
- **Screening sanzioni e PEP:** interrogazione OpenSanctions con fallback locale offline
- **Mandato d'incarico (Agency Mandate):** generazione, firma digitale (DocuSeal), custodia
- **Proforma DDD (Diplomatic Proforma):** preventivo con calcolo valuta RON/EUR (BNR)
- **Dossier finale:** aggregazione prove, catena di custodia, PDF certificato
- **Audit trail immutabile:** ogni evento è registrato in `Diplomatic Audit Log` con timestamp e utente

**Pipeline DDD (12 step verificabili):**

```
KYB/KYC → Mandato → Firma mandato → Preventivo → Pagamento →
Analisi passaporto → Screening sanzioni → Raccolta evidenze →
OSINT → Analisi antifrode → Report finale → Pratica chiusa
```

**Elementi normativi:** Il modulo implementa i requisiti di due diligence previsti dalla Direttiva (UE) 2015/849 (AMLD5) e successive modifiche, con tracciabilità completa per audit autorità.

**File di riferimento:** `thanatos_intel/thanatos_ddd/`

---

### 4.5 Catena di Custodia Digitale delle Prove (Chain of Custody)

**Descrizione:**

THANATOS INTEL implementa una catena di custodia conforme agli standard forensi digitali:

- Ogni prova acquisita genera un record immutabile in `Chain Of Custody Event`
- Ogni trasferimento, visione o modifica è loggata con: utente, timestamp, hash del file, modalità di acquisizione
- Il sistema integra con **Frappe Drive** per la conservazione centralizzata dei file, con cartelle create automaticamente per ogni caso
- Il log è esportabile come documento probatorio (`Custody Log Entry`) per uso in sede giudiziaria

**Struttura del record:**
```
Investigation Evidence → Chain Of Custody Event:
  - acquired_by (investigatore)
  - acquired_at (timestamp)
  - acquisition_method (fotografico, digitale, testimonianza)
  - file_hash (SHA256)
  - custodian (chi detiene fisicamente)
  - transfer_log (ogni passaggio di mano)
```

---

### 4.6 Motore OSINT Integrato (12 Provider)

Il modulo OSINT (`thanatos_intel/osint/engine.py`) integra in un'unica interfaccia 12 provider di intelligence digitale, con:

- **Cache Redis** (TTL 24h) per evitare richieste ridondanti
- **Persistenza automatica** di ogni lookup in `OSINT Lookup` per audit e reportistica
- **Promozione automatica** degli esiti negativi alla blacklist interna

**Provider integrati:**

| Provider | Tipo di dato | API Key |
|----------|-------------|---------|
| HaveIBeenPwned (HIBP) | Email in data breach | Sì |
| AbuseIPDB | Reputazione IP | Sì (free tier) |
| RDAP (rdap.org) | WHOIS domini e IP | No |
| OpenCorporates | Registro aziende globale | Opzionale |
| SecurityTrails | DNS history, subdomini | Sì |
| IPinfo | Geolocalizzazione IP, ASN | Sì (free tier) |
| VirusTotal v3 | Hash file, URL, domini, IP | Sì |
| URLScan.io | Scansione URL | Sì |
| Shodan | Esposizione host | Sì |
| Censys | Asset internet | Sì |
| GLEIF | Identificativi legali aziende | No |
| GDELT | Adverse media | No |

**Nuovi lookup persona/azienda (lookup_person, lookup_company_full):**  
Combinano OpenSanctions cache + ICIJ Offshore Leaks (cache locale) + GDELT + blacklist interna in una singola chiamata API con risk summary automatico.

---

### 4.7 Sistema di Notifiche Multi-Canale con Contestualizzazione Investigativa

THANATOS INTEL implementa un sistema di notifiche che:

- **WABA (WhatsApp Business API):** notifiche in italiano per eventi chiave del caso (mandato pronto, richiesta pagamento, report disponibile, step da completare) con template pre-approvati Meta
- **Email Frappe:** notifiche operative interne (nuovo ticket, assegnazione caso)
- **Helpdesk Bridge:** ogni ticket aperto dal cliente è automaticamente collegato al caso investigativo, con notifica all'investigatore assegnato
- **AI Digest:** sommari automatici giornalieri dei casi attivi, generati via AI gateway locale

---

## 5. FLUSSO OPERATIVO COMPLETO

```
                        ┌─────────────────────────────┐
                        │     PORTALE CLIENTI          │
                        │  (Investigation Client)      │
                        └──────────┬──────────────────┘
                                   │ nuovo caso / richiesta
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    INVESTIGATION CASE                            │
│  Numero caso, titolo, tipo, cliente, investigatore, priorità    │
└──────┬──────────────┬────────────────┬───────────────┬──────────┘
       │              │                │               │
       ▼              ▼                ▼               ▼
  KYC CHECK      KYB CHECK       OSINT JOB      INVESTIGATION
  (persona)     (azienda)       (ricerca        EVIDENCE
                               digitale)       (prove)
       │              │                │               │
       └──────────────┴────────────────┴───────────────┘
                                   │
                                   ▼
                         RISK SCORE ENGINE
                    (24 segnali, score 0-100)
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
              score < 75                    score ≥ 75
                    │                             │
                    ▼                             ▼
           INVESTIGATION                   FRAUD ALERT /
              REPORT                        BLOCCO CASO
          (PDF certificato)
                    │
                    ▼
         CHAIN OF CUSTODY
         (consegna prove)
                    │
                    ▼
             CASO CHIUSO
        (fattura + distribuzione)
```

---

## 6. MODULO DI BILLING E DISTRIBUZIONE RICAVI

Il sistema implementa un modulo di fatturazione avanzato specifico per il settore investigativo:

### 6.1 Struttura billing

- **Crediti cliente:** saldo prepagato per servizi a consumo (interrogazioni blacklist, OSINT job, verifica passaporto)
- **Subscription Plans:** piani fissi mensili/annuali con quote di servizio incluse
- **Revenue Distribution:** calcolo automatico delle quote per investigatore principale, co-investigatori, affiliati e costi infrastruttura
- **Party Payout:** liquidazione automatizzata dei compensi

### 6.2 Integrazione ERP (ERPNext)

- Sincronizzazione automatica con **Sales Invoice** (e-fattura EU) per clienti italiani e rumeni
- Calcolo automatico del tasso di cambio RON/EUR (BNR - Banca Nazionale della Romania) per entità rumene
- Profili e-fattura automatici per paese: EN 16931 (IT/RO), XRECHNUNG (DE), PEPPOL BIS (BE/NL)
- Proforma DDD: documento preventivo con numero di riferimento mandato

### 6.3 Integrazioni pagamento

- **Stripe:** pagamento online diretto, webhook per conferma automatica
- **DocuSeal:** firma digitale contratti e mandati con archiviazione legale

---

## 7. PORTALE CLIENTI E ACCESSO DIFFERENZIATO

### 7.1 Ruoli e accesso

| Ruolo | Accesso |
|-------|---------|
| Investigation Client | Portale clienti: propri casi, documenti, fatture, supporto |
| Affiliate | Portale: casi riferiti, commissioni |
| Investigator | Portale operatori: board tutti i casi + desk ERPNext |
| Investigation Manager | Accesso completo: gestione team, analytics, desk ERPNext |
| System Manager | Accesso sistema completo |

### 7.2 Portale web (interfaccia clienti)

Pagine dedicate con design dark-mode esclusivo:
- `/portal` — Dashboard: casi, documenti, fatture, azioni in sospeso
- `/portal/case/{name}` — Dettaglio caso: timeline, prove, report, ticket supporto
- `/portal/verifica-blacklist` — Servizio a pagamento: verifica email/IP/IBAN/azienda
- `/portal/ops` — Centro operativo investigatori: board casi per step pipeline
- `/portal/guide` — Procedure passo-passo per clienti e operatori
- `/news` — Intelligence news feed aggregato

### 7.3 Navigazione contestuale

Il sistema implementa una navigazione adattiva al ruolo: il menu del portale varia automaticamente mostrando link a **Drive** (storage file), **CRM**, **Helpdesk**, **Desk ERPNext** solo agli operatori; ai clienti mostra documenti, fatture e supporto.

---

## 8. INTEGRAZIONI ESTERNE

| Applicazione | Ruolo nel sistema | Tipo integrazione |
|-------------|------------------|-------------------|
| **Frappe Drive** | Storage centralizzato file/prove per caso | Cartella automatica per caso, bridge accesso |
| **Frappe CRM** | Gestione pipeline commerciale / pre-vendita | Sync automatico deal→caso |
| **Frappe Helpdesk** | Ticketing supporto clienti | Ticket linkati a Investigation Case |
| **Frappe Insights** | Dashboard analytics e KPI | Query predefinite: casi per stato, mandati, revenue |
| **Frappe Wiki** | Knowledge base procedure operative | 7 pagine procedure standard |
| **DocuSeal** | Firma digitale mandati e contratti | API REST, template mandato/proforma |
| **OpenSanctions** | Database sanzioni internazionali | CSV pubblico + API match |
| **OFAC / EU / UN** | Liste sanzioni ufficiali | XML/CSV scaricati giornalmente |
| **Stripe** | Pagamenti online | API v3, webhook |
| **WABA** | Notifiche WhatsApp Business | API Meta Cloud, template IT |
| **AI gateway** | Sommari, analisi, digest | HTTP interno rete WireGuard |

---

## 9. SICUREZZA E PRIVACY

### 9.1 Controllo accessi

- Ogni doctype sensibile ha `permission_query_conditions` personalizzate: un cliente vede solo i propri casi, un investigatore vede i casi assegnati, un manager vede tutto
- Il campo `has_permission` su Investigation Case, Client, Evidence, Report, OSINT Job è gestito da funzioni Python custom (non dagli ACL standard Frappe)
- Tutte le API whitelist sono protette da `frappe.session.user` check + ruolo

### 9.2 Privacy dei dati

- Nessun dato investigativo viene inviato a servizi cloud non autorizzati
- Il modello AI gira su infrastruttura privata (rete interna WireGuard)
- I backup sono su StorageBox Hetzner EU (server in Germania, GDPR compliant)
- La catena di custodia garantisce l'integrità probatoria

### 9.3 Audit trail

- Ogni documento ha `track_changes: 1` per la storia delle modifiche
- `Diplomatic Audit Log`: log immutabile specifico per pratiche DDD
- `OSINT Lookup`: registro di ogni interrogazione eseguita (quando, chi, su cosa)
- `Blacklist Entry`: ogni voce ha sorgente, dataset, URL originale e data ultimo aggiornamento

---

## 10. NOVITÀ E ORIGINALITÀ AI FINI BREVETTUALI

### 10.1 Elementi nuovi rispetto allo stato dell'arte

La combinazione dei seguenti elementi, integrata in un'unica piattaforma, non ha precedenti noti nel settore:

1. **Pipeline adattiva senza stato persistente** — a differenza dei workflow tradizionali (Jira, Monday, Asana), lo step corrente viene calcolato in real-time interrogando i dati effettivi del caso, non un flag di avanzamento manuale

2. **Fusione automatica multi-fonte di blacklist** — il sistema non solo aggrega OFAC/EU/UN ma promuove autonomamente gli esiti negativi di ogni OSINT lookup (IP, email, azienda) nella blacklist interna senza operatore, mantenendo `external_id` univoco per dedup cross-fonte

3. **Risk scoring investigativo a segnali bloccanti** — lo score non è una media ma un sistema a soglie con segnali "blocking" che portano lo score a 100 indipendentemente dagli altri, con effetto di blocco automatico del caso

4. **Due diligence diplomatica end-to-end digitalizzata** — dal profilo richiedente alla firma del mandato, dallo screening sanzioni al dossier finale, in un unico flusso documentale tracciato con catena di custodia forense

5. **Distribuzione automatizzata dei proventi investigativi** — calcolo e liquidazione quote per caso tra investigatori, affiliati e struttura, integrato nativamente nel ciclo di fatturazione ERP

### 10.2 Elementi non banali

- L'integrazione del calcolo del tasso di cambio BNR (RON) direttamente nelle proforma e fatture per entità rumene, senza intervento manuale, è specifica del settore delle agenzie di investigazione con attività transfrontaliere IT-RO
- La gestione della visibilità dei file Drive per ruolo investigativo (blocco accesso per ruoli portal) tramite monkey-patch lazy sul modulo `drive.api.product` è una soluzione tecnica originale al problema dell'integrazione tra sistemi Frappe indipendenti

---

## 11. DEPLOYMENT E OPERATIVITÀ

### 11.1 Infrastruttura

```
Internet
    │
Cloudflare CDN/DNS (protezione DDoS, SSL)
    │
nginx (reverse proxy)
    │
    ├── thanatos.onekeyco.com → bench Frappe (porta 8000)
    │     ├── gunicorn (workers)
    │     ├── Redis (cache + queue)
    │     └── MariaDB (database)
    │
    └── /mnt/mmos-shared-storage (NFS 100GB WireGuard)
          └── File Drive / media investigativi
```

### 11.2 Aggiornamenti automatici

- **Giornaliero:** Aggiornamento blacklist (OFAC+EU+UN+Interpol), fetch tassi di cambio BNR, news digest AI, OpenSanctions sync
- **Orario:** Ingestione news, fetch tassi di cambio FX

---

## 12. GLOSSARIO TECNICO

| Termine | Definizione |
|---------|-------------|
| DDD | Due Diligence Diplomatica — processo di verifica per pratiche di cittadinanza/passaporto |
| KYC | Know Your Customer — verifica identità persona fisica |
| KYB | Know Your Business — verifica identità aziendale |
| AML | Anti-Money Laundering — prevenzione riciclaggio |
| PEP | Politically Exposed Person — persona politicamente esposta |
| OSINT | Open Source Intelligence — intelligence da fonti aperte |
| IOC | Indicator of Compromise — indicatore di compromissione cyber |
| MRZ | Machine Readable Zone — zona leggibile automaticamente dei passaporti |
| OFAC | Office of Foreign Assets Control — ufficio US Treasury per sanzioni |
| SDN | Specially Designated Nationals — lista sanzionati OFAC |
| LEI | Legal Entity Identifier — identificatore legale aziendale (standard GLEIF) |
| Chain of Custody | Catena di custodia — documentazione dell'integrità delle prove |
| Pipeline | Sequenza di step investigativi con stato calcolato automaticamente |
| Blacklist Entry | Voce nella lista nera interna, arricchita da fonti istituzionali |
| e-Fattura EU | Fatturazione elettronica conforme standard europei (EN 16931, XRECHNUNG) |

---

## 13. CONTATTI E RIFERIMENTI

**Titolare:**  
OneKeyCo S.r.l.  
Email: info@onekeyco.com  
Web: https://thanatos.onekeyco.com  

**Repository codice sorgente:**  
https://github.com/michelemilazzo/thanatos_intel (privato)  

**Versione del software documentata:**  
v0.1.0 — commit branch `main`, data 9 giugno 2026  

---

*Documento predisposto ai fini del deposito di marchio presso l'Ufficio Italiano Brevetti e Marchi (UIBM) e dell'Ufficio dell'Unione Europea per la Proprietà Intellettuale (EUIPO), e per eventuale deposito di brevetto per invenzione industriale ai sensi degli artt. 45 e ss. del Codice della Proprietà Industriale (D.Lgs. 30/2005).*

*Il contenuto di questo documento è riservato. La divulgazione non autorizzata costituisce violazione del segreto industriale ai sensi dell'art. 98 del Codice della Proprietà Industriale.*
