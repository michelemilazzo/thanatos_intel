#!/usr/bin/env python3
"""
Self-test OFFLINE della recovery machine.

Prova l'intera catena con un vettore BIP39 NOTO (nessun fondo reale):
  1. genera una coppia RSA usa-e-getta (simula il vault)
  2. cifra un seed guess con una parola sbagliata (come farebbe il browser)
  3. lancia thanatos-recovery-cli -> decripta -> seedrecover -> Fernet
  4. decifra il risultato e verifica che sia il seed corretto

Se stampa "SELF-TEST: PASS" la macchina è pronta per recuperi reali.
Non serve internet né la private key di produzione.
"""
import os
import sys
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.fernet import Fernet

HERE = Path(__file__).resolve().parent
CLI = HERE / "thanatos-recovery-cli"
BTCR = HERE / "btcrecover"

# Vettore standard: "abandon x11 + about". m/84'/0'/0'/0/0 (native segwit):
KNOWN_ADDR = "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu"
GUESS = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon ability"
EXPECTED = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"


def main():
    tmp = Path(tempfile.mkdtemp(prefix="thanatos_selftest_"))
    try:
        # 1) coppia RSA usa-e-getta
        priv = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        priv_path = tmp / "test_priv.pem"
        priv_path.write_bytes(priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()))

        # 2) cifra il guess con la public (come il browser col vault)
        ct = priv.public_key().encrypt(
            GUESS.encode(),
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        in_path = tmp / "test_seed.enc"
        in_path.write_bytes(ct)
        out_path = tmp / "test_result.enc"

        # 3) esegui il CLI reale
        env = dict(os.environ, THANATOS_BTCRECOVER_DIR=str(BTCR))
        print("-> eseguo recupero di prova (seedrecover, offline)...")
        r = subprocess.run(
            [sys.executable, str(CLI),
             "--job-id", "SELFTEST",
             "--input-file", str(in_path),
             "--private-key", str(priv_path),
             "--wallet-type", "bip39",
             "--known-address", KNOWN_ADDR,
             "--missing-words", "1",
             "--wordlist", "english",
             "--output-file", str(out_path)],
            capture_output=True, text=True, timeout=900, env=env)

        if not out_path.exists():
            print(r.stdout); print(r.stderr, file=sys.stderr)
            print("SELF-TEST: FAIL (nessun output prodotto)", file=sys.stderr)
            return 1

        # 4) decifra il risultato e confronta
        key = out_path.with_suffix(out_path.suffix + ".key").read_bytes()
        got = Fernet(key).decrypt(out_path.read_bytes()).decode().strip()
        if got == EXPECTED:
            print("SELF-TEST: PASS — la recovery machine funziona (recupero + crypto OK)")
            return 0
        print(f"SELF-TEST: FAIL — atteso:\n  {EXPECTED}\nottenuto:\n  {got}", file=sys.stderr)
        return 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
