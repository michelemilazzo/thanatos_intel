# 🧪 QA Test Results — Wallet Recovery Backend

**Data**: 2026-07-06
**Ambiente**: dev — `thanatos.onekeyco.com` (bench-cli `benches/thanatos`, branch `main`)
**Metodo**: test funzionale E2E reale contro il sito live (non solo status HTTP)
**Commit fix**: `3f47573`

---

## Esito sintetico

| Area | Esito |
|------|-------|
| Import moduli backend (`recovery_api`, `vault_manager`, `cli`) | ✅ PASS |
| DocType `Wallet Recovery Job` presente nel DB (custom, module Thanatos Core) | ✅ PASS |
| `create_recovery_job` / `create_recovery_batch` | ✅ PASS |
| Upload seed cifrato (RSA-OAEP) → vault | ✅ PASS |
| `generate_cli_command` (wallet-type + private-key) | ✅ PASS (dopo fix) |
| `upload_recovery_result` + download link + HMAC token | ✅ PASS (dopo fix) |
| Endpoint download HTTP live (`get_recovery_result`) | ✅ PASS — 403 "Invalid or expired token" (route OK, non 404) |
| CLI offline: RSA-decrypt input + Fernet result ri-decifrabile | ✅ PASS (dopo fix) |
| Scheduler cleanup TTL agganciato (`daily`) | ✅ PASS (prima non girava) |

---

## 🐛 Bug tracciati e risolti

### BUG-1 — `--wallet-type` invalido nel comando CLI (Alta)
- **Sintomo**: `generate_cli_command` emetteva `--wallet-type bip39-seed`
  (`"BIP39 Seed".lower().replace(' ','-')`), ma il CLI accetta solo
  `bip39`/`electrum`/`bip38` (argparse `choices`). Il comando sarebbe fallito subito.
- **Fix**: `WALLET_TYPE_CLI_MAP` esplicita + `frappe.throw` per tipi non supportati.
- **Verifica**: comando generato ora `--wallet-type bip39`. ✅

### BUG-2 — Download link 404 (Alta)
- **Sintomo**: link puntava a `thanatos_intel.api.recovery_api.get_recovery_result`
  (modulo inesistente) → 404, seed non scaricabile dal cliente.
- **Fix**: path corretto `thanatos_intel.thanatos_recovery.api.recovery_api.get_recovery_result`.
- **Verifica**: HTTP GET reale → 403 con "Invalid or expired token" (route risolve). ✅

### BUG-3 — CLI: risultato indecifrabile (Critica)
- **Sintomo**: `FERNET_KEY = Fernet.generate_key()` a livello modulo, rigenerata e
  scartata a ogni esecuzione → il `seed_output.enc` non era decifrabile da NESSUNO.
  Inoltre `decrypt_input` leggeva plaintext invece di decifrare l'RSA del vault.
- **Fix**:
  - `decrypt_input(input_file, private_key_path)`: RSA-OAEP con la private key del vault.
  - `encrypt_result`: genera la chiave Fernet e la **persiste** in `<output>.key` (0600),
    consegnabile al cliente su canale separato.
  - Nuovo argomento CLI `--private-key`; il comando generato lo include.
- **Verifica**: roundtrip completo — client cifra con public key → CLI decripta con
  private key → CLI cifra il seed completo → client decifra con `.key`. Tutto match. ✅

### BUG-4 — Secret HMAC hardcoded a import-time (Media, sicurezza)
- **Sintomo**: `VAULT_SECRET_KEY = frappe.local.conf.get(..., "dev-secret-12345")`
  valutato all'import, con fallback prevedibile → possibile forgiare token di download.
- **Fix**: `_get_vault_secret()` → `site_config.wallet_recovery_secret_key` oppure
  secret casuale a 32 byte persistito una tantum in `keys/hmac_secret.key` (0600).
- **Verifica**: token generati/validati correttamente col nuovo secret. ✅

### BUG-5 — Cleanup TTL mai eseguito (Media)
- **Sintomo**: `cleanup_expired_recoveries` esisteva ma non era in nessun
  `scheduler_events` dell'app → i vault scaduti non venivano mai rimossi.
- **Fix**: aggiunto a `scheduler_events['daily']` in `hooks.py`.

---

## 🆕 Fase 3 — Batch multi-job (implementato)

- Nuovo endpoint `create_recovery_batch(case_id, jobs)`: crea N job nello stesso caso
  in un'unica chiamata (più wallet/seed per cliente).
- `create_recovery_job` esteso con `wallet_type` / `missing_words_count` / `wordlist_type`.
- **Verifica**: batch di 2 job creati (`WRJ-00001`, `WRJ-00002`) e processati. ✅

---

## ⚠️ Regressione introdotta e corretta durante il lavoro

Il primo deploy di `hooks.py` (partito da un checkout più vecchio) aveva rimosso la
riga scheduler `osint.official_documents.docuengine_poll_pending`. Rilevata a diff,
**ripristinata** prima del commit; worker riavviati con la versione corretta.

---

## ⏭️ Deferiti (non implementati in questo giro)

- **Real BTCRecover su recovery machine**: richiede la macchina air-gapped fisica con
  `btcrecover` + wordlist installati. Il wrapper è pronto e il roundtrip crypto è
  provato; manca solo l'esecuzione sul ferro offline.
- **Ledger Hardware Wallet**: mappato a `bip39` (derivazione + passphrase); il supporto
  device fisico (conferma on-device) è feature a sé, non incluso.
- **Frontend browser encryption**: la cifratura RSA lato browser vive nel Vue widget;
  il form desk (`wallet_recovery_form.js`) è glue amministrativa e per l'upload result
  usa ancora un placeholder — va completato con la cifratura reale lato client.
- **Production security audit**: pen-test formale del flusso end-to-end deployato.
