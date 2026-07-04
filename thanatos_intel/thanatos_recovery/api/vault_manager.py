"""
Vault Manager: Gestione E2E del vault di recovery (cifratura, TTL, cleanup)

Responsabilità:
  - Genera e gestisci RSA keypair per il vault
  - Crittografa seed input da client
  - Decripta seed output dal tool offline
  - Cleanup automatico su scadenza TTL
  - Audit trail completo
"""

import frappe
import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization
from cryptography.fernet import Fernet


VAULT_BASE_PATH = "/mnt/thanatos-box/recovery-vault"
VAULT_TTL_HOURS = 48


# ==================== VAULT INITIALIZATION ====================

def ensure_vault_exists():
    """
    Crea la struttura del vault se non esiste

    Directory:
      /mnt/thanatos-box/recovery-vault/
        ├── keys/
        │   ├── private.pem (NOT WORLD READABLE)
        │   ├── public.pem
        │   └── key_rotation_log.json
        ├── {job_id}/
        │   ├── seed_input.enc
        │   ├── seed_output.enc (se completato)
        │   ├── job_metadata.json
        │   └── audit.log
    """
    vault_path = Path(VAULT_BASE_PATH)
    vault_path.mkdir(parents=True, exist_ok=True, mode=0o700)

    keys_path = vault_path / "keys"
    keys_path.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Genera keypair se non esiste
    private_key_path = keys_path / "private.pem"
    public_key_path = keys_path / "public.pem"

    if not private_key_path.exists():
        frappe.logger().info("Generating RSA keypair for vault...")

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
        )

        # Salva private key (read-only per staff)
        with open(private_key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        os.chmod(private_key_path, 0o600)

        # Salva public key (distribuibile ai client)
        public_key = private_key.public_key()
        with open(public_key_path, "wb") as f:
            f.write(public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))

        frappe.logger().info(f"Vault keys generated at {keys_path}")


def get_vault_public_key() -> str:
    """
    Restituisce la public key RSA per il browser client

    Returns:
        str: PEM-encoded public key
    """
    ensure_vault_exists()
    public_key_path = Path(VAULT_BASE_PATH) / "keys" / "public.pem"

    with open(public_key_path, "r") as f:
        return f.read()


def get_vault_private_key():
    """
    Carica la private key RSA per decriptare seed input

    Returns:
        RSA private key object
    """
    ensure_vault_exists()
    private_key_path = Path(VAULT_BASE_PATH) / "keys" / "private.pem"

    with open(private_key_path, "rb") as f:
        return serialization.load_pem_private_key(
            f.read(),
            password=None
        )


# ==================== JOB VAULT OPERATIONS ====================

def create_job_vault(job_id: str, case_id: str, operator: str):
    """
    Crea directory vault per un nuovo job

    Args:
        job_id: WRJ-YYYY-0001
        case_id: CASE-2026-0042
        operator: email utente
    """
    job_vault_path = Path(VAULT_BASE_PATH) / job_id
    job_vault_path.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Metadata iniziale
    metadata = {
        "job_id": job_id,
        "case_id": case_id,
        "created_by": operator,
        "created_at": datetime.now().isoformat(),
        "status": "draft",
        "expires_at": (datetime.now() + timedelta(hours=VAULT_TTL_HOURS)).isoformat()
    }

    metadata_file = job_vault_path / "job_metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)
    os.chmod(metadata_file, 0o600)

    # Audit log iniziale
    audit_file = job_vault_path / "audit.log"
    audit_file.touch(mode=0o600)
    _vault_audit_log(job_id, f"Job vault created for case {case_id}")

    frappe.logger().info(f"Job vault created: {job_vault_path}")


def save_encrypted_seed_input(job_id: str, encrypted_data_base64: str):
    """
    Salva il seed input crittografato nel vault

    Args:
        job_id: WRJ-YYYY-0001
        encrypted_data_base64: base64(RSA encrypted seed)
    """
    import base64

    job_vault_path = Path(VAULT_BASE_PATH) / job_id
    seed_input_file = job_vault_path / "seed_input.enc"

    # Decode e salva
    encrypted_bytes = base64.b64decode(encrypted_data_base64)
    with open(seed_input_file, "wb") as f:
        f.write(encrypted_bytes)
    os.chmod(seed_input_file, 0o600)

    _vault_audit_log(job_id, f"Seed input saved ({len(encrypted_bytes)} bytes)")


