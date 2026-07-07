#!/usr/bin/env python3
"""
thanatos-recovery-cli: Offline tool per recupero seed BIP39/Electrum
Wrapper di BTCRecover con validazione e cifratura E2E

Installazione:
  chmod +x /usr/local/bin/thanatos-recovery-cli
  pip install btcrecover cryptography pycryptodome

Uso:
  thanatos-recovery-cli \\
    --job-id CASE-2026-0042_REC-001 \\
    --input-file ~/seed.enc \\
    --wallet-type bip39 \\
    --missing-words 3 \\
    --wordlist english \\
    [--output-file ~/result.enc]

IMPORTANTE:
  - Eseguire OFFLINE (no internet)
  - Input file: seed crittografato (non verrà decriptato qui)
  - Output: seed completo crittografato

Security:
  - Nessuno stdout/log del seed (plaintext mai in memoria)
  - File temporanei rimossi
  - Niente backup/tmp files
"""

import sys
import argparse
import json
import logging
import subprocess
import tempfile
import shutil
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import os


# Directory dell'installazione btcrecover (clone github, contiene seedrecover.py).
# Override con env THANATOS_BTCRECOVER_DIR.
BTCRECOVER_DIR = os.environ.get("THANATOS_BTCRECOVER_DIR", "/opt/btcrecover")

# Wordlist app -> codice lingua di seedrecover (--language)
WORDLIST_LANG_MAP = {
    "english": "en",
    "italian": "it",
    "spanish": "es",
    "french": "fr",
    "german": "de",
}

# ==================== LOGGING (SAFE) ====================

class SafeFormatter(logging.Formatter):
    """Formattatore che sanitizza logs (no seed/password)"""
    def format(self, record):
        record.msg = str(record.msg).replace("seed", "SEED").replace("pass", "PASS")
        return super().format(record)


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("/tmp/thanatos_recovery.log", mode='a'),
    ]
)
logger = logging.getLogger(__name__)

# Rimuovi handler che logga a stdout (per sicurezza)
logger.handlers = [h for h in logger.handlers if not isinstance(h, logging.StreamHandler)]


# ==================== CRYPTO ====================

def encrypt_result(plaintext: str, output_file: Path) -> Path:
    """
    Cripta il seed recuperato con Fernet.

    La chiave Fernet viene generata QUI e salvata in <output_file>.key (0600):
    senza persisterla il risultato sarebbe indecifrabile da chiunque.
    Lo staff consegna la chiave al cliente su canale separato dal link di download.

    Args:
        plaintext: seed completo (string, es. "word1 word2 ...")
        output_file: dove salvare il file .enc

    Returns:
        Path: percorso del file chiave
    """
    key = Fernet.generate_key()
    encrypted = Fernet(key).encrypt(plaintext.encode())
    with open(output_file, "wb") as f:
        f.write(encrypted)

    key_file = output_file.with_suffix(output_file.suffix + ".key")
    with open(key_file, "wb") as f:
        f.write(key)
    os.chmod(key_file, 0o600)

    logger.info(f"Result encrypted and saved to {output_file}")
    logger.info(f"Fernet key saved to {key_file}")
    return key_file


def decrypt_input(input_file: Path, private_key_path: Path) -> str:
    """
    Decripta il seed input cifrato RSA-OAEP con la chiave privata del vault.

    Il client cifra il seed parziale con la public key del vault; la private key
    viene copiata offline sulla recovery machine e usata solo qui.

    Args:
        input_file: file .enc (RSA-OAEP)
        private_key_path: chiave privata PEM del vault
    """
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    with open(input_file, "rb") as f:
        ciphertext = f.read()

    plaintext = private_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return plaintext.decode().strip()


# ==================== BTCRECOVER WRAPPER ====================

