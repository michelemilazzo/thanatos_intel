"""
API per Wallet Recovery Job in Thanatos
Flusso E2E: upload seed encrypted -> genera comando CLI -> upload risultato -> link scadibile
"""

import frappe
import json
import hmac
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization


# ==================== CONFIG ====================

VAULT_BASE_PATH = "/mnt/thanatos-box/recovery-vault"
VAULT_TTL_HOURS = 48

# Mappa il valore del campo DocType "Wallet Type" all'argomento --wallet-type del CLI
WALLET_TYPE_CLI_MAP = {
    "BIP39 Seed": "bip39",
    "Electrum Seed": "electrum",
    "BIP38 Encrypted": "bip38",
    "Ledger Passphrase": "bip39",  # Ledger usa derivazione BIP39 + passphrase
}


def _get_vault_secret() -> str:
    """
    Secret HMAC per firmare i download link.

    Priorità:
      1. site_config `wallet_recovery_secret_key`
      2. file persistente nel vault (generato una tantum, 0600)

    Non usa mai una costante hardcoded: un secret prevedibile permetterebbe
    di forgiare token di download validi.
    """
    conf_key = frappe.local.conf.get("wallet_recovery_secret_key")
    if conf_key:
        return conf_key

    secret_file = Path(VAULT_BASE_PATH) / "keys" / "hmac_secret.key"
    if secret_file.exists():
        return secret_file.read_text().strip()

    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret = os.urandom(32).hex()
    secret_file.write_text(secret)
    os.chmod(secret_file, 0o600)
    return secret

# Generate RSA keypair on first run
def get_or_create_keys():
    keys_dir = Path(f"{VAULT_BASE_PATH}/keys")
    keys_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = keys_dir / "private.pem"
    public_key_path = keys_dir / "public.pem"

    if not private_key_path.exists():
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
        )
        with open(private_key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))

        public_key = private_key.public_key()
        with open(public_key_path, "wb") as f:
            f.write(public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))

    return private_key_path, public_key_path


# ==================== FRAPPE API ENDPOINTS ====================

@frappe.whitelist()
def create_recovery_job(case_id, wallet_type=None, missing_words_count=None, wordlist_type=None):
    """
    Crea un nuovo Wallet Recovery Job legato a un caso

    Args:
        case_id: Investigation Case ID

    Returns:
        dict: job record
    """
    frappe.only_for(["Investigator", "Investigation Manager"])

    if not frappe.db.exists("Investigation Case", case_id):
        frappe.throw(f"Investigation Case {case_id} inesistente")

    job = frappe.new_doc("Wallet Recovery Job")
    job.case_id = case_id
    job.operator = frappe.session.user
    job.status = "Draft"
    if wallet_type:
        job.wallet_type = wallet_type
    if missing_words_count:
        job.missing_words_count = int(missing_words_count)
    if wordlist_type:
        job.wordlist_type = wordlist_type
    job.insert()

    _log_audit(job.name, f"Job created by {frappe.session.user}")

    return job.as_dict()


@frappe.whitelist()
def create_recovery_batch(case_id, jobs):
    """
    Crea più Wallet Recovery Job in un colpo solo (Fase 3: batch multi-job).

    Utile quando un cliente ha più wallet/seed da recuperare nello stesso caso.

    Args:
        case_id: Investigation Case ID
        jobs: JSON list di dict, es:
              [{"wallet_type":"BIP39 Seed","missing_words_count":3,"wordlist_type":"english"}, ...]

    Returns:
        dict: {created: [job_name, ...], count: N}
    """
    frappe.only_for(["Investigator", "Investigation Manager"])

    if not frappe.db.exists("Investigation Case", case_id):
        frappe.throw(f"Investigation Case {case_id} inesistente")

    if isinstance(jobs, str):
        jobs = json.loads(jobs)
    if not isinstance(jobs, list) or not jobs:
        frappe.throw("Parametro 'jobs' deve essere una lista non vuota")

    created = []
    for spec in jobs:
        job = frappe.new_doc("Wallet Recovery Job")
        job.case_id = case_id
        job.operator = frappe.session.user
        job.status = "Draft"
        job.wallet_type = spec.get("wallet_type")
        job.missing_words_count = int(spec.get("missing_words_count") or 1)
        job.wordlist_type = spec.get("wordlist_type") or "english"
        job.insert()
        _log_audit(job.name, f"Job created (batch) by {frappe.session.user}")
        created.append(job.name)

    return {"created": created, "count": len(created)}


@frappe.whitelist()
def get_vault_public_key():
    """
    Restituisce la public key RSA per il client (browser-side encryption)

    Returns:
        str: PEM-encoded public key
    """
    _, public_key_path = get_or_create_keys()
    with open(public_key_path, "r") as f:
        return f.read()


@frappe.whitelist(allow_guest=False)
def upload_seed_input(job_id, encrypted_seed_base64):
    """
    Carica il seed input crittografato (da browser/client)

    Args:
        job_id: WRJ-YYYY-0001
        encrypted_seed_base64: base64(AES-encrypted seed)

    Returns:
        dict: {status: "ok", vault_path: "..."}
    """
    frappe.only_for(["Investigator", "Investigation Manager"])

    job = frappe.get_doc("Wallet Recovery Job", job_id)

    # Salva file binario nel vault
    vault_job_path = Path(f"{VAULT_BASE_PATH}/{job_id}")
    vault_job_path.mkdir(parents=True, exist_ok=True)

    seed_input_file = vault_job_path / "seed_input.enc"

    import base64
    with open(seed_input_file, "wb") as f:
        f.write(base64.b64decode(encrypted_seed_base64))

    job.seed_input_file = f"file://{seed_input_file}"
    job.status = "Uploaded"
    job.db_update()

    _log_audit(job_id, f"Seed input uploaded ({seed_input_file.stat().st_size} bytes)")

    return {"status": "ok", "vault_path": str(seed_input_file)}


