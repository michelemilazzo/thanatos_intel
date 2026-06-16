# Motore Pratiche Thanatos — architettura

Definizione del sistema che guida una pratica dall'arrivo del cliente alla
consegna, con: self-service finché possibile, gate operatore quando serve,
tracciabilità completa tra tutti gli attori, identità a livelli (licenza),
archivio cliente persistente, bacheca AI-mediata, notifiche multicanale.

## Principi

1. **Data-driven, non hardcoded.** Una pratica = un *Service Blueprint* (record),
   non codice. Aggiungere una pratica o una figura nuova = creare/editare un
   record, senza deploy.
2. **Self finché non serve un operatore.** Gli step `AUTO` scorrono da soli; al
   primo `GATE` la pratica si ferma e crea un TODO per il ruolo di turno. Appena
   approva, riparte fino al gate successivo.
3. **Tutto tracciato, tutto comunicato.** Ogni transizione scrive in bacheca e
   notifica (email + WhatsApp ora; Telegram/push poi). Audit immutabile = licenza.
4. **L'AI è il concierge del caso.** Pone le domande al cliente, raccoglie/valida
   le risposte, sollecita documenti, riassume all'operatore. Una sola interfaccia
   conversazionale (mmos_ai) per la corrispondenza.

## Modello dati (DocTypes Frappe)

### Nuovi
- **Service Blueprint** — definizione di un tipo di pratica.
  - `service_name`, `category`, `self_serve` (bool), `identity_tier` (minimo
    richiesto: Base / KYC / KYB / KIT), `steps` (child *Blueprint Step*).
- **Blueprint Step** (child) — un passo del template.
  - `idx`, `label`, `actor_role` (link *Case Role*), `mode` (AUTO|GATE),
    `action_type` (form|sign|pay|upload|work|review|deliver|notify|ai_question),
    `output`, `sla_hours`, `client_visible` (bool), `optional` (bool).
- **Case Role** — registro figure ESTENSIBILE (Cliente, Operatore/PM,
  Investigatore, Avvocato, Commercialista, Mediatore, Collaboratore, +future).
  Mappa a un Frappe Role; `can_be_assigned`, `is_client`, `is_internal`.
- **Case Step Instance** (child di Investigation Case) — istanza runtime di uno
  step: `blueprint_step`, `status` (Pending|In Progress|Awaiting Client|Done|
  Skipped|Blocked), `assignee` (User), `role`, `due`, `completed_at`, `note`.
- **Case Assignment** (child di Investigation Case) — chi copre quale ruolo in
  QUESTO caso: `role` (Case Role) → `user`. Permette team per-pratica.
- **Client Vault Item** — archivio documenti del cliente, riusabile tra pratiche:
  `client`, `doc_kind` (KYC|KYB|CIS|KIT|Altro), `file`, `valid_until`, `status`
  (Valido|In verifica|Scaduto), `verified_by`, `verified_on`. "Sempre aggiornato".

### Estesi
- **Investigation Case**: + `blueprint` (link), + `current_step`, +
  `case_steps` (Case Step Instance), + `assignments` (Case Assignment).
  Stati esistenti (`Draft→Open→In Progress→Review→Closed`) restano come stato
  macro; il dettaglio fine vive negli step.

## Identità a livelli (gate licenza)

Ogni pratica dichiara `identity_tier` minimo. Il wizard, prima di aprire, esige
che il *Client Vault* del cliente soddisfi quel tier:
- **Base** — anagrafica + email/telefono verificati. (es. verifiche rapide)
- **KYC** — documento d'identità privato.
- **KYB** — visura/documenti azienda + UBO.
- **KIT** — diligence rafforzata (es. DDD passaporti).
Se manca, il wizard manda prima al completamento identità (riusa onboarding
KYC/KYB esistente) e POI riprende l'apertura pratica. I documenti restano nel
Vault e valgono per le pratiche successive (no re-upload).

## Motore (engine.py)

- `open_case(client, blueprint, payload)` — crea il caso dagli step del
  blueprint, valida l'identity_tier, posiziona `current_step` al primo.
- `advance(case)` — esegue/valuta lo step corrente:
  - `AUTO`: esegue l'azione (genera mandato, emette preventivo, consegna report)
    o attende l'evento esterno (firma, pagamento, upload), poi passa oltre.
  - `GATE`: crea ToDo nativo Frappe per `assignee`/ruolo + notifica, e si ferma.
- Eventi esterni che richiamano `advance`: firma DocuSeal, webhook pagamento
  Stripe, upload evidenza, completamento ToDo operatore, risposta cliente all'AI.
- Ogni transizione → `notify.dispatch(case, event)`.

## Bacheca + AI concierge

- Un thread per pratica (riusa `activity_timeline` + `case_chat`), messaggi con
  `visibility` (client|internal). Note interne struttura nascoste al cliente.
- Step `ai_question` / `Awaiting Client`: il motore pubblica una domanda; l'AI
  (mmos_ai) la pone al cliente in chat, raccoglie la risposta, valida, compila il
  campo del caso e chiama `advance`. L'operatore vede tutto e può intervenire.

## Notifiche (dispatcher unico)

`notify.py` con canali pluggabili, aggrega l'esistente:
- **bacheca** (sempre), **email** (`client_comms`, esiste), **whatsapp**
  (`waba_notifications`, esiste), **telegram** (da aggiungere), **push** (app,
  futuro). Preferenze canali per-cliente.

## Pratiche iniziali (Blueprint)

Stesso motore, step diversi. Pilota: **Indagine** (gate-heavy) + **OSINT**
(self-serve) per validare entrambe le corsie. Poi DDD, Antifrode, Corporate.

Indagine (esempio step):
| # | Step | Ruolo | Modo | Tier |
|---|------|-------|------|------|
| 1 | Apri pratica (wizard) | Cliente | AUTO | KYC/KYB |
| 2 | Triage/accettazione | Operatore | GATE | |
| 3 | Mandato (PDF) | Sistema | AUTO | |
| 4 | Firma mandato | Cliente | AUTO | |
| 5 | Preventivo | Sistema/Op. | AUTO/GATE | |
| 6 | Pagamento | Cliente | AUTO | |
| 7 | Assegna investigatore | Operatore | GATE | |
| 8 | Lavorazione + evidenze | Investigatore | GATE | |
| 9 | Revisione legale (opz.) | Avvocato | GATE | |
| 10 | Consegna report | Sistema | AUTO | |
| 11 | Chiusura + fattura | Sistema/Commercialista | AUTO | |

OSINT: salta 3,4,9 (mandato/firma/legale) se sotto soglia; resta self-serve a
carta (pay-per-use esistente).

## Fasi di build

- **F1 — Fondamenta** : DocTypes nuovi + estensioni + `engine.advance` +
  `notify.dispatch` (aggrega email/whatsapp esistenti) + ToDo nativi. No UI.
- **F2 — Wizard + Bacheca** : pagina portale "Apri pratica" generata dal
  Blueprint + bacheca per-caso (timeline+chat+domande) + viste TODO per ruolo.
- **F3 — Identità tier + Vault** : gate scalare + archivio cliente sempre
  aggiornato (scadenze, re-verifica).
- **F4 — AI concierge + canali** : mmos_ai sulle domande caso + Telegram/push.

Pilota live: Indagine + OSINT end-to-end prima di estendere alle altre.