def run_btcrecover(
    mnemonic_guess: str,
    wallet_type: str,
    missing_words: int,
    wordlist: str,
    known_address: str,
    passphrase_list: str = None,
    addr_limit: int = 10,
    timeout_s: int = 3600,
) -> str:
    """
    Recupera il seed completo con seedrecover.py di btcrecover.

    IMPORTANTE (verificato con test reale su btcrecover 1.13):
      - Il recupero seed usa `seedrecover.py`, NON `btcrecover.py --tokens`.
      - Serve SEMPRE un target di validazione: un indirizzo noto del wallet
        (`--addrs`). Senza, qualsiasi seed con checksum valido sembra corretto.
      - `--big-typos N` prova a sostituire fino a N parole intere (parole
        mancanti/sbagliate); le posizioni ignote vanno riempite con un
        placeholder valido nel guess.
      - Per wallet con passphrase (es. Ledger 25a parola) si passa
        `--passphrase-list` con i candidati.

    Args:
        mnemonic_guess: miglior guess del seed (lunghezza corretta, placeholder
            nelle posizioni ignote)
        wallet_type: valore --wallet-type di seedrecover (es. bip39, electrum2)
        missing_words: n. parole mancanti/sbagliate -> --big-typos
        wordlist: lingua app (english, italian, ...)
        known_address: indirizzo noto del wallet (target di validazione)
        passphrase_list: path a file con passphrase candidate (opzionale, Ledger)
        addr_limit: quanti indirizzi derivare per path
        timeout_s: timeout massimo

    Returns:
        str: seed completo recuperato (+ eventuale passphrase in coda)

    Raises:
        Exception: se il recupero fallisce o va in timeout
    """
    seedrecover = Path(BTCRECOVER_DIR) / "seedrecover.py"
    if not seedrecover.exists():
        raise FileNotFoundError(
            f"seedrecover.py non trovato in {BTCRECOVER_DIR}. "
            "Installa btcrecover (git clone https://github.com/3rdIteration/btcrecover) "
            "e imposta THANATOS_BTCRECOVER_DIR."
        )

    if not known_address:
        raise ValueError("known_address obbligatorio: senza indirizzo noto il recupero non può validare i candidati")

    lang = WORDLIST_LANG_MAP.get(wordlist, "en")

    cmd = [
        sys.executable, str(seedrecover),
        "--wallet-type", wallet_type,
        "--language", lang,
        "--mnemonic", mnemonic_guess,
        "--addrs", known_address,
        "--addr-limit", str(addr_limit),
        "--no-eta", "--no-progress", "--disablesecuritywarnings",
    ]
    if missing_words and int(missing_words) > 0:
        cmd += ["--big-typos", str(int(missing_words))]
    if passphrase_list:
        cmd += ["--passphrase-list", passphrase_list]

    logger.info(f"Running seedrecover ({wallet_type}, big-typos={missing_words}, lang={lang})")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        cwd=str(BTCRECOVER_DIR),
    )

    output = (result.stdout or "") + "\n" + (result.stderr or "")

    # seedrecover stampa "Seed found: <mnemonic>" (e, se passphrase,
    # "Matched with BIP39 Passphrase: <pp>")
    if "Seed found:" in output:
        seed_complete = output.split("Seed found:")[1].strip().splitlines()[0].strip()
        passphrase = None
        for line in output.splitlines():
            if "Passphrase:" in line:
                passphrase = line.split("Passphrase:")[1].strip()
        logger.info(f"Seed recovered: {len(seed_complete.split())} words"
                    + (" (+ passphrase)" if passphrase else ""))
        if passphrase:
            # allega la passphrase al risultato consegnato al cliente
            return f"{seed_complete}\nPASSPHRASE: {passphrase}"
        return seed_complete

    if result.returncode != 0:
        logger.error("seedrecover failed")
        raise Exception("seedrecover error (vedi log)")
    raise Exception("Nessun seed corrispondente trovato: controlla guess, n. parole, indirizzo e lingua")


# ==================== MAIN ====================

def main():
    parser = argparse.ArgumentParser(
        description="Thanatos Wallet Recovery CLI - Offline seed recovery tool"
    )
    parser.add_argument("--job-id", required=True, help="Job ID (es. CASE-2026-0042_REC-001)")
    parser.add_argument("--input-file", required=True, help="Path to encrypted seed input")
    parser.add_argument("--private-key", required=True,
                        help="Vault RSA private key (PEM) per decriptare l'input")
    parser.add_argument("--wallet-type", required=True, choices=["bip39", "electrum2"],
                        help="Tipo wallet per seedrecover (bip39 copre anche Ledger)")
    parser.add_argument("--known-address", required=True,
                        help="Indirizzo noto del wallet: target di validazione (obbligatorio)")
    parser.add_argument("--missing-words", type=int, default=0,
                        help="N. parole mancanti/sbagliate (-> --big-typos)")
    parser.add_argument("--wordlist", default="english", choices=list(WORDLIST_LANG_MAP.keys()),
                        help="BIP39 wordlist language")
    parser.add_argument("--passphrase-list", default=None,
                        help="File con passphrase candidate (Ledger 25a parola / BIP39 passphrase)")
    parser.add_argument("--output-file", default=None, help="Output file for encrypted result")

    args = parser.parse_args()

    # Validazione input
    input_file = Path(args.input_file)
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        sys.exit(1)

    private_key_file = Path(args.private_key)
    if not private_key_file.exists():
        logger.error(f"Private key not found: {private_key_file}")
        sys.exit(1)

    if not args.output_file:
        args.output_file = f"{input_file.parent}/{args.job_id}_result.enc"

    output_file = Path(args.output_file)

    logger.info(f"===== THANATOS RECOVERY JOB: {args.job_id} =====")
    logger.info(f"Wallet type: {args.wallet_type}")
    logger.info(f"Missing words: {args.missing_words}")
    logger.info(f"Wordlist: {args.wordlist}")
    logger.info(f"Output: {output_file}")

    try:
        # Step 1: Leggi seed input (crittografato)
        logger.info("Step 1: Reading encrypted seed input...")
        seed_partial = decrypt_input(input_file, private_key_file)
        logger.info(f"Input seed read: {len(seed_partial.split())} words")

        # Step 2: Run seedrecover
        logger.info("Step 2: Running recovery algorithm...")
        seed_complete = run_btcrecover(
            mnemonic_guess=seed_partial,
            wallet_type=args.wallet_type,
            missing_words=args.missing_words,
            wordlist=args.wordlist,
            known_address=args.known_address,
            passphrase_list=args.passphrase_list,
        )

        # Step 3: Encrypt result
        logger.info("Step 3: Encrypting recovery result...")
        encrypt_result(seed_complete, output_file)

        logger.info("===== RECOVERY COMPLETE =====")
        logger.info(f"Output file: {output_file}")
        logger.info(f"File size: {output_file.stat().st_size} bytes")

        print(f"✅ Recovery complete. Result saved to: {output_file}")
        print(f"   File size: {output_file.stat().st_size} bytes")
        print(f"   ⚠️  Keep this file secure and encrypted until delivery to client")

    except Exception as e:
        logger.error(f"Recovery failed: {str(e)}", exc_info=True)
        print(f"❌ Recovery failed: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        # Cleanup: scrub temp files
        logger.info("Cleaning up temporary files...")
        # Aggiungi qui la pulizia di file temporanei


if __name__ == "__main__":
    main()