def decrypt_seed_input(job_id: str) -> str:
    """
    Decripta il seed input (via private key del vault)

    NOTA: Questo dovrebbe essere eseguito OFFLINE dal tool recovery.
    Questo endpoint è solo per test/debug e dovrebbe richiedere autorizzazione speciale.

    Args:
        job_id: WRJ-YYYY-0001

    Returns:
        str: seed parziale in plaintext
    """
    frappe.only_for(["Investigation Manager"])  # Restrizione extra

    job_vault_path = Path(VAULT_BASE_PATH) / job_id
    seed_input_file = job_vault_path / "seed_input.enc"

    if not seed_input_file.exists():
        frappe.throw(f"Seed input not found for job {job_id}")

    private_key = get_vault_private_key()

    with open(seed_input_file, "rb") as f:
        encrypted_data = f.read()

    try:
        decrypted = private_key.decrypt(
            encrypted_data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        _vault_audit_log(job_id, f"Seed input decrypted by {frappe.session.user}")
        return decrypted.decode()

    except Exception as e:
        frappe.logger().error(f"Failed to decrypt seed input for {job_id}: {e}")
        frappe.throw("Decryption failed")


def save_encrypted_seed_output(job_id: str, encrypted_result_base64: str):
    """
    Salva il seed output crittografato (dal tool recovery)

    Args:
        job_id: WRJ-YYYY-0001
        encrypted_result_base64: base64(seed completo crittografato)
    """
    import base64

    job_vault_path = Path(VAULT_BASE_PATH) / job_id
    seed_output_file = job_vault_path / "seed_output.enc"

    encrypted_bytes = base64.b64decode(encrypted_result_base64)
    with open(seed_output_file, "wb") as f:
        f.write(encrypted_bytes)
    os.chmod(seed_output_file, 0o600)

    # Aggiorna metadata
    metadata_file = job_vault_path / "job_metadata.json"
    with open(metadata_file, "r") as f:
        metadata = json.load(f)
    metadata["status"] = "completed"
    metadata["completed_at"] = datetime.now().isoformat()
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    _vault_audit_log(job_id, f"Seed output saved ({len(encrypted_bytes)} bytes)")


# ==================== CLEANUP & EXPIRATION ====================

@frappe.whitelist()
def cleanup_expired_recoveries():
    """
    Scheduler: Rimuove job vault scaduti (TTL > VAULT_TTL_HOURS)
    Dovrebbe essere eseguito giornalmente via Frappe scheduler
    """
    frappe.only_for(["Administrator"])

    vault_path = Path(VAULT_BASE_PATH)
    expired_count = 0
    failed_count = 0

    if not vault_path.exists():
        return {"expired": 0, "failed": 0}

    for job_dir in vault_path.iterdir():
        if not job_dir.is_dir() or job_dir.name == "keys":
            continue

        try:
            metadata_file = job_dir / "job_metadata.json"
            if not metadata_file.exists():
                continue

            with open(metadata_file, "r") as f:
                metadata = json.load(f)

            expires_at = datetime.fromisoformat(metadata.get("expires_at", ""))

            if datetime.now() > expires_at:
                # Backup audit log prima di eliminare
                audit_file = job_dir / "audit.log"
                if audit_file.exists():
                    backup_path = vault_path / "audit_archive" / f"{job_dir.name}.log"
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(audit_file, backup_path)

                # Elimina directory
                shutil.rmtree(job_dir)
                frappe.logger().info(f"Cleaned up expired job vault: {job_dir.name}")
                expired_count += 1

        except Exception as e:
            frappe.logger().error(f"Failed to cleanup job {job_dir.name}: {e}")
            failed_count += 1

    frappe.logger().info(f"Cleanup complete: {expired_count} expired, {failed_count} failed")

    return {"expired": expired_count, "failed": failed_count}


# ==================== UTILITY ====================

def _vault_audit_log(job_id: str, message: str):
    """
    Aggiunge riga a audit log del job
    """
    job_vault_path = Path(VAULT_BASE_PATH) / job_id
    audit_file = job_vault_path / "audit.log"

    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] {message}\n"

    with open(audit_file, "a") as f:
        f.write(log_entry)


def get_job_vault_info(job_id: str) -> dict:
    """
    Restituisce info sul vault di un job (per debugging)
    """
    job_vault_path = Path(VAULT_BASE_PATH) / job_id

    if not job_vault_path.exists():
        return {"status": "not_found"}

    metadata_file = job_vault_path / "job_metadata.json"
    with open(metadata_file, "r") as f:
        metadata = json.load(f)

    # Dimensioni file
    seed_input_file = job_vault_path / "seed_input.enc"
    seed_output_file = job_vault_path / "seed_output.enc"

    return {
        "status": "found",
        "metadata": metadata,
        "seed_input_size": seed_input_file.stat().st_size if seed_input_file.exists() else 0,
        "seed_output_size": seed_output_file.stat().st_size if seed_output_file.exists() else 0,
        "expires_at": metadata.get("expires_at"),
        "is_expired": datetime.now() > datetime.fromisoformat(metadata.get("expires_at", ""))
    }
