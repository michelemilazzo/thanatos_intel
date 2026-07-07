# 🔒 RUNBOOK — Recovery Machine Air-Gapped (Thanatos)

Questo bundle trasforma una macchina pulita in **recovery machine offline** per il
recupero seed. Non serve internet dopo l'allestimento. Il seed in chiaro non lascia
mai questa macchina.

**Contenuto del bundle** (nessun segreto incluso):
- `btcrecover/` — motore di recupero (seedrecover.py)
- `wheelhouse/` — tutti i pacchetti Python come wheel (install 100% offline)
- `thanatos-recovery-cli` — il tool wrapper
- `install-offline.sh` · `selftest.sh` · `selftest.py`
- questo RUNBOOK

Target: **Linux x86_64, Python 3.12**.

---

## 1. Allestimento (una tantum)

1. Procurati una macchina dedicata (laptop) con Linux x86_64 e Python 3.12 già installato.
2. Copia questo bundle sulla macchina **via USB** (non via rete).
3. **Scollega la macchina dalla rete** (stacca cavo, disattiva Wi-Fi/Bluetooth).
4. Installa offline:
   ```bash
   cd thanatos-recovery-bundle
   ./install-offline.sh
   ```
5. Certifica che funziona (recupero di prova con vettore noto, offline):
   ```bash
   ./selftest.sh
   ```
   Deve stampare **`SELF-TEST: PASS`**. Se sì, la macchina è pronta.

> La macchina resta **sempre offline** da qui in poi.

---

## 2. Eseguire un recupero (per ogni caso)

Dal portale desk, per il job (`WRJ-…`) prendi con te (via USB):
- `seed_input.enc` (il seed cifrato del cliente)
- il comando generato da **"Generate Command"**
- la **private key del vault** `private.pem` (dal server, `recovery-vault/keys/`)
- l'eventuale `passphrases.txt` (per Ledger)

Poi sulla macchina offline:
```bash
cd thanatos-recovery-bundle
THANATOS_BTCRECOVER_DIR=$PWD/btcrecover \
  venv/bin/python thanatos-recovery-cli \
  --job-id WRJ-00001 \
  --input-file /media/usb/seed_input.enc \
  --private-key /media/usb/private.pem \
  --wallet-type bip39 \
  --known-address bc1q...  \
  --missing-words 1 \
  --wordlist english \
  --output-file /media/usb/seed_output.enc
```
(Il comando esatto lo genera il form — copialo. Per Ledger include `--passphrase-list`.)

Produce due file:
- `seed_output.enc` → riportalo al server e caricalo sul job (diventa il link download)
- `seed_output.enc.key` → la chiave Fernet: **consegnala al cliente su canale
  separato** dal link di download (servono entrambi per decifrare).

---

## 3. Dopo ogni recupero (igiene)

```bash
# cancella la private key del vault e gli output dalla macchina/USB
shred -u /media/usb/private.pem
shred -u /media/usb/seed_input.enc /media/usb/seed_output.enc*
```
- Non riconnettere mai la macchina alla rete con seed/chiavi ancora presenti.
- La private key del vault vive sul server; qui è solo di passaggio, va sempre wipeata.

---

## 4. Rigenerare i wheel (altro target Python/arch)

Se la macchina non è x86_64/Py3.12, su una macchina ONLINE con lo stesso target:
```bash
python3 -m venv build && build/bin/pip install -U pip wheel
build/bin/pip download -d wheelhouse -r btcrecover/requirements.txt cryptography bip_utils
build/bin/pip wheel crcmod -w wheelhouse   # se scaricato come sdist
```
Poi ricopia `wheelhouse/` nel bundle e riparti dal punto 1.

---

## 5. Requisiti di sicurezza (non negoziabili)

- Macchina **sempre offline** durante decrypt/recupero.
- Trasferimenti **solo via USB**, mai in rete.
- La private key del vault e i seed in chiaro **non devono mai** finire in rete.
- Wipe (`shred`) di chiavi e output dopo ogni caso.
- La `.key` del risultato va su canale **diverso** dal link di download.
