# Thanatos Canary Toolkit

Toolkit **difensivo/controinformativo** per Thanatos: token-esca (canary token) e documenti/credenziali
civetta che segnalano al **primo accesso** chi li apre/esfiltra (IP, user-agent, geo, referrer, ora,
device fingerprint, WebRTC). Uso **consensuale e lecito** (indagini su mandato). **NON** è un RAT/spyware:
niente accesso occulto a dispositivi di terzi (reato). Vedi distinzione consenso vs abuso in MMOS Remote.

## Architettura (riuso infra esistente)

```
  operatore (desk Thanatos)                        target
  ┌─────────────────────────┐                 ┌──────────────┐
  │ Canary Token (DocType)  │  genera link →  │ apre link /  │
  │  · ref opaco per caso   │                 │ scarica esca │
  │  · investigation_case   │                 └──────┬───────┘
  └──────────┬──────────────┘                        │ phone-home
             │ PULL */10 + on-demand                  ▼
             │                          ┌─────────────────────────────┐
  ┌──────────▼──────────────┐  __hits   │ Worker Foxglove (CF Pages)  │
  │ Canary Hit (DocType)    │◄──────────│ /l /px /scheda.* /go /pay   │
  │  · IP/geo/asn/fp/webrtc │           │ /__hits  /__hit  /__redir   │
  │  · suspect_net (VPN/DC) │           │ KV HITS (TTL 120g)          │
  └──────────┬──────────────┘           └─────────────────────────────┘
             │ nuovo hit + alert_on         WHOIS = Cloudflare, mai Thanatos
             ▼
  notify._email_operator(case)  → alert per-caso all'operatore assegnato
```

- **Cattura** = worker Foxglove (`foxglove.pages.dev`, install `/root/canary-foxglove` su mmos-client).
  Nessuna nuova infra pubblica, nessuna attribuzione a Thanatos. Vettori già supportati dal worker:
  `/l` (link/redirect-esca), `/px` (pixel img+email), `/scheda.pdf|docx|xlsx` (download office phone-home),
  `/pay` (QR), sottodominio `<ref>.c.thanatos.agency` (DNS token, risolto da `canary-dns.service`).
- **Ingest** = modello **PULL** (`thanatos_cyber.canary.pull_all_hits`, scheduler `*/10 * * * *`) + bottone
  on-demand. Foxglove non chiama mai onekeyco → opsec. Solo i `ref` di token conosciuti vengono
  materializzati; dedup per `hit_key = sha256(ts|ip|type|via|r|path)`.
- **Storage/attribuzione** = `Canary Token` (una campagna/esca, legata a `Investigation Case`) +
  `Canary Hit` (una visita). Modulo **Thanatos Cyber**.
