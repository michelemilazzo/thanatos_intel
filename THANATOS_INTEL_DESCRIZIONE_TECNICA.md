# THANATOS INTEL
## Piattaforma Integrata di Intelligence Investigativa
### Documento Tecnico — Visione, Architettura, Stato e Roadmap

---

**Titolare:** OneKeyCo S.r.l.  
**Autore:** Michele Milazzo  
**Data:** 9 giugno 2026 — Versione 2.0  
**Uso:** Deposito marchio/brevetto · Riferimento tecnico interno · Tracciatura avanzamento  
**Riservatezza:** Confidenziale

---

## INDICE

1. [Visione originale del progetto](#1-visione-originale-del-progetto)
2. [Denominazione e marchio](#2-denominazione-e-marchio)
3. [Architettura generale del sistema](#3-architettura-generale-del-sistema)
4. [Infrastruttura server e AI](#4-infrastruttura-server-e-ai)
5. [Moduli funzionali — dettaglio](#5-moduli-funzionali--dettaglio)
6. [Elementi tecnici innovativi (brevettabili)](#6-elementi-tecnici-innovativi-brevettabili)
7. [Integrazioni esterne](#7-integrazioni-esterne)
8. [Flusso operativo completo](#8-flusso-operativo-completo)
9. [Billing, entità legali e distribuzione ricavi](#9-billing-entità-legali-e-distribuzione-ricavi)
10. [Portale clienti e accesso differenziato](#10-portale-clienti-e-accesso-differenziato)
11. [Sicurezza, privacy e audit trail](#11-sicurezza-privacy-e-audit-trail)
12. [Stato di avanzamento — implementato vs. da fare](#12-stato-di-avanzamento--implementato-vs-da-fare)
13. [Roadmap tecnica prioritaria](#13-roadmap-tecnica-prioritaria)
14. [Glossario tecnico](#14-glossario-tecnico)
15. [Riferimenti legali e contatti](#15-riferimenti-legali-e-contatti)

---

## 1. VISIONE ORIGINALE DEL PROGETTO

### 1.1 L'idea

THANATOS INTEL nasce dalla necessità di **digitalizzare completamente il ciclo operativo di un'agenzia investigativa privata professionale** che opera in ambito europeo (Italia e Romania principalmente) su tre filoni principali:

1. **Investigazioni tradizionali** (persone fisiche e giuridiche, frodi, infedeltà coniugale, recupero crediti, background check)
2. **Due Diligence Diplomatica (DDD)** — verifica di eleggibilità per pratiche di cittadinanza, passaporti diplomatici e visti speciali, con produzione di dossier certificati per le autorità competenti
3. **Intelligence su minacce digitali e finanziarie** — OSINT, analisi cyber, crypto-fraud, corporate intelligence

Il problema che il sistema risolve è la **frammentazione operativa**: prima di THANATOS INTEL, un'agenzia investigativa usava strumenti separati per gestire i casi (fogli Excel), raccogliere prove (email e cloud generici), fare screening sanzioni (consultazione manuale di siti OFAC/ONU), fatturare (software contabile separato), comunicare con i clienti (WhatsApp personale). Ogni strumento non parlava con gli altri.

### 1.2 La proposta di valore

**"Un unico sistema che va dal primo contatto con il cliente alla consegna del report certificato, con tracciabilità completa, screening sanzioni integrato, firma digitale dei mandati e fatturazione automatica."**

Più specificamente:
- Il cliente apre il portale, crea la richiesta, carica i documenti
- Il sistema verifica automaticamente l'identità, fa lo screening sanzioni, genera il mandato da firmare digitalmente
- L'investigatore vede in real-time su quale step è ogni caso e cosa deve fare
- Il sistema notifica automaticamente (WhatsApp, email) cliente e operatori a ogni step
- Al termine, il report viene consegnato firmato digitalmente con catena di custodia forense
- La fattura viene emessa automaticamente, in formato e-fattura EU, con calcolo del cambio RON/EUR

### 1.3 Destinatari

| Segmento | Caso d'uso principale |
|----------|----------------------|
| Agenzie investigative private (IT/RO) | Gestione completa portafoglio casi |
| Studi legali con necessità di DD | Due diligence su controparti |
| Aziende con risk compliance | KYB/AML su partner e fornitori |
| Intermediari diplomatici | Pratiche cittadinanza/passaporti |
| Privati con esigenze investigative | Background check, verifica frodi |
| Affiliati e collaboratori | Portale per segnalazioni e commissioni |

### 1.4 Modello di business

- **SaaS subscription** (mensile/annuale) per accesso alla piattaforma
- **Pay-per-use** per servizi a consumo (interrogazione blacklist, OSINT job, verifica passaporto)
- **Revenue sharing** per affiliati che portano clienti (calcolato automaticamente dal sistema)
- **B2B white-label** per agenzie partner che vogliono la propria istanza brandizzata

---

## 2. DENOMINAZIONE E MARCHIO

### 2.1 Nome

**THANATOS INTEL** (marchio denominativo)

Il nome deriva da **Thanatos** (Θάνατος), figura mitologica greca della morte serena e inevitabile. Nel contesto investigativo evoca la certezza del risultato: ogni verifica porta a una risposta definitiva. **INTEL** richiama la tradizione del termine nel settore dell'intelligence operativa.

### 2.2 Marchio figurativo

- Simbolo: immagine stilizzata che evoca precisione e analisi  
- Palette: blu scuro `#0A0E1A` / `#0D1B3E` (navy) + oro `#C8A96E`  
- Tipografia: Georgia serif (denominazioni) + system sans-serif (UI)  
- Asset: `thanatos-logo-mark.png` · `thanatos-icon-192.png` (favicon)

### 2.3 Classi merceologiche (Classificazione di Nizza)

- **Classe 42** — Software as a Service; piattaforme analisi dati; due diligence digitale; intelligence investigativa; ricerca e sviluppo scientifico nel campo della sicurezza informatica
- **Classe 45** — Servizi investigativi privati; verifica identità; compliance KYC/KYB; due diligence diplomatica; gestione pratiche investigative; servizi legali di supporto
- **Classe 35** — Analisi aziendale e reputazionale; monitoraggio sanzioni internazionali; gestione rischio; elaborazione dati anti-frode; servizi di intelligence commerciale

### 2.4 Domini registrati

- `thanatos.onekeyco.com` — piattaforma principale (produzione)  
- `thanatos.agency` · `www.thanatos.agency` — dominio brandizzato pubblico  
- `docuseal.thanatos.agency` — firma digitale documenti  

---

## 3. ARCHITETTURA GENERALE DEL SISTEMA

### 3.1 Stack tecnologico

| Componente | Tecnologia | Versione |
|------------|------------|---------|
| Framework backend | Frappe | 16.20.x |
| ERP integrato | ERPNext | 16.21.x |
| Runtime Python | Python | 3.14.5 |
| Database | MariaDB | 10.x |
| Cache + Queue | Redis | 7.x |
| Frontend | Vue.js 3 + JavaScript | — |
| Web server | nginx + gunicorn | — |
| Firma digitale | DocuSeal | self-hosted |
| Build/deploy | bench-cli (no Docker) | — |
| PDF generation | ReportLab + WeasyPrint | — |
| OCR pipeline | DeepFace + OpenCV (cv2) | — |

### 3.2 App Frappe installate sul sito

```
thanatos.onekeyco.com
├── frappe           (framework core)
├── erpnext          (ERP: fatture, contabilità, clienti ERP)
├── hrms             (gestione investigatori come dipendenti)
├── crm              (pipeline commerciale pre-vendita)
├── drive            (storage file centralizzato per casi)
├── wiki             (knowledge base procedure operative)
├── payments         (gateway pagamento Stripe)
├── mmos_brand       (customizzazioni globali MMOS: Drive team, billing inter-ERP)
├── frappe_assistant_core (AI assistant nativo, endpoint MCP)
└── thanatos_intel   (app principale — tutti i moduli investigativi)
```

### 3.3 Struttura moduli thanatos_intel

```
thanatos_intel/
├── thanatos_core/          # Nucleo: casi, clienti, prove, report, investigatori
├── thanatos_ddd/           # Due Diligence Diplomatica
├── thanatos_cyber/         # Cyber intelligence: IOC, IP, domini, hash, crypto scam
├── thanatos_corporate/     # Intelligence societaria: company profile, officers, debt
├── thanatos_documents/     # Analisi documentale: OCR, confronto, passaporti
├── thanatos_fraud/         # Motore anti-frode: alert, regole, watchlist
├── thanatos_osint/         # OSINT: entità, relazioni, job di ricerca
├── thanatos_portal/        # Portale clienti: visto, checklist, documenti
├── fraud_engine/           # Blacklist multi-fonte, pattern fraudolenti
├── osint/                  # Engine OSINT (12 provider integrati)
├── billing/                # Fatturazione, crediti, distribuzione proventi
├── pipeline/               # State machine workflow investigativi
├── rules/                  # Motore regole rischio e scoring 0-100
├── integrations/           # Bridge: Drive, Helpdesk, WABA, blacklist_ingest, DocuSeal
├── news/                   # Ingestion RSS + AI digest giornaliero
└── ai/                     # OCR pipeline, providers AI, blueprint assistant
```

---

## 4. INFRASTRUTTURA SERVER E AI

### 4.1 Mappa completa dei server

```
INTERNET
    │
    ├─── Cloudflare CDN/DNS (DDoS protection, SSL, proxy)
    │         thanatos.onekeyco.com → 167.233.35.84
    │         thanatos.agency / www.thanatos.agency → 167.233.35.84
    │         docuseal.thanatos.agency → 89.167.24.194
    │         mail.thanatos.agency → 89.167.53.215
    │
    └─── RETE PRIVATA HETZNER (10.10.0.0/24 — non esposta a Internet)
```

| Server | IP Pubblico | IP Privato | Tipo | DC | Ruolo |
|--------|------------|------------|------|-----|-------|
| **dev** (bench thanatos) | 167.233.35.84 | 10.10.0.6 | cx43 8vCPU/16GB | Nuremberg | **PRODUZIONE THANATOS** — bench-cli, MariaDB, nginx, systemd |
| **mmos-press** | 46.225.51.52 | 10.10.0.10 | cx43 8vCPU/16GB | Nuremberg | Frappe Press control-plane, AI gateway mmos_ai (porta 8800) |
| **ai-mmos-core** | 89.167.24.194 | 10.10.0.4 | cx43 8vCPU/16GB | Helsinki | Docker bench Press (standby), Ollama (LLM locale), DocuSeal |
| **mmos-app** | 46.62.167.83 | 10.10.0.5 | cx33 4vCPU/8GB | Helsinki | Docker bench utenti (TCF, Axionyx, demo), nginx pubblico |
| **wireguard** | 116.203.74.218 | 10.10.0.2 | cx23 2vCPU/4GB | Nuremberg | VPN, MinIO backup, NFS 100GB condiviso |
| **mmos-mail** | 89.167.53.215 | 10.10.0.3 | cx23 2vCPU/4GB | Helsinki | Stalwart mail server (no-replies@thanatos.agency) |

**Totale: 6 server Hetzner — 2 DC (Nuremberg + Helsinki)**

### 4.2 Rete e storage

```
Rete privata Hetzner "MMOS-VPN-hetzner" (id 11928970)
└── Tutti i 6 server connessi su 10.10.0.0/24 (interfaccia enp7s0)
    Traffico server-to-server: interno, non esposto a Internet

Storage NFS condiviso: /mnt/mmos-shared-storage (100GB su wireguard 10.10.0.2)
└── File Drive investigativi
└── Backup temporanei
└── Upload media

StorageBox Hetzner: u609494@u609494.your-storagebox.de (BX21 1TB)
└── Backup offsite DB + files produzione (SSH port 23 / Samba)

MariaDB produzione: 127.0.0.1:3306 su server dev (bench-cli)
Piano futuro: cluster Galera 3 nodi (dev + mmos-press + wireguard come arbitrator)
```

### 4.3 Architettura AI

#### Componenti AI del sistema

```
┌─────────────────────────────────────────────────────┐
│              LIVELLI AI IN THANATOS INTEL            │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. AI GATEWAY MMOS (mmos-press 10.10.0.10:8800)   │
│     ├── Provider attivo: DeepSeek V4 Flash (free)   │
│     ├── Fallback: OpenRouter                        │
│     ├── Memoria persistente: MariaDB session-keyed  │
│     └── Config: mmos_ai_gateway_url + key           │
│                                                     │
│  2. OLLAMA (ai-mmos-core 10.10.0.4:11434)          │
│     ├── Modello news: llama3.1:8b (configurabile)   │
│     ├── Uso: riscrittura news in "voce Thanatos"    │
│     └── Fallback: Claude CLI subprocess             │
│                                                     │
│  3. FRAPPE ASSISTANT CORE (installato su sito)     │
│     ├── server_enabled=1                            │
│     ├── Endpoint MCP: mcp.onekeyco.com             │
│     └── Tool Frappe nativi (CRUD, ricerche)         │
│                                                     │
│  4. CLAUDE AI (Anthropic)                          │
│     ├── Claude Code su mmos-press (admin infra)     │
│     ├── Press Agent (cron ogni 30min health-check)  │
│     └── Claude su dev server (sviluppo)             │
│                                                     │
│  5. OCR PIPELINE (nell'app thanatos_intel)         │
│     ├── DeepFace (face match + liveness)            │
│     ├── OpenCV (fallback haar cascade)              │
│     └── Abstraction layer OCRService               │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### Flusso AI per caso investigativo

```
Documento caricato
    │
    ▼
OCR Pipeline (DeepFace/OpenCV)
    ├── Estrazione campi (nome, data nascita, MRZ)
    ├── Confronto fotografia passaporto / selfie
    ├── Liveness check (3 frame video)
    └── Risk flags: mrz_checksum_invalid, photo_mismatch, liveness_failed
    │
    ▼
AI Gateway (mmos_ai)
    ├── Analisi sommario caso
    ├── Suggerimento prossimi step
    └── Risposta a domande operatore/cliente
    │
    ▼
News AI Digest (Ollama/Claude)
    ├── Riscrittura notizie in "voce Thanatos"
    ├── Digest giornaliero casi attivi
    └── Alert su soggetti monitorati
```

#### Configurazione site_config (chiavi AI)

```json
{
  "mmos_ai_gateway_url": "http://10.10.0.10:8800",
  "mmos_ai_gateway_key": "...",
  "ai_provider": "mmos_gateway",
  "ollama_host": "http://10.10.0.4:11434",
  "ollama_news_model": "llama3.1:8b"
}
```

### 4.4 Agente di sorveglianza Press (Claude autonomo)

Un'istanza Claude headless gira come cron ogni 30 minuti su mmos-press:
- Analizza snapshot read-only di tutto il control-plane Press
- Applica rimedi idempotenti allowlistati (deliver-jobs, fix-server-team, restart-workers, unblock-redis, prune-disk)
- **NON** può eseguire comandi arbitrari — è vincolato a `/root/press_remediate.sh`
- Log: `/var/log/mmos/press-agent.log`

### 4.5 Deployment Thanatos (bench-cli, no Docker)

```
Server dev (167.233.35.84)
└── /home/frappe/bench-cli/
    └── benches/
        └── thanatos/                    ← bench produzione
            ├── apps/
            │   ├── frappe/
            │   ├── erpnext/
            │   ├── thanatos_intel/      ← repo github michelemilazzo/thanatos_intel
            │   └── ... (altri 8 app)
            ├── sites/
            │   └── thanatos.onekeyco.com/
            │       ├── site_config.json
            │       └── private/backups/
            └── env/ (Python 3.14 venv uv)

Servizi: systemd --user (utente frappe)
  dev-web:8000, dev-socketio:9000, dev-worker_pool, dev-redis:13000
nginx: /etc/nginx/conf.d/ (reverse proxy + SSL Let's Encrypt)
```

---

## 5. MODULI FUNZIONALI — DETTAGLIO

### 5.1 thanatos_core — Nucleo investigativo

**DocType principali:**

| DocType | Descrizione |
|---------|-------------|
| `Investigation Case` | Caso investigativo: numero, titolo, tipo, cliente, investigatore, stato, priorità, cartella Drive |
| `Investigation Client` | Cliente: persona fisica o giuridica, credito servizi, KYC status, ERP customer ID |
| `Investigation Evidence` | Prova: titolo, tipo, file allegato, data acquisizione, catena di custodia |
| `Investigation Report` | Report finale: PDF certificato, firma, stato pubblicazione, link Download |
| `Investigation Entity` | Soggetto investigato: persona/azienda con risk score e link a casi |
| `Investigator` | Profilo investigatore: specializzazioni, tipo (Employee/Contractor), disponibilità |
| `KYC Check` | Verifica identità persona fisica: documenti, risultato, score |
| `KYB Check` | Verifica identità aziendale: visura, beneficiari, risultato |
| `Risk Score` | Score 0-100 per entità: livello (low/medium/high/critical/blocked), flag attivi |
| `Chain Of Custody Event` | Evento catena di custodia: chi, quando, cosa, hash file |
| `News Article` | Articolo news: fonte, categoria, estratto AI, body HTML |
| `Case Type` | Tipo caso con `pipeline_key` che determina il flusso investigativo |

### 5.2 thanatos_ddd — Due Diligence Diplomatica

**DocType principali:**

| DocType | Descrizione |
|---------|-------------|
| `Diplomatic Eligibility Case` | Pratica DDD principale: richiedente, passaporto, status, step |
| `Applicant Profile` | Profilo richiedente: dati anagrafici, passaporti multipli, nazionalità |
| `Agency Mandate` | Mandato d'incarico: firmato digitalmente via DocuSeal, IBAN emittente |
| `Diplomatic Proforma` | Preventivo DDD: importo EUR + calcolo RON BNR |
| `Sanctions Screening` | Risultato screening: tipo (Sanctions/PEP), fonte, outcome, payload |
| `Video Verification Session` | Sessione video-verifica: file recording, esito liveness |
| `Final Dossier` | Dossier finale: documenti allegati, firma, hash integrità |
| `Legal Opinion` | Parere legale allegato alla pratica |
| `Country Framework` | Framework normativo per paese: requisiti, documenti, validità |
| `Diplomatic Audit Log` | Log immutabile eventi DDD: chi, quando, cosa |
| `Authority Submission` | Invio documentazione all'autorità competente |

**Funzionalità speciali:**
- `facecheck.py` — Face match DeepFace/OpenCV + liveness check da video
- `signature.py` — Firma elettronica eIDAS SES su canvas HTML5 con re-stamp PDF
- `screening.py` — Screening OpenSanctions API + fallback cache locale offline
- `opensanctions_sync.py` — Cache locale in `tabOpenSanctions Cache` (aggiornata daily)
- `translation.py` — Traduzione documenti per autorità straniere
- `pdf/mandate.py` — Generazione PDF mandato con ReportLab (logo, IBAN, firma)

### 5.3 thanatos_cyber — Cyber Intelligence

| DocType | Descrizione |
|---------|-------------|
| `IOC` | Indicator of Compromise: hash, IP, dominio, URL |
| `IP Reputation` | Reputazione IP: score AbuseIPDB, geoloc, ASN |
| `Domain Intel` | Intelligence dominio: RDAP, DNS history, subdomini |
| `Hash Reputation` | Reputazione file: VirusTotal, malware families |
| `URL Scan` | Scansione URL: urlscan.io result, screenshot |
| `Crypto Scam Intelligence` | Intelligence crypto fraud: wallet, pattern EN590 |
| `File Sample` | Campione file malware: hash, classificazione |

**Integrazione Chainalysis:** `chainalysis_ingest.py` per analisi wallet crypto e tracciamento transazioni sospette.

### 5.4 thanatos_corporate — Corporate Intelligence

| DocType | Descrizione |
|---------|-------------|
| `Company Profile` | Profilo aziendale: ragione sociale, sede, LEI, stato |
| `Company Officer` | Ufficiale aziendale: ruolo, nazionalità, PEP check |
| `Corporate Link` | Relazione tra aziende: controllo, partecipazione |
| `Financial Snapshot` | Snapshot finanziario: revenue, debiti, rating |
| `Debt Exposure` | Esposizione debitoria: creditori, importi |
| `Due Diligence Report` | Report DD aziendale: score, flag, raccomandazione |

### 5.5 thanatos_documents — Analisi Documentale

| DocType | Descrizione |
|---------|-------------|
| `Passport Analysis` | Analisi passaporto: OCR campi, MRZ check, foto |
| `Document Intake` | Acquisizione documento: tipo, file, canale ricezione |
| `Document Check` | Verifica autenticità: elementi di sicurezza, esito |
| `Document Comparison` | Confronto tra documenti: differenze, anomalie |
| `Document Metadata` | Metadati estratti: EXIF, hash, timestamp |
| `Document Verdict` | Verdetto finale: autentico/sospetto/falso + evidenza |

**OCR Pipeline Blueprint:**
```
Input: Passport / ID Card / Residence Permit / Marriage Cert / Financial Docs
Step 1: Upload documento
Step 2: Estrazione campi OCR (nome, cognome, data nascita, MRZ, numero)
Step 3: Validazione campi (checksum MRZ, coerenza date)
Step 4: Rilevamento campi mancanti
Step 5: Risk checks (mrz_invalid, near_expiry, country_mismatch)
Step 6: Archiviazione campi estratti nel caso
Step 7: Notifica operatore con risultato
```

### 5.6 thanatos_fraud — Motore Anti-frode

| DocType | Descrizione |
|---------|-------------|
| `Risk Rule` | Regola rischio custom: `selector_expression` (Python eval ristretto) |
| `Fraud Alert` | Alert generato: entità, regola scattata, severity |
| `Watchlist Entry` | Lista di sorveglianza interna (pre-blacklist) |

**scorer.py:** valuta entità contro tutte le Risk Rule attive, aggiorna `Entity.risk_score`, crea `Fraud Alert` per match Critical/High. Le regole usano un namespace Python sicuro (`SAFE_BUILTINS`) per eval controllato.

### 5.7 fraud_engine — Blacklist Multi-fonte

| DocType | Descrizione |
|---------|-------------|
| `Blacklist Entry` | Voce blacklist: tipo (Email/IP/Person/Company/IBAN/Wallet), valore, source, external_id, source_url |
| `Blacklist Report` | Segnalazione blacklist da comunità: verifica operatore, bonus 2€ se approvata |
| `Fraud Pattern` | Pattern fraudolenti codificati (es. EN590 advance-fee) |

**blacklist_ingest.py — Fonti aggiornate giornalmente:**

| Fonte | Dataset | External ID |
|-------|---------|------------|
| US Treasury OFAC | SDN Enhanced XML | `OFAC:{uid}` |
| OpenSanctions (EU FSF) | EU Financial Sanctions | `EU:{id}` |
| UN Security Council | Consolidated Sanctions | `UN:{dataid}` |
| OpenSanctions (Interpol) | Red Notices | `OPENSANCTIONS:{id}` |
| OpenSanctions cache | Tutti i dataset | `OS:{id}` |
| AbuseIPDB (reattivo) | IP reputation | `ABUSEIP:{ip}` |
| HIBP (reattivo) | Email breaches | `HIBP:{email}` |

**Blacklist attuale (9 giugno 2026): 31.852 voci attive**

| Fonte | Voci |
|-------|------|
| OFAC SDN Enhanced | 19.023 |
| OpenSanctions / Interpol | 5.934 |
| EU Sanctions (FSF) | 5.890 |
| UN Consolidated | 1.002 |
| Internal | 3 |
| **Totale** | **31.852** |

### 5.8 osint/engine.py — OSINT Engine (12 Provider)

| Provider | Tipo dato | Key richiesta |
|----------|-----------|--------------|
| HIBP | Email breach | Sì (a pagamento) |
| AbuseIPDB | IP reputation | Sì (free 1000/day) |
| RDAP (rdap.org) | WHOIS domini/IP | No |
| OpenCorporates | Aziende globali | Opzionale |
| SecurityTrails | DNS history | Sì |
| IPinfo | Geoloc IP, ASN | Sì (free tier) |
| VirusTotal v3 | Hash/URL/IP/dominio | Sì |
| URLScan.io | Scansione URL | Sì |
| Shodan | Esposizione host | Sì |
| Censys | Asset internet | Sì |
| GLEIF | LEI aziendale | No |
| GDELT | Adverse media | No |

**Nuovi lookup (giugno 2026):**
- `lookup_person(name, dob, nationality)` — OpenSanctions + ICIJ cache + GDELT + blacklist → risk summary
- `lookup_company_full(name, country)` — OpenCorporates + GLEIF + ICIJ + GDELT + blacklist → risk summary

### 5.9 pipeline/pipeline.py — State Machine Adattiva

**Pipeline per tipo caso:**

| Pipeline Key | Tipo caso | N. Step |
|-------------|-----------|---------|
| `Investigation` | Investigazione standard / Corporate | 10 step |
| `DDD` / `Due Diligence` | Due Diligence Diplomatica | 12 step |
| `OSINT` / `Cyber` | Ricerca OSINT / Cyber intelligence | 8 step |
| `Antifrode` / `Fraud` | Analisi truffa | 9 step |
| `Generic` | Fallback generico | 6 step |

**Step tipo Investigation:**
```
Verifica identità (KYB/KYC) → Mandato d'incarico → Firma mandato →
Preventivo → Pagamento → Raccolta evidenze → OSINT / Lookup →
Analisi antifrode → Verifica blacklist → Report finale
```

**Step tipo DDD:**
```
Verifica identità → Mandato d'incarico → Firma mandato →
Preventivo DDD → Pagamento → Analisi passaporto →
Verifica sanzioni → Raccolta evidenze → OSINT →
Analisi antifrode → Report finale → Pratica chiusa
```

### 5.10 billing/ — Fatturazione e Distribuzione Ricavi

**DocType:**

| DocType | Descrizione |
|---------|-------------|
| `Thanatos Billing Settings` | Config globale: prezzi servizi, bonus community, entità DDD |
| `Investigation Subscription Plan` | Piani abbonamento con quote servizi incluse |
| `Usage Event` | Evento a consumo: tipo servizio, importo, caso |
| `Revenue Distribution` | Distribuzione proventi: investigatore principale, co-inv, affiliati, costi |
| `Revenue Split Line` | Singola riga distribuzione: beneficiario, percentuale, importo |
| `Party Payout` | Liquidazione compenso: beneficiario, importo, stato |
| `Credit Ledger` | Wallet generale: ogni transazione credito/debito per qualsiasi parte |
| `Stripe Event` | Evento webhook Stripe: pagamento, subscription, refund |
| `Stripe Subscription` | Abbonamento Stripe collegato a cliente |
| `Billing Entity` | Entità emittente fattura: ragione sociale, IBAN, P.IVA, legge applicabile |
| `Infrastructure Cost` | Costo infrastruttura allocato a caso (Hetzner, API, ecc.) |
| `Affiliate Application` | Richiesta affiliazione: dati richiedente, commissione applicata |
| `Case Assignment` | Assegnazione investigatore a caso: ruolo, percentuale compenso |

---

## 6. ELEMENTI TECNICI INNOVATIVI (BREVETTABILI)

### 6.1 Pipeline Investigativa Adattiva Senza Stato Persistente

**Problema risolto:** i sistemi di workflow tradizionali (Jira, Monday, Asana, Trello) usano un flag di stato aggiornato manualmente ("spostato da To-Do a In Progress"). Questo crea disallineamento se l'operatore dimentica di aggiornare, se i dati cambiano, se si torna indietro su uno step.

**Soluzione brevettabile:** lo step corrente è **calcolato in real-time** interrogando i dati effettivi del documento (esiste il mandato? è firmato? esiste il pagamento? ecc.). Non esiste un flag "step corrente" nel database — esiste solo la realtà del dato.

```python
# Pseudocodice dell'algoritmo
def get_pipeline(case) -> list[Step]:
    for step in PIPELINE[case.pipeline_key]:
        if step.check_function(case):
            step.status = "done"
        elif step == first_undone:
            step.status = "current"   # ← calcolato, non memorizzato
        else:
            step.status = "pending"
    return steps
```

**Novità rispetto allo stato dell'arte:** nessun sistema investigativo commerciale (Tracfone, I2, Palantir) usa questo approccio senza-stato per la pipeline. La validazione è idempotente e deterministica.

### 6.2 Risk Scoring Investigativo Multi-Dimensionale con Segnali Bloccanti

**24 segnali catalogati** su 7 dimensioni: documento, identità, compliance, finanziario, geopolitico, comportamentale, frode.

**Meccanismo blocking:** i segnali `sanctions_match_confirmed` e `high_risk_pattern_en590` sono **bloccanti** — portano lo score a 100 indipendentemente dagli altri, con blocco automatico del caso. Questo implementa la regola FATF/AML: se c'è un match sanzionato confermato, il caso si blocca sempre, senza possibilità di mitigazione da altri fattori.

### 6.3 Blacklist Multi-Fonte con Fusione Automatica e Auto-Promozione

Descritto in 5.7 e 4.3. Il meccanismo brevettabile è la **promozione automatica**: ogni OSINT lookup che trova un esito negativo (AbuseIPDB ≥25%, HIBP breach, OpenSanctions hit) alimenta automaticamente la blacklist interna senza intervento operativo, con tracciabilità completa della fonte.

### 6.4 Due Diligence Diplomatica End-to-End Digitalizzata

Il flusso completo — dal profilo richiedente alla firma del mandato, dallo screening sanzioni al dossier certificato — in un unico sistema tracciato con catena di custodia forense è una combinazione originale non esistente in nessun prodotto commerciale noto.

### 6.5 Distribuzione Automatizzata Proventi Investigativi Multi-Parte

Il sistema calcola e liquida automaticamente le quote di ogni caso tra: investigatore principale, co-investigatori, affiliato segnalatore, entità di riferimento, e quota costi infrastruttura. Il calcolo avviene al salvataggio di ogni `Revenue Distribution` tramite hook Frappe, con scrittura su `Credit Ledger` di ogni parte.

### 6.6 Firma Elettronica eIDAS con Re-Stamp PDF e Audit Immutabile

La firma avviene su canvas HTML5 (signature_pad.js), viene trasmessa come base64 PNG al backend che ri-stampa il PDF del mandato inserendo: immagine firma, timestamp, IP, User-Agent, hash SHA256 del PDF originale. Il risultato è un PDF firmato con audit trail immutabile — conformità eIDAS SES (Simple Electronic Signature).

---

## 7. INTEGRAZIONI ESTERNE

| Applicazione | Ruolo | Tipo |
|-------------|-------|------|
| **Frappe Drive** | Storage file prove/documenti per caso (cartella auto-creata) | Frappe app stessa istanza |
| **Frappe CRM** | Pipeline commerciale → caso | Frappe app stessa istanza |
| **Frappe Helpdesk** | Ticket supporto linkati a caso | Frappe app stessa istanza |
| **Frappe Insights** | Dashboard KPI (6 query, 3 dashboard) | Frappe app stessa istanza |
| **Frappe Wiki** | Procedure operative (7 pagine) | Frappe app stessa istanza |
| **DocuSeal** | Firma digitale mandati (self-hosted su docuseal.thanatos.agency) | REST API + webhook |
| **Stripe** | Pagamenti online + webhook conferma | API v3 + events |
| **OpenSanctions** | DB sanzioni internazionali (cache locale + API match) | CSV + REST |
| **OFAC / EU / UN / Interpol** | Liste sanzioni ufficiali (aggiornamento giornaliero) | XML/CSV public |
| **WABA** | Notifiche WhatsApp Business (template IT pre-approvati) | Meta Cloud API |
| **mmos_ai gateway** | AI conversazionale + analisi (rete interna) | HTTP interno |
| **Ollama** | LLM locale per news rewrite + AI fallback | HTTP interno |
| **Stalwart Mail** | Email transazionale (no-replies@thanatos.agency) | SMTP/IMAP |
| **ERPNext** (stessa istanza) | Fatture, contabilità, clienti ERP | Frappe ORM diretto |
| **Inter-ERP billing** | Push Purchase Invoice a ERPNext di clienti partner | REST API Frappe |

---

## 8. FLUSSO OPERATIVO COMPLETO

```
CLIENTE                          SISTEMA                         INVESTIGATORE
   │                                │                                   │
   │── Richiesta via portale ──────►│                                   │
   │                          Crea Investigation Case                   │
   │                          Pipeline: step = KYC/KYB                 │
   │◄── Richiesta documenti ────────│── Notifica WhatsApp ─────────────►│
   │                                │                                   │
   │── Upload documenti ───────────►│                                   │
   │                          OCR Pipeline:                             │
   │                          - Estrazione campi passaporto             │
   │                          - MRZ check                               │
   │                          - Face match selfie/doc                   │
   │                          - Risk flags → Risk Score                 │
   │                                │                                   │
   │                          Screening sanzioni (OpenSanctions)        │
   │                          Verifica blacklist multi-fonte            │
   │                                │                                   │
   │                          Pipeline: step = Mandato d'incarico       │
   │◄── Mandato PDF per firma ──────│── Notifica operatore ────────────►│
   │                                │                                   │
   │── Firma digitale (canvas) ────►│                                   │
   │                          Re-stamp PDF + audit log eIDAS            │
   │                                │                                   │
   │                          Pipeline: step = Preventivo               │
   │◄── Proforma/preventivo ────────│                                   │
   │                                │                                   │
   │── Pagamento Stripe ───────────►│                                   │
   │                          Webhook Stripe → conferma                 │
   │                                │── Assegna investigatore ─────────►│
   │                                │                                   │
   │                          Pipeline: step = Raccolta evidenze        │
   │                                │◄── Upload prove + note ───────────│
   │                          Chain of Custody: hash + timestamp        │
   │                                │                                   │
   │                          Pipeline: step = OSINT                    │
   │                                │── lookup_person / lookup_company ►│
   │                          12 provider OSINT                         │
   │                          Auto-promozione blacklist se hit          │
   │                                │                                   │
   │                          Pipeline: step = Analisi antifrode        │
   │                          Risk Rule evaluation                      │
   │                          Fraud Alert se score > 75                 │
   │                                │                                   │
   │                          Pipeline: step = Report finale            │
   │                                │◄── Redazione report ──────────────│
   │                          PDF certificato + firma digitale          │
   │◄── Notifica report pronto ─────│── Notifica WhatsApp ─────────────►│
   │                                │                                   │
   │── Download report PDF ────────►│                                   │
   │                                │                                   │
   │                          Pipeline: CHIUSO                          │
   │                          Fattura automatica (ERPNext)              │
   │                          Revenue Distribution:                     │
   │                          - Investigatore principale: %             │
   │                          - Co-investigatori: %                     │
   │                          - Affiliato segnalatore: %               │
   │◄── Fattura e-invoice ──────────│── Liquidazione compensi ─────────►│
```

---

## 9. BILLING, ENTITÀ LEGALI E DISTRIBUZIONE RICAVI

### 9.1 Entità di fatturazione

| Entità | Tipo | Legge applicabile | Ambito |
|--------|------|------------------|--------|
| **THANATOS INVESTIGAZIONI S.R.L.** | Agenzia principale (RO) | Legge rumena / instanțele București / Legea 329/2003 | Tutti i servizi investigativi standard |
| **ARES INVESTIGAZIONI SRL** | Agenzia affiliata (IT) | Legge italiana / Foro di Roma / art. 134 TULPS | Fatturazione pratiche DDD/passaporti |

**Logica di selezione:** `Thanatos Billing Settings.ddd_billing_entity` = ARES per le DDD, Thanatos per tutto il resto. L'hook `stamp_ddd_billing_entity` assegna automaticamente l'entità corretta al salvataggio del documento.

### 9.2 Valute e contabilità

- **EUR** è la valuta base per tutti i servizi
- **RON** (lei rumeni) è richiesto dall'ANAF per l'agenzia rumena
- Tasso di cambio: **BNR (Banca Nazionale della Romania)** — aggiornato quotidianamente via scheduler
- Campi `*_ron` su Sales Invoice, Quotation, Proforma, Revenue Distribution calcolati automaticamente
- Custom Fields su ERPNext per RON (non nativi ERPNext): `custom_eur_ron_rate`, `custom_ron_ccy`, `custom_net_total_ron`, `custom_grand_total_ron`

### 9.3 e-Fattura EU (integrazione ERPNext)

| Paese | Profilo e-fattura | Standard |
|-------|-----------------|---------|
| Italia | EN 16931 | fatturaPA/SDI |
| Romania | EN 16931 | e-Factura ANAF |
| Germania | XRECHNUNG | XRechnung 3.0 |
| Belgio/NL | EN 16931 | PEPPOL BIS |
| Altri UE | BASIC | UBL 2.1 |

Il profilo viene assegnato automaticamente dall'hook `on_sales_invoice_before_insert` in base al paese della company emittente.

**Blocco attuale:** la seconda Company ERPNext (ARES IT) non è ancora creabile — `fiscal_regime` fantasma in cache + `LinkValidationError` account default. Da risolvere con bonifica multi-company prima del go-live fatturazione ARES.

### 9.4 Wallet e crediti clienti

- Ogni `Investigation Client` ha un `service_credit` (saldo prepagato)
- Crediti guadagnati: segnalazione in `/portal/segnala` → se approvata da operatore → +2€ (cap 20€/mese)
- Crediti spesi: interrogazione blacklist (5€), OSINT job, verifica passaporto (prezzi configurabili)
- Tutto tracciato in `Credit Ledger` (party-generic, supporta clienti, agenti, agenzie)

---

## 10. PORTALE CLIENTI E ACCESSO DIFFERENZIATO

### 10.1 Ruoli e permessi

| Ruolo Frappe | Portale | Desk ERPNext | Casi visibili |
|-------------|---------|-------------|--------------|
| Investigation Client | `/portal` completo | No | Solo propri casi |
| Affiliate | `/portal` (solo casi riferiti) | No | Solo casi segnalati |
| Investigator | `/portal/ops` + `/portal` | Sì (limitato) | Casi assegnati + propri |
| Investigation Manager | Tutto | Sì (completo) | Tutti i casi |
| System Manager | Tutto | Sì (admin) | Tutti |

### 10.2 Pagine portale

| URL | Accesso | Contenuto |
|-----|---------|-----------|
| `/portal` | Tutti gli autenticati | Dashboard: casi, documenti, fatture, azioni in sospeso, accesso rapido |
| `/portal/case/{name}` | Utente con accesso al caso | Timeline, prove, report, ticket supporto |
| `/portal/ops` | Investigator/Manager | Board casi aperti per step pipeline, KPI operativi |
| `/portal/guide` | Tutti | Procedure passo-passo (client e operatori) |
| `/portal/verifica-blacklist` | Client con crediti | Servizio a pagamento: verifica Email/IP/IBAN/Azienda |
| `/portal/segnala` | Client | Segnalazione soggetti → bonus 2€ se approvata |
| `/portal/wallet` | Client | Saldo crediti, movimenti |
| `/news` | Pubblico | News intelligence feed |
| `/news/categoria/{slug}` | Pubblico | Notizie per categoria |

### 10.3 Icone di accesso rapido nel portale

Il portale `/portal` include una sezione "Accesso Rapido" con icone differenziate per ruolo:
- **Tutti:** Dashboard, Guida, Supporto, Procedure
- **Solo client:** I miei Documenti, Fatture, Wallet
- **Solo operatori:** Centro Operativo, Drive, CRM, Helpdesk, Desk, Analytics, Wiki, Risk Score, Nuovo Caso, Mandato DDD, OSINT Lookup

### 10.4 Workspace Desk (investigatori/manager)

Il workspace Thanatos Intel nel Desk ERPNext include:
- 16 shortcut rapide (Centro Operativo, Drive, CRM, Helpdesk, Analytics, Wiki, Risk Score, ecc.)
- Card "Strumenti & App" con link a tutte le app integrate
- 6 query Insights predefinite
- 3 dashboard Insights (Casi, Mandati DDD, Revenue)

---

## 11. SICUREZZA, PRIVACY E AUDIT TRAIL

### 11.1 Controllo accessi granulare

Ogni DocType sensibile ha `permission_query_conditions` e `has_permission` Python custom:
- `Investigation Case`: il client vede solo i propri; l'investigatore solo quelli assegnati; il manager tutti
- `Investigation Client`: ogni cliente vede solo il proprio profilo
- `Investigation Evidence`, `Investigation Report`, `OSINT Job`: stesso pattern basato sul caso padre
- `Risk Score`, `Chain Of Custody Event`: solo full-access (manager/investigatore)

### 11.2 Privacy e data protection

- Nessun dato investigativo va su servizi cloud non approvati
- Il modello AI gira su rete interna privata Hetzner (10.10.0.x)
- Backup: StorageBox Hetzner EU (BX21 1TB, Falkenstein DE), GDPR compliant
- Credenziali API (Stripe, DocuSeal, WABA) solo in `site_config.json` (non versionato)
- Sanificazione dati su ambienti di staging (email/scheduler disabilitati, chiavi azzerate)

### 11.3 Audit trail completo

| Log | Dove | Cosa trancia |
|-----|------|-------------|
| Track changes Frappe | Su ogni DocType (`track_changes: 1`) | Chi ha modificato cosa e quando |
| `Diplomatic Audit Log` | DocType dedicato | Ogni evento DDD con payload |
| `OSINT Lookup` | DocType dedicato | Ogni interrogazione OSINT (quando, chi, su cosa, risultato) |
| `Chain Of Custody Event` | DocType dedicato | Ogni trasferimento/visione prova con hash |
| `Blacklist Entry.last_seen` | Campo nel record | Ogni hit sulla blacklist |
| Press Agent log | `/var/log/mmos/press-agent.log` | Ogni azione autonoma dell'agente |

---

## 12. STATO DI AVANZAMENTO — IMPLEMENTATO VS. DA FARE

### ✅ COMPLETATO

#### Core operativo
- [x] Investigation Case con pipeline adattiva (tutti i tipi)
- [x] Investigation Client con portale clienti completo
- [x] Investigation Evidence con catena di custodia
- [x] Investigation Report con PDF certificato
- [x] KYC Check e KYB Check
- [x] Risk Score engine (24 segnali, 5 livelli, blocking)
- [x] Chain of Custody Event
- [x] Investigator profile con specializzazioni

#### Due Diligence Diplomatica
- [x] Diplomatic Eligibility Case con pipeline DDD 12 step
- [x] Applicant Profile con passaporti multipli
- [x] Agency Mandate con generazione PDF (ReportLab)
- [x] Firma elettronica eIDAS SES su canvas HTML5
- [x] Diplomatic Proforma con calcolo RON/EUR BNR
- [x] Sanctions Screening (OpenSanctions API + cache locale)
- [x] OpenSanctions daily sync (cache locale MariaDB)
- [x] Country Framework
- [x] Diplomatic Audit Log
- [x] Final Dossier
- [x] Billing Entity con legge/foro per paese (IT: ARES, RO: Thanatos)

#### Blacklist e frode
- [x] Blacklist Entry multi-fonte (11.000+ voci)
- [x] Ingest giornaliero: OFAC SDN + EU + UN + Interpol
- [x] Auto-promozione da OSINT lookup (AbuseIPDB, HIBP)
- [x] Fraud Pattern (EN590 advance-fee)
- [x] Risk Rule engine con eval Python controllato
- [x] Fraud Alert automatici
- [x] Portale `/portal/verifica-blacklist` (a pagamento)

#### OSINT
- [x] Engine 12 provider (HIBP, AbuseIPDB, RDAP, OpenCorporates, SecurityTrails, IPinfo, VT, URLScan, Shodan, Censys, GLEIF, GDELT)
- [x] Cache Redis 24h
- [x] Persistenza OSINT Lookup
- [x] lookup_person() e lookup_company_full() multi-fonte
- [x] Risk summary automatico

#### Portale e UX
- [x] Portale clienti completo (`/portal`)
- [x] Centro operativo investigatori (`/portal/ops`)
- [x] Guida step-by-step (`/portal/guide`)
- [x] Navigazione contestuale per ruolo
- [x] Icone accesso rapido differenziate per ruolo
- [x] News feed (`/news`)
- [x] Ticket helpdesk linkati a caso dal portale

#### Billing
- [x] Subscription Plans
- [x] Credit Ledger (wallet universale)
- [x] Revenue Distribution con split automatico
- [x] Party Payout
- [x] Stripe integration (keys + webhook)
- [x] e-Fattura EU profili automatici per paese
- [x] RON accounting (BNR) su tutte le entità finanziarie
- [x] Custom Fields RON su Sales Invoice e Quotation ERPNext

#### Integrazioni
- [x] Frappe Drive: bridge accesso + cartella auto-creata per ogni caso (13 casi backfillati)
- [x] Frappe CRM: hook on_deal_update → caso
- [x] Frappe Helpdesk: ticket linkati a caso (Custom Field)
- [x] Frappe Insights: 6 query + 3 dashboard + chart
- [x] Frappe Wiki: 7 pagine procedure
- [x] WABA: 4 template notifiche WhatsApp
- [x] DocuSeal: 6 template attivi, API key configurata
- [x] mmos_ai gateway: configurato (url + key in site_config)
- [x] Ollama: configurato per news rewrite (10.10.0.4)
- [x] Frappe Assistant Core: server_enabled=1, MCP attivo

#### Workspace e navigazione desk
- [x] Workspace Thanatos Intel con 16 shortcut
- [x] Card "Strumenti & App"
- [x] Investigatori: Lorenzo Marrocu (thanatosinvestig@libero.it) e Michele Milazzo (michele.milazzo@live.com)

#### Infrastruttura
- [x] bench-cli production mode (systemd --user, no Docker)
- [x] nginx + SSL Let's Encrypt (thanatos.onekeyco.com + thanatos.agency)
- [x] StorageBox backup
- [x] Press Agent (Claude autonomo cron 30min)
- [x] Inter-ERP billing (Purchase Invoice push a ERP partner)

---

### ⚠️ PARZIALMENTE COMPLETATO

- [x] **OFAC ingest completo** — 19.023 voci caricate (SDN Enhanced XML 107MB, completato 9 giugno 2026)
- [⚡] **Pipeline fix** — corretto `callable(getattr(...))` invece di `hasattr`, in produzione
- [⚡] **Seconda Company ERPNext (ARES IT)** — blocco regional-setup, richiede bonifica multi-company
- [⚡] **Inter-ERP billing verso clienti** — testato e funzionante sul bench dev, non ancora attivato in produzione su tutti i clienti

---

### ❌ DA IMPLEMENTARE (priorità alta)

#### OCR e verifica documenti
- [ ] **OCR reale passaporti** — il blueprint esiste (`ai/ocr_pipeline_blueprint.md`) e l'abstraction layer OCRService è creata, ma l'integrazione con un provider OCR reale (Tesseract, AWS Textract, Google Vision) non è completata. Attualmente restituisce `runtime_placeholder`.
- [ ] **DeepFace/OpenCV attivi** — `facecheck.py` è scritto con logica DeepFace + fallback OpenCV, ma DeepFace non è installato nel venv produzione (richiede TensorFlow ~1GB). Da decidere: installare su bench o usare provider cloud (AWS Rekognition, Azure Face API).
- [ ] **Video liveness check** — il framework è in `facecheck.py` (SSIM diff su 3 frame), ma l'endpoint di upload video e processing non è esposto via API pubblica.

#### Workflow documenti e firma
- [ ] **DocuSeal webhook** — da configurare via UI DocuSeal admin (`docuseal.thanatos.agency/settings/webhook`) puntando a `https://thanatos.onekeyco.com/api/method/thanatos_intel.integrations.docuseal_webhook.handle`. L'endpoint API DocuSeal per webhook non è disponibile.
- [ ] **Traduzione documenti** — `translation.py` esiste ma non è integrata con un provider di traduzione (DeepL, LibreTranslate self-hosted su dev server).

#### Sanzioni e screening
- [ ] **OpenSanctions completo** — il dataset consolidato (`/datasets/latest/default/`) ha ~1GB. Il sync attuale usa `sanctions` (~200MB). Da decidere se fare il full sync o restare sul subset.
- [ ] **OpenSanctions API key premium** — la free tier ha rate limit. Per screening in produzione intensivo serve account enterprise OpenSanctions.

#### AI e intelligence
- [ ] **AI Assistant investigativo** — il blueprint `assistant_blueprint.md` descrive le capabilities (detect missing docs, suggest next steps, explain country requirements, support operators/clients). Va implementato come frontend chat nel portale e nel desk, usando mmos_ai gateway.
- [ ] **News digest AI per casi** — la funzione `daily_case_digest` in `news/ingestion.py` è schedulata ma non integra l'AI per collegare notizie a soggetti monitorati nei casi aperti.
- [ ] **frappe_ai memoria persistente** — attualmente solo in-session. Da implementare `AI Chat Log` DocType con persistenza tra sessioni.
- [ ] **Embedding semantici** — Ollama `nomic-embed-text` per ricerca semantica nel knowledge base e nei documenti del caso.

#### Crypto e financial intelligence
- [ ] **Chainalysis** — `chainalysis_ingest.py` è un placeholder. Richiede API key Chainalysis (€€€) o alternativa gratuita (blockchain.info per Bitcoin, etherscan per Ethereum).
- [ ] **Crypto Scam Intelligence** — DocType creato, ma nessun feed automatico di wallet sospetti. Possibili fonti gratuite: ScamAlert.io, CryptoScamDB (GitHub).

#### Normativo e compliance
- [ ] **EU e-Invoice Genericode** — importazione XML Genericode per mapping completo UOM (unità di misura) e codici pagamento. Necessario per e-fattura conforme al 100%.
- [ ] **Company ARES ERPNext** — creazione Company italiana (con FatturaPA/SDI) bloccata da bug multi-company. Richiede bonifica.

#### Notifiche
- [ ] **WABA credenziali** — `waba_phone_id` e `waba_token` non ancora inseriti in site_config. Le notifiche WhatsApp sono codificate ma inattive.

#### Infrastruttura
- [ ] **Cluster Galera** — pianificato (3 nodi: dev + mmos-press + wireguard arbitrator) ma non ancora implementato. Prerequisito: verifica PK InnoDB su tutte le tabelle.
- [ ] **LibreTranslate** — è installato su dev server (Docker) ma non integrato con Thanatos.
- [ ] **Prometheus analytics** — configurato il relabeling IP→hostname, cadvisor su mmos-app, ma le query Insights per analytics bench non sono complete.

---

### 💡 ROADMAP FUTURA (priorità media/bassa)

- [ ] **White-label per agenzie partner** — istanza dedicata per agenzia terza con proprio branding
- [ ] **App mobile** — client nativo iOS/Android per clienti (notifiche push native, firma su mobile)
- [ ] **Integrazione registri pubblici IT** — Camera di Commercio (CCIAA) via PEC o API Infocamere
- [ ] **Integrazione ONRC Romania** — Registrul Comerțului rumeno per KYB automatizzato
- [ ] **Face verification cloud** — AWS Rekognition / Azure Face API come provider premium per OCR+liveness
- [ ] **Blockchain per Chain of Custody** — hash delle prove su blockchain pubblica per ammissibilità probatoria massima
- [ ] **Report AI-generated** — draft automatico del report investigativo con AI, da revisionare dall'investigatore
- [ ] **Frappe Lending** — analisi rateizzazione su proprie fatture (NOT erogazione credito, richiede licenza OAM/BNR)
- [ ] **Galera + Read Replicas** — alta disponibilità DB con replica sincrona

---

## 13. ROADMAP TECNICA PRIORITARIA

### Sprint 1 — URGENTE (entro 2 settimane)
```
1. [WABA] Inserire waba_phone_id e waba_token in site_config → notifiche WhatsApp attive
2. [DocuSeal webhook] Configurare via UI docuseal.thanatos.agency/settings
3. [ARES Company] Bonificare multi-company ERPNext → creare Company ARES IT
4. [OFAC] ✅ Ingest completato — 31.852 voci totali attive (OFAC 19k + EU 5.9k + Interpol 5.9k + UN 1k)
```

### Sprint 2 — IMPORTANTE (entro 1 mese)
```
5. [OCR Passaporto] Integrare Tesseract (gratuito) o Google Vision (free 1000/mese)
   come primo provider reale in OCRService
6. [Face Match] Installare DeepFace + tensorflow nel venv produzione, o configurare
   AWS Rekognition come provider cloud
7. [AI Assistant] Implementare chat AI nel portale e nel desk usando mmos_ai gateway
   - Rilevamento documenti mancanti per il caso corrente
   - Suggerimento prossimo step
   - Risposta a domande procedure per paese
8. [News → Casi] Collegare AI digest giornaliero ai soggetti monitorati nei casi attivi
```

### Sprint 3 — COMPLETAMENTO (entro 2 mesi)
```
9.  [OpenSanctions full] Sync del dataset completo (~1M entità) su storage dedicato
10. [Genericode EU] Import XML per e-fattura 100% conforme
11. [Galera cluster] POC su DB di test prima di migrare produzione
12. [Crypto intelligence] Feed gratuiti wallet sospetti (CryptoScamDB, blockchain explorers)
13. [Traduzione documenti] LibreTranslate self-hosted (già sul dev server)
14. [frappe_ai memoria] DocType AI Chat Log per persistenza conversazioni tra sessioni
```

---

## 14. GLOSSARIO TECNICO

| Termine | Definizione |
|---------|-------------|
| DDD | Due Diligence Diplomatica — verifica eleggibilità per pratiche cittadinanza/passaporto |
| KYC | Know Your Customer — verifica identità persona fisica (documenti, biometria) |
| KYB | Know Your Business — verifica identità aziendale (visura, beneficiari, compliance) |
| AML | Anti-Money Laundering — prevenzione e rilevamento riciclaggio di denaro |
| PEP | Politically Exposed Person — persona con ruolo politico rilevante, soggetta a screening rafforzato |
| OSINT | Open Source Intelligence — intelligence raccolta da fonti aperte e pubbliche |
| IOC | Indicator of Compromise — indicatore tecnico di compromissione cyber |
| MRZ | Machine Readable Zone — zona leggibile automaticamente del passaporto (2 righe codificate) |
| OFAC | Office of Foreign Assets Control — ufficio US Treasury che gestisce le sanzioni americane |
| SDN | Specially Designated Nationals — lista dei sanzionati OFAC |
| LEI | Legal Entity Identifier — identificatore legale univoco aziendale (standard GLEIF) |
| BNR | Banca Națională a României — banca centrale rumena, fonte tasso di cambio RON ufficiale |
| eIDAS | Regolamento EU 910/2014 per l'identità digitale e firma elettronica |
| SES | Simple Electronic Signature — firma elettronica semplice (livello base eIDAS) |
| Chain of Custody | Catena di custodia — documentazione dell'integrità e dei passaggi di mano delle prove |
| Pipeline | Sequenza di step investigativi calcolata dinamicamente dallo stato reale del caso |
| Blacklist Entry | Voce nella lista nera, arricchita da fonti istituzionali internazionali con tracciabilità fonte |
| e-Fattura EU | Fatturazione elettronica strutturata conforme standard europei (EN 16931, XRECHNUNG) |
| bench-cli | CLI Frappe per gestione bench (no Docker), usato in produzione su server dev |
| Frappe | Framework Python open-source per applicazioni web ERP/CRM/SaaS |
| Revenue Distribution | Calcolo automatico quote proventi tra le parti coinvolte in un caso |
| Inter-ERP billing | Push automatico di Purchase Invoice a istanza ERPNext di clienti partner |
| mmos_ai gateway | AI gateway interno MMOS che aggrega provider LLM (DeepSeek, OpenRouter) con memoria persistente |

---

## 15. RIFERIMENTI LEGALI E CONTATTI

**Titolare:**  
OneKeyCo S.r.l.  
Email: info@onekeyco.com  
Web: https://thanatos.onekeyco.com | https://thanatos.agency  

**Repository codice sorgente:**  
https://github.com/michelemilazzo/thanatos_intel (privato)  
Branch: `main` (produzione)  

**Versione documentata:**  
v0.1.0 — commit `8e0cccd` · branch `main` · 9 giugno 2026  
~11.000+ voci blacklist · 14 moduli funzionali · 65+ DocType · 12 provider OSINT  

**Per deposito marchio UIBM/EUIPO:**
- Classi: 42, 45, 35
- Marchio denominativo: THANATOS INTEL
- Marchio figurativo: logo navy/oro con simbolo stilizzato
- Costo orientativo: UIBM €101 (online) | EUIPO €850 (3 classi, UE)

**Per deposito brevetto:**
- Ufficio: UIBM (Italia) / EPO (Europa)
- Tipologia: Brevetto per invenzione industriale (D.Lgs. 30/2005, artt. 45 ss.)
- Elementi brevettabili identificati: §6.1 Pipeline adattiva, §6.2 Risk scoring bloccante, §6.3 Blacklist auto-fusione, §6.4 DDD end-to-end, §6.5 Revenue distribution multi-parte
- Prerequisito: ricerca anteriorità (consigliata prima del deposito)

---

*Documento riservato. La divulgazione non autorizzata costituisce violazione del segreto industriale ai sensi dell'art. 98 del Codice della Proprietà Industriale (D.Lgs. 30/2005) e dell'art. 39 TRIPs.*

*Ultima modifica: 9 giugno 2026 — Versione 2.0*