@frappe.whitelist()
def generate_cli_command(job_id, parameters):
    """
    Genera il comando CLI per eseguire BTCRecover offline

    Args:
        job_id: WRJ-YYYY-0001
        parameters: JSON con {missing_words_count, wordlist_type, ...}

    Returns:
        dict: {command: "thanatos-recovery-cli ...", job_id: "..."}
    """
    frappe.only_for(["Investigator", "Investigation Manager"])

    job = frappe.get_doc("Wallet Recovery Job", job_id)
    params = json.loads(parameters)

    vault_job_path = f"{VAULT_BASE_PATH}/{job_id}"

    cli_wallet_type = WALLET_TYPE_CLI_MAP.get(job.wallet_type)
    if not cli_wallet_type:
        frappe.throw(f"Wallet type non supportato dal CLI: {job.wallet_type}")

    cmd = f"""thanatos-recovery-cli \\
  --job-id {job_id} \\
  --input-file {vault_job_path}/seed_input.enc \\
  --private-key {VAULT_BASE_PATH}/keys/private.pem \\
  --wallet-type {cli_wallet_type} \\
  --missing-words {params.get('missing_words_count', 3)} \\
  --wordlist {params.get('wordlist_type', 'english')} \\
  --output-file {vault_job_path}/seed_output.enc"""

    # Salva comando nel doctype
    job.processing_command = cmd
    job.status = "Processing"
    job.db_update()

    _log_audit(job_id, f"CLI command generated")

    return {
        "command": cmd,
        "job_id": job_id,
        "instructions": "Copy this command to your recovery machine and execute it offline. No internet connection required."
    }


@frappe.whitelist(allow_guest=False)
def upload_recovery_result(job_id, encrypted_result_base64):
    """
    Carica il seed completo (result) crittografato dal tool offline

    Args:
        job_id: WRJ-YYYY-0001
        encrypted_result_base64: base64(encrypted seed output)

    Returns:
        dict: {status: "ok", download_link: "...", expires_at: "..."}
    """
    frappe.only_for(["Investigator", "Investigation Manager"])

    job = frappe.get_doc("Wallet Recovery Job", job_id)

    vault_job_path = Path(f"{VAULT_BASE_PATH}/{job_id}")
    seed_output_file = vault_job_path / "seed_output.enc"

    import base64
    with open(seed_output_file, "wb") as f:
        f.write(base64.b64decode(encrypted_result_base64))

    # Genera token HMAC per il download link
    expires_at = datetime.now() + timedelta(hours=VAULT_TTL_HOURS)
    token = _generate_vault_token(job_id, expires_at)

    download_link = f"/api/method/thanatos_intel.thanatos_recovery.api.recovery_api.get_recovery_result?job_id={job_id}&token={token}"

    # Salva metadata nel job
    job.seed_output_file = f"file://{seed_output_file}"
    job.result_vault_url = download_link
    job.result_expires_at = expires_at
    job.status = "Completed"
    job.db_update()

    _log_audit(job_id, f"Recovery result uploaded. Download link generated (expires {expires_at})")

    return {
        "status": "ok",
        "download_link": download_link,
        "expires_at": expires_at.isoformat(),
        "instructions": "Share this link securely with the client. Link expires in 48 hours."
    }


@frappe.whitelist(allow_guest=True)
def get_recovery_result(job_id, token=None):
    """
    Scarica il seed recuperato dal vault (client-facing endpoint)

    Args:
        job_id: WRJ-YYYY-0001
        token: HMAC token per validare la richiesta

    Returns:
        bytes: file encrypted seed_output.enc
    """
    # Valida token
    if not token or not _validate_vault_token(job_id, token):
        frappe.throw("Invalid or expired token", frappe.PermissionError)

    vault_job_path = Path(f"{VAULT_BASE_PATH}/{job_id}")
    seed_output_file = vault_job_path / "seed_output.enc"

    if not seed_output_file.exists():
        frappe.throw("Recovery result not found", frappe.DoesNotExistError)

    # Log audit per compliance
    _log_audit(job_id, f"Recovery result downloaded by {frappe.session.user or 'guest'}")

    # Ritorna il file
    with open(seed_output_file, "rb") as f:
        frappe.response['filecontent'] = f.read()
    frappe.response['filename'] = f"{job_id}_seed_output.enc"
    frappe.response['type'] = "download"


# ==================== UTILITY FUNCTIONS ====================

def _generate_vault_token(job_id, expires_at):
    """
    Genera HMAC token per il download link (scadibile)
    """
    message = f"{job_id}:{expires_at.isoformat()}".encode()
    token = hmac.new(
        _get_vault_secret().encode(),
        message,
        hashlib.sha256
    ).hexdigest()
    return token


def _validate_vault_token(job_id, token):
    """
    Valida HMAC token + verifica scadenza
    """
    job = frappe.db.get_value(
        "Wallet Recovery Job", job_id,
        ["result_expires_at"],
        as_dict=True
    )

    if not job or not job.result_expires_at:
        return False

    # Ricalcola token con la scadenza salvata
    expected_token = _generate_vault_token(job_id, job.result_expires_at)

    # Verifica token e scadenza
    is_valid = hmac.compare_digest(token, expected_token)
    is_not_expired = datetime.now() < job.result_expires_at

    return is_valid and is_not_expired


def _log_audit(job_id, message):
    """
    Aggiunge riga all'audit log
    """
    job = frappe.get_doc("Wallet Recovery Job", job_id)
    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] {message}"

    if job.audit_log:
        job.audit_log += f"\n{log_entry}"
    else:
        job.audit_log = log_entry

    job.db_update()