- **Alert** = sui nuovi hit di un token con `alert_on` e pratica collegata → email all'operatore via
  `workflow/notify._email_operator`. (L'email istantanea globale la manda già il worker via `ALERT_URL`.)

## DocType

**Canary Token** — `ref` (opaco 8hex, unique), `label`, `token_type`, `investigation_case`, `case_step`,
`recipient` (per attribuzione fuga), `status`, `redir_url/redir_title`, `alert_on`, `hit_count`,
`last_hit`, `vectors` (JSON link generati), `notes`.

**Canary Hit** — `token`, `investigation_case`, `hit_ts` (UTC), `hit_type`, `via`, `ip`, `suspect_net`,
`country/city`, `asn/org`, `tz`, `fp` (device fingerprint), `webrtc` (IP reali), `ua`, `lat/lon/acc`,
`hit_key` (dedup unique), `raw`.

## API (`thanatos_intel.thanatos_cyber.canary`)

| Metodo | Uso |
|--------|-----|
| `generate(label, token_type, investigation_case, recipient, redir_url, redir_title, notes)` | crea token + ritorna tutti i link |
| `generate_batch(label, recipients, token_type, investigation_case)` | **1 token per destinatario** → attribuzione fuga |
| `set_redirect(ref, url, title, image)` | configura redirect-esca sul worker (`/__redir`) |
| `list_tokens(investigation_case)` | campagne + link ricostruiti |
| `pull_hits(ref)` / `pull_all_hits()` | ingest on-demand / scheduler |
| `hits(ref, investigation_case)` | lista hit |
| `dashboard(investigation_case)` | token + hit recenti + **entity resolution** per fingerprint (cross-caso) |
| `dossier(ref)` | **fascicolo de-anon** per token: IP residenziale vs datacenter/VPN, IP pubblici **WebRTC (VPN-proof)**, fingerprint device (+cross-caso), GPS, timeline, **best-guess IP reale** |
| `disable(ref)` | disattiva token |

## Playbook attribuzione (caso "chi apre l'esca")

1. `generate(label, token_type="Link / Pagina", investigation_case="CASE-…")` → usa il link **`page`** (`/?utm_content=<ref>`): è la homepage del blog che carica `b.js` → **device fingerprint + WebRTC IP-leak**, che de-anonimizzano anche dietro VPN in-browser. (Il `link`=`/l` redirect-esca è più "sembra la pagina vera" ma fa solo beacon base + redirect veloce: meno de-anon.)
2. Manda il link al target col ref opaco nel param `utm_content`. Ogni apertura → push real-time → Canary Hit + alert operatore.
3. `dossier(ref)` → **best_guess_ip** (WebRTC pubblico > IP residenziale > datacenter), correlazione device via fingerprint (stesso device su VPN e IP reale), GPS se concesso, cross-caso. Il WebRTC `srflx` rivela l'IP pubblico reale anche se il target naviga via VPN.
4. Per il **secondo device**: il QR in pagina (b.js) codifica lo stesso URL `+via=qr` → quando lo scansiona col telefono cattura anche quello.

## Casi d'uso → tipo token

- **Rilevare una fuga di dati** → `generate_batch` con un DOCX/XLSX/PDF-esca per ogni destinatario
  (ref distinto per copia). Quando l'esca fa phone-home fuori, `recipient` dice **chi** ha esfiltrato.
- **Attribuire chi apre un'esca** → Link / Redirect-esca + fingerprint/WebRTC (de-anon anche dietro VPN
  via device fingerprint e IP-leak WebRTC; DOCX/XLSX aperti in Office caricano l'immagine esterna).
- **Dispositivo cliente compromesso** → Sottodominio DNS + (fase 2) Credenziale-esca / Endpoint honeypot:
  credenziali finte piazzate sul device che, se un malware le prova contro il nostro honeypot, loggano
  il tentativo.

## Honeypot — device cliente compromesso (credenziale-esca + endpoint)

Route worker: **`/login`** (login NEUTRO, member-area della civetta — nessun brand reale = niente phishing).
POST con username/password → Hit `credential` con `attempt_user`/`attempt_secret` (ciò che l'attaccante ha
provato). **`/api/*`** → Hit `honeypot` (metodo+path + Authorization/token usato). Loggano solo con `ref`
presente (le creds piantate lo portano) → niente rumore da bot.

`planted_creds(ref)` genera credenziali **deterministiche dal ref** (`password = sha256(ref+secret)[:14]`,
ricostruibili senza storage): l'operatore le pianta sul device del cliente (password manager, file config).
Se il device è compromesso e un malware le esfiltra e le **prova**, l'hit viene loggato e attribuito.
UI: nel form "Nuova esca" tipi *Credenziale-esca* / *Endpoint honeypot* → dialog con le creds da piantare;
i tentativi appaiono nel Dossier sotto "⚠ Tentativi credenziali / honeypot".

## Stato

- **Fase 1 (FATTA):** DocType + API + PULL scheduler + ingest PUSH + alert operatore + vettori
  link/pixel/email/PDF/DOCX/XLSX/QR/redirect/DNS.
- **Fase 1b — Attribuzione (FATTA):** vettore `page` (b.js fingerprint+WebRTC), `dossier(ref)` de-anon,
  **Page desk** `/app/thanatos-canary`.
- **Fase 2 — Honeypot (FATTA):** route worker `/login` + `/api/*`, `planted_creds`, campi Hit
  `attempt_user`/`attempt_secret`, UI creds piantate + tentativi nel dossier. Verificato E2E in produzione.
