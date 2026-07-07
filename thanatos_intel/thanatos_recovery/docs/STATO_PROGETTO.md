# 🗺️ Wallet Recovery — Stato del progetto (punto di verità)

**Ultimo aggiornamento**: 2026-07-06
**Dove vive**: `thanatos_intel`, modulo `thanatos_recovery/` — checkout **bench** su dev
`/home/frappe/bench-cli/benches/thanatos/apps/thanatos_intel` (branch `main`)
⚠️ NON editare `shared-apps/thanatos_intel@main` (è più vecchio, non è quello che gira)

**Cos'è**: recupero seed wallet persi/parziali (BIP39/Electrum/BIP38) in modo sicuro e offline.
**Modello**: browser cifra RSA → vault → staff esegue CLI OFFLINE (btcrecover) → risultato Fernet → cliente scarica con link a scadenza.

---

## 📦 I 6 pezzi (e dove sono)

| # | Pezzo | File | Stato |
|---|-------|------|-------|
| 1 | **DocType** `Wallet Recovery Job` | `thanatos_recovery/doctype/wallet_recovery_job/` (custom:1, vive nel DB) | ✅ Funziona |
| 2 | **API backend** (7 endpoint) | `thanatos_recovery/api/recovery_api.py` | ✅ Testato E2E |
| 3 | **Vault** (RSA keys, cifratura, TTL cleanup) | `thanatos_recovery/api/vault_manager.py` + `/mnt/thanatos-box/recovery-vault/` | ✅ Funziona |
| 4 | **CLI offline** `thanatos-recovery-cli` (usa `seedrecover.py`) | `thanatos_recovery/api/thanatos_recovery_cli.py` | ✅ Recupero reale provato (BIP39 + Ledger passphrase) |
| 5 | **Form desk** (cifratura RSA browser) | `public/js/wallet_recovery_form.js` | ✅ Testato roundtrip |
| 6 | **Scheduler** cleanup TTL 48h | `hooks.py` → `scheduler_events['daily']` | ✅ Agganciato |

**Doc**: `thanatos_recovery/docs/` → STAFF_ONBOARDING_GUIDE, MANUAL_QA_TEST_PLAN, QA_TEST_RESULTS, questo file.

---

## 🔄 Il flusso (7 passi)

1. Staff apre un Investigation Case → bottone **Wallet Recovery** (Tools)
2. Inserisce wallet type + **seed guess a lunghezza piena** + **indirizzo noto** (obbligatorio!) + eventuale passphrase Ledger → **il browser cifra RSA-4096** il seed, sale solo il ciphertext
3. Job creato (`WRJ-00001`…), stato `Uploaded`
4. Staff clicca **Generate Command** → comando CLI con `--private-key --known-address` (+ `--passphrase-list` se Ledger)
5. Copia la private key + comando su **macchina air-gapped**, esegue `thanatos-recovery-cli` (btcrecover)
6. Il CLI produce `seed_output.enc` + `seed_output.enc.key` (Fernet) → staff carica il `.enc`
7. Link di download HMAC (48h) → condiviso al cliente; la `.key` va su **canale separato**

---

## ✅ FATTO (testato con prove reali)

- DocType nel DB + naming `WRJ-NNNNN`
- 7 endpoint API, tutti importano e rispondono
- Creazione job singola **e batch multi-job** (`create_recovery_batch`)
- Cifratura RSA lato browser (WebCrypto) ↔ decifratura CLI Python: **roundtrip provato**
- CLI: RSA-decrypt input + Fernet result con **chiave persistita** (ri-decifrabile dal cliente)
- **btcrecover REALE (seedrecover 1.13)**: recupero di una parola sbagliata validato sull'indirizzo → `Seed found` ✅
- **Ledger / passphrase**: passphrase persa recuperata da lista candidati validando sull'indirizzo derivato ✅
- **CLI E2E completo reale**: guess cifrato RSA → decifra → seedrecover → Fernet → decifra al seed corretto ✅
- Download endpoint live (403 su token errato = route OK)
- Secret HMAC persistente (no più hardcoded)
- Cleanup TTL nello scheduler daily
- Bug trovati e risolti: 5 + motore CLI riscritto (vedi QA_TEST_RESULTS.md)

**Commit**: `3f47573` (fix backend + batch) · `92338dd` (doc) · `ff0d5b8` (RSA browser) · `f1430e6` (seedrecover reale + Ledger)

---

## ⏳ MANCA (solo hardening produzione, niente codice bloccante)

| Cosa | Stato | Serve |
|------|-------|-------|
| **Recovery machine di produzione** | ✅ **Bundle offline pronto e provato** (install `--no-index` + self-test PASS). Tarball 39M in box storage `/mnt/thanatos-box/recovery-bundle/`. Sorgenti in `thanatos_recovery/recovery_machine/` | Solo l'azione fisica: copiare il bundle via USB su un laptop, scollegarlo dalla rete, `./install-offline.sh` + `./selftest.sh` |
| **Security audit / pen-test** | ⏳ da fare sul flusso deployato | slot di test dedicato |
| **Staff training reale** | ⏳ guida pronta, manca la sessione | organizzare sessione + firma |

**Bundle recovery machine** (`recovery_machine/`): `install-offline.sh` (venv + wheel, zero rete), `selftest.py/.sh` (recupero di prova con vettore noto → certifica), `RUNBOOK.md` (procedura air-gap/chiave/wipe), `build-bundle.sh` (rigenera il tarball). Il tarball binario (btcrecover + wheelhouse) NON è in git: sta in box storage.

> ⚠️ **Requisito chiave emerso dal test reale**: il recupero è impossibile senza un **indirizzo noto** del wallet (o xpub). seedrecover valida i candidati derivando gli indirizzi e confrontandoli: senza target, qualsiasi seed con checksum valido sembrerebbe corretto. Il campo `known_address` è ora obbligatorio.

---

## ⚠️ 2 cose da sapere (gotcha)

1. **Due checkout su dev**: edita SEMPRE quello del bench (`benches/thanatos/apps/`), non `shared-apps` (stale). Verifica con `python -c "import thanatos_intel, os; print(os.path.dirname(thanatos_intel.__file__))"`.
2. **`git commit` sul bench prende tutto l'index**: il 2026-07-06 il commit `ff0d5b8` ha inglobato 6 rename portale già staged da un altro processo (danno funzionale: nessuno, erano già su disco). Su questo repo: `git add <file specifici>` + controllare `git diff --cached` prima di committare.

---

## 🔗 Link verifica rapidi

- Desk: `https://thanatos.onekeyco.com/app/investigation-case` → caso → Wallet Recovery
- JS servito: `https://thanatos.onekeyco.com/assets/thanatos_intel/js/wallet_recovery_form.js?v=20260706b`
- Endpoint download: `.../api/method/thanatos_intel.thanatos_recovery.api.recovery_api.get_recovery_result`
- Repo: `github.com/michelemilazzo/thanatos_intel` (branch main)
- Accesso dev: `ssh -i ~/.ssh/external_access root@167.233.35.84`
