# THANATOS AI — Masterplan

> **THANATOS AI è un'etichetta, non un'AI separata.** Il cervello è uno solo: [MMOS AI](https://github.com/michelemilazzo/mmos-ai/blob/main/MMOS_AI_MASTERPLAN.md) (gateway 10.10.0.10:8800, memoria unica MariaDB con namespacing per sito). Sul sito thanatos quel cervello si presenta come **THANATOS AI** — persona con prompt e competenze investigative.
>
> Questo masterplan copre il **braccio investigativo**: i DocType, le pipeline e i tool di dominio dentro `thanatos_intel` che THANATOS AI usa per apprendere dai casi, dagli input degli analisti e dalle fonti OSINT, e produrre ciò che serve a un'indagine (arricchimenti, collegamenti, timeline, report di due diligence). Niente infrastruttura AI duplicata qui: memoria, RAG e motore azioni vivono nel core MMOS AI.

**Regola di tracking:** ogni task completato si spunta `[x]` con data a fianco. Niente task chiuso senza commit relativo.

---

## Stato di partenza (già fatto)

- [x] App `thanatos_intel` con moduli: `osint/` (engine + doctype), `fraud_engine/`, `pipeline/`, `news/` (ingestion attiva), `reporting/`, `billing`
- [x] Blueprint AI esistenti: `ai/assistant_blueprint.md`, `ai/ocr_pipeline_blueprint.md`, `ai/ocr_service.py`, `ai/providers.py`
- [x] Prod live su bench-cli (167.233.35.84), gateway mmos_ai raggiungibile via wireguard
- [x] Scaffold due diligence (`thanatos_due_diligence`) + flusso fatturazione DD (entità ARES)

---

## Fase 1 — Il Caso come unità di conoscenza

Obiettivo: tutto ruota attorno al Caso; ogni input diventa dato strutturato.

- [ ] DocType **Investigation Case**: soggetti, incarico, stato, livello riservatezza, scadenze
- [ ] DocType **Case Evidence**: documento/foto/URL/nota collegata al caso, hash SHA-256 per integrità, catena di custodia (chi/quando/da dove)
- [ ] Ingestione documenti: OCR (completare `ai/ocr_service.py` come pipeline batch), estrazione testo PDF/immagini
- [ ] **Entity extraction** AI su ogni evidenza: persone, aziende, indirizzi, targhe, IBAN, telefoni, email → DocType **Case Entity** con dedup
- [ ] Storage evidenze su NFS condiviso con cifratura at-rest, mai nel repo
- [ ] Permessi per ruolo: analista vede solo i propri casi; audit log accessi

## Fase 2 — OSINT automation

Obiettivo: l'AI arricchisce le entità da fonti aperte senza lavoro manuale.

- [ ] Estendere `osint/engine.py`: registry fonti pluggable (visure, registri imprese, news, social pubblici, leak DB legali, sanzioni/PEP)
- [ ] Job di arricchimento per entità: nuova Case Entity → ricerche automatiche → risultati come Evidence con fonte e timestamp
- [ ] Collegare ingestion `news/` ai casi: match automatico entità↔articoli, alert su nuove menzioni
- [ ] Monitoraggio continuo: watch list per caso, ricontrollo periodico fonti (scheduler)
- [ ] Rate limiting e rispetto ToS per fonte; proxy/configurazione per fonte in DocType **OSINT Source**

## Fase 3 — Analisi e ragionamento

Obiettivo: dall'accumulo dati alle conclusioni investigative.

- [ ] **Grafo entità**: relazioni tra Case Entity (socio di, residente a, transazione con) — DocType Relation + visualizzazione grafo nel desk (vis.js/cytoscape)
- [ ] **Timeline automatica** del caso: eventi datati estratti da evidenze, ordinati e navigabili
- [ ] Scoring `fraud_engine`: regole + AI per indicatori di rischio (incongruenze patrimoniali, prestanome, società schermo) con spiegazione per ogni flag
- [ ] Cross-case search: "questo soggetto è già comparso in un altro caso?" (con barriera permessi)
- [ ] Chat investigativa per caso: domande in linguaggio naturale sul fascicolo (RAG sulle evidenze del caso, via gateway con Claude — mai modelli free per dati sensibili)
- [ ] Suggerimenti proattivi: "manca la visura di X", "l'indirizzo Y compare in due evidenze contrastanti"

## Fase 4 — Memoria investigativa (apprendimento)

Obiettivo: ogni caso chiuso rende il sistema più bravo.

- [ ] Knowledge base metodologica: a caso chiuso, l'AI estrae pattern anonimizzati (tipologia frode → segnali → fonti utili) in DocType **Investigation Pattern**
- [ ] I pattern alimentano `fraud_engine`: nuovi casi vengono confrontati con i pattern noti
- [ ] Feedback analista su ogni suggerimento AI (utile/inutile) → tuning dei prompt e delle regole
- [ ] Metriche: tempo medio per fase di indagine, % suggerimenti accettati, copertura fonti

## Fase 5 — Report e deliverable

Obiettivo: l'AI scrive il grosso del report, l'analista valida.

- [ ] Generatore **report Due Diligence**: template ARES (`thanatos_due_diligence`) compilato dall'AI da evidenze+grafo+timeline, con citazione fonte per ogni affermazione
- [ ] Livelli report: executive summary / standard / completo con allegati
- [ ] Export PDF con letterhead (fix `repeat_header_footer` già noto), reportlab/qrcode (dipendenze da installare — vedi memoria billing)
- [ ] Flusso revisione: bozza AI → review analista → firma → fattura DD automatica (Billing Entity ARES)
- [ ] Watermark e classificazione riservatezza sul PDF

## Fase 6 — Compliance e sicurezza

In parallelo dalla Fase 1 — non negoziabile per il dominio investigativo.

- [ ] Registro trattamenti GDPR: base giuridica per caso, retention policy, cancellazione certificata a fine mandato
- [ ] Audit trail immutabile (accessi, ricerche OSINT, generazioni AI)
- [ ] Isolamento dati: nessun dato di caso esce verso modelli non autorizzati; embedding/RAG solo su infrastruttura propria (Ollama) o provider con DPA
- [ ] Backup cifrati dei casi nel giro StorageBox/MinIO
- [ ] Test di accesso: verificare che un analista non veda casi altrui (test automatici permessi)

---

## Dipendenze tra fasi

Fase 1 sblocca tutto. Fase 2 e 3 procedono in parallelo dopo la 1. Fase 4 richiede 3. Fase 5 richiede 3. Fase 6 parte subito e accompagna ogni fase.

## Convenzioni

- Sviluppo su bench `thanatos` del dev server, deploy via `tools/deploy-thanatos.sh` ([[thanatos-deploy-workflow]]).
- Ogni fase = milestone; ogni task spuntato cita il commit.
- Dati caso = DB + NFS cifrato. Codice = solo Git.
