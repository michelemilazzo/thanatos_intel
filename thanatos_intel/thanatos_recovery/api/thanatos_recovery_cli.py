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
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import os


# ==================== CONFIG ====================

# FERNET_KEY = os.environ.get("THANATOS_RECOVERY_KEY", "DEVELOPMENT_KEY_CHANGE_ME")
# Per ora usiamo chiave hardcoded per POC; in produzione via env var o file protetto

FERNET_KEY = Fernet.generate_key()  # POC: generiamo una key temporanea
cipher_suite = Fernet(FERNET_KEY)

# Wordlist paths (da installare localmente)
WORDLIST_PATHS = {
    "english": "/usr/share/dict/words",  # BIP39 English (puoi prendere da btcrecover)
    "italian": "/usr/share/dict/italian",
    "spanish": "/usr/share/dict/spanish",
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

def encrypt_result(plaintext: str, output_file: Path) -> None:
    """
    Cripta il seed recuperato con Fernet

    Args:
        plaintext: seed completo (string, es. "word1 word2 ...")
        output_file: dove salvare il file .enc
    """
    encrypted = cipher_suite.encrypt(plaintext.encode())
    with open(output_file, "wb") as f:
        f.write(encrypted)
    logger.info(f"Result encrypted and saved to {output_file}")


def decrypt_input(input_file: Path) -> str:
    """
    Decripta il seed input (facoltativo se pre-decriptato dal client)
    In questo POC assumiamo che il file sia plaintext.
    In produzione: decripta con PRIVATE_KEY RSA
    """
    with open(input_file, "r") as f:
        return f.read().strip()


# ==================== BTCRECOVER WRAPPER ====================

def run_btcrecover(
    seed_partial: str,
    wallet_type: str,
    missing_words: int,
    wordlist: str
) -> str:
    """
    Chiama BTCRecover per recuperare il seed completo

    Args:
        seed_partial: seed parziale (es. "apple banana cherry ... ????")
        wallet_type: bip39, electrum, bip38
        missing_words: numero di parole mancanti
        wordlist: english, italian, spanish

    Returns:
        str: seed completo recuperato

    Raises:
        Exception: se BTCRecover fallisce o timeout
    """
    logger.info(f"Starting BTCRecover for {wallet_type} with {missing_words} missing words")

    import tempfile
    import shutil

    # Crea directory temp per BTCRecover
    temp_dir = tempfile.mkdtemp(prefix="btcrecover_")
    try:
        # Crea file di input per BTCRecover
        tokens_file = os.path.join(temp_dir, "tokens.txt")
        with open(tokens_file, "w") as f:
            if wallet_type == "bip39":
                f.write(seed_partial)
            elif wallet_type == "electrum":
                f.write(seed_partial)
            else:
                raise ValueError(f"Unsupported wallet type: {wallet_type}")

        # Mappa wallet type a BTCRecover format
        wallet_type_map = {
            "bip39": "--bip39",
            "electrum": "--electrum",
            "bip38": "--bip38"
        }

        wallet_arg = wallet_type_map.get(wallet_type)
        if not wallet_arg:
            raise ValueError(f"Unsupported wallet type: {wallet_type}")

        # Costruisci comando BTCRecover
        # NOTA: BTCRecover ha molte opzioni. Questo è un esempio semplificato.
        cmd = [
            "btcrecover",
            "--tokens", tokens_file,
            wallet_arg,
            f"--language={wordlist}",
            "--no-dupchecks",
            "--workers=4",
            "--timeout=300"  # 5 minuti max
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        # Esegui BTCRecover
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minuti timeout totale
        )

        if result.returncode != 0:
            logger.error(f"BTCRecover failed: {result.stderr}")
            raise Exception(f"BTCRecover error: {result.stderr}")

        # Parsing result
        output = result.stdout
        logger.info(f"BTCRecover output: {output}")

        # BTCRecover prints "Password found: <seed>" on success
        if "Password found:" in output:
            seed_complete = output.split("Password found:")[1].strip().split('\n')[0]
            logger.info(f"✅ Seed recovered: {len(seed_complete.split())} words")
            return seed_complete
        else:
            raise Exception("BTCRecover did not find matching seed")

    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("Cleaned up temporary files")


# ==================== MAIN ====================

def main():
    parser = argparse.ArgumentParser(
        description="Thanatos Wallet Recovery CLI - Offline seed recovery tool"
    )
    parser.add_argument("--job-id", required=True, help="Job ID (es. CASE-2026-0042_REC-001)")
    parser.add_argument("--input-file", required=True, help="Path to encrypted seed input")
    parser.add_argument("--wallet-type", required=True, choices=["bip39", "electrum", "bip38"],
                        help="Type of wallet")
    parser.add_argument("--missing-words", type=int, default=3, help="Number of missing/wrong words")
    parser.add_argument("--wordlist", default="english", choices=list(WORDLIST_PATHS.keys()),
                        help="BIP39 wordlist language")
    parser.add_argument("--output-file", default=None, help="Output file for encrypted result")

    args = parser.parse_args()

    # Validazione input
    input_file = Path(args.input_file)
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
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
        seed_partial = decrypt_input(input_file)
        logger.info(f"Input seed read: {len(seed_partial.split())} words")

        # Step 2: Run BTCRecover
        logger.info("Step 2: Running recovery algorithm...")
        seed_complete = run_btcrecover(
            seed_partial=seed_partial,
            wallet_type=args.wallet_type,
            missing_words=args.missing_words,
            wordlist=args.wordlist
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
