"""Connettori email esterni per clienti Thanatos.

Permette a ogni utente di collegare account Gmail / Outlook-Business / IMAP generico
alla propria casella @thanatos.agency. Le mail vengono scaricate via IMAP e consegnate
nella cartella INBOX.External della casella Stalwart dell'utente.

Store per-utente: /etc/thanatos/mail_connectors/<userkey>.json
Password cifrata con Fernet (chiave derivata da encryption_key del sito).
"""
import imaplib
import json
import os
import time
import uuid
import email as _email_mod
import base64
import hashlib

import frappe

STORE_DIR = "/etc/thanatos/mail_connectors"
IMAP_DELIVERY_HOST = "mailmx.onekeyco.com"
WEBMAIL_SECRETS = "/etc/thanatos/webmail_secrets.json"

PROVIDERS = {
    "gmail": {"label": "Gmail", "host": "imap.gmail.com", "port": 993},
    "outlook_business": {"label": "Outlook / Office 365", "host": "outlook.office365.com", "port": 993},
    "yahoo": {"label": "Yahoo Mail", "host": "imap.mail.yahoo.com", "port": 993},
    "imap": {"label": "IMAP generico", "host": "", "port": 993},
}


def _fernet():
    from cryptography.fernet import Fernet
    key_src = frappe.conf.get("encryption_key") or "thanatos-mail-connectors-key"
    key = base64.urlsafe_b64encode(hashlib.sha256(key_src.encode()).digest())
    return Fernet(key)


def _encrypt(plain):
    return _fernet().encrypt(plain.encode()).decode()


def _decrypt(enc):
    return _fernet().decrypt(enc.encode()).decode()


def _userkey(user=None):
    u = user or frappe.session.user
    return u.replace("@", "_").replace(".", "_")


def _store_path(user=None):
    os.makedirs(STORE_DIR, exist_ok=True)
    return os.path.join(STORE_DIR, _userkey(user) + ".json")


def _load(user=None):
    p = _store_path(user)
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p)) or []
    except Exception:
        return []


def _save(connectors, user=None):
    p = _store_path(user)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(connectors, f, indent=2)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o640)
    except Exception:
        pass


def _target_mailbox(user=None):
    u = user or frappe.session.user
    if u.endswith("@thanatos.agency"):
        return u
    # cerca Email Account collegato
    ea = frappe.db.get_value("Email Account", {"login_id": u}, "email_id")
    if ea:
        return ea
    # fallback: usa l'email utente stessa se è @thanatos.agency
    return None


def _guard_user():
    if frappe.session.user == "Guest":
        frappe.throw("Login richiesto.", frappe.PermissionError)


# ── API pubblica ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def list_connectors():
    _guard_user()
    rows = []
    for c in _load():
        rows.append({k: v for k, v in c.items() if k != "password_enc"})
    return {"connectors": rows, "providers": PROVIDERS}


@frappe.whitelist()
def add_connector(provider, email, password, label=None, imap_host=None, imap_port=None, inbox_folder="INBOX"):
    _guard_user()
    prov = PROVIDERS.get(provider)
    if not prov:
        frappe.throw(f"Provider non supportato: {provider}")
    host = (imap_host or "").strip() or prov["host"]
    port = int(imap_port or prov["port"])
    email = email.strip().lower()
    if not host:
        frappe.throw("Host IMAP obbligatorio per provider IMAP generico.")

    target = _target_mailbox()
    if not target:
        frappe.throw("Nessuna casella @thanatos.agency associata al tuo account. Contatta l'amministratore.")

    # test connessione prima di salvare
    ok, err = _test_imap(host, port, email, password)
    if not ok:
        frappe.throw(f"Connessione IMAP fallita: {err}")

    connectors = _load()
    # sostituisci se stessa email
    connectors = [c for c in connectors if c.get("email") != email]
    connectors.append({
        "id": str(uuid.uuid4()),
        "provider": provider,
        "label": label or f"{prov['label']} — {email}",
        "imap_host": host,
        "imap_port": port,
        "email": email,
        "password_enc": _encrypt(password),
        "inbox_folder": inbox_folder,
        "target_mailbox": target,
        "enabled": True,
        "last_sync_at": None,
        "last_uid": 0,
        "uid_validity": None,
        "last_error": None,
        "synced_count": 0,
    })
    _save(connectors)
    return {"ok": True, "email": email, "target": target}


@frappe.whitelist()
def delete_connector(connector_id):
    _guard_user()
    connectors = [c for c in _load() if c.get("id") != connector_id]
    _save(connectors)
    return {"ok": True}


@frappe.whitelist()
def toggle_connector(connector_id, enabled):
    _guard_user()
    connectors = _load()
    for c in connectors:
        if c.get("id") == connector_id:
            c["enabled"] = bool(enabled)
    _save(connectors)
    return {"ok": True}


@frappe.whitelist()
def test_connector(connector_id):
    _guard_user()
    for c in _load():
        if c.get("id") == connector_id:
            try:
                pw = _decrypt(c["password_enc"])
            except Exception:
                return {"ok": False, "error": "Impossibile decifrare la password."}
            ok, err = _test_imap(c["imap_host"], c["imap_port"], c["email"], pw)
            return {"ok": ok, "error": err}
    frappe.throw("Connettore non trovato.")


@frappe.whitelist()
def sync_now(connector_id):
    _guard_user()
    for c in _load():
        if c.get("id") == connector_id:
            n, err = _sync_connector_entry(c, frappe.session.user)
            if err:
                return {"ok": False, "error": err, "synced": n}
            return {"ok": True, "synced": n}
    frappe.throw("Connettore non trovato.")


# ── Cron ─────────────────────────────────────────────────────────────────────

def sync_all_connectors():
    """Cron: sincronizza tutti i connettori di tutti gli utenti."""
    if not os.path.isdir(STORE_DIR):
        return
    for fname in os.listdir(STORE_DIR):
        if not fname.endswith(".json"):
            continue
        user_key = fname[:-5]
        # ricostruisce email utente (approssimativo — il target_mailbox è nel file)
        connectors = []
        try:
            connectors = json.load(open(os.path.join(STORE_DIR, fname))) or []
        except Exception:
            continue
        updated = []
        for c in connectors:
            if not c.get("enabled"):
                updated.append(c)
                continue
            n, err = _sync_connector_entry(c, user_key)
            c["last_sync_at"] = frappe.utils.now()
            if err:
                c["last_error"] = err
            else:
                c["last_error"] = None
                c["synced_count"] = c.get("synced_count", 0) + n
            updated.append(c)
        try:
            p = os.path.join(STORE_DIR, fname)
            tmp = p + ".tmp"
            json.dump(updated, open(tmp, "w"), indent=2)
            os.replace(tmp, p)
        except Exception:
            pass


# ── Core IMAP ────────────────────────────────────────────────────────────────

def _test_imap(host, port, email, password):
    try:
        M = imaplib.IMAP4_SSL(host, int(port))
        M.login(email, password)
        M.logout()
        return True, None
    except imaplib.IMAP4.error as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def _sync_connector_entry(c, user_key):
    """Scarica mail nuove dal connettore e le consegna nella casella Stalwart."""
    try:
        pw = _decrypt(c["password_enc"])
    except Exception as e:
        return 0, f"Decifrazione password fallita: {e}"

    target = c.get("target_mailbox")
    if not target:
        return 0, "target_mailbox mancante"

    # credenziali webmail per APPEND su Stalwart
    try:
        webmail_secs = json.load(open(WEBMAIL_SECRETS))
        delivery_pw = webmail_secs.get(target)
    except Exception:
        delivery_pw = None
    if not delivery_pw:
        return 0, f"Nessuna app-password webmail per {target}. Esegui il provisioning."

    try:
        M = imaplib.IMAP4_SSL(c["imap_host"], int(c["imap_port"]))
        M.login(c["email"], pw)
    except Exception as e:
        return 0, f"Login IMAP fallito: {e}"

    try:
        M.select(c.get("inbox_folder", "INBOX"))

        # controlla UIDVALIDITY
        typ, status_data = M.status(c.get("inbox_folder", "INBOX"), "(UIDVALIDITY MESSAGES)")
        uid_validity = None
        if typ == "OK":
            import re
            m = re.search(r"UIDVALIDITY (\d+)", status_data[0].decode())
            if m:
                uid_validity = int(m.group(1))

        last_uid = c.get("last_uid", 0)
        # se UIDVALIDITY cambiata, ricomincia da zero
        if uid_validity and uid_validity != c.get("uid_validity") and c.get("uid_validity"):
            last_uid = 0

        # cerca UID > last_uid
        search_criteria = f"UID {last_uid + 1}:*" if last_uid > 0 else "ALL"
        typ, uid_data = M.uid("SEARCH", None, search_criteria)
        if typ != "OK" or not uid_data[0]:
            M.logout()
            return 0, None

        raw_uids = uid_data[0].split()
        if not raw_uids:
            M.logout()
            return 0, None

        # limita a 50 mail per ciclo
        raw_uids = raw_uids[-50:]
        delivered = 0
        max_uid = last_uid

        for uid_bytes in raw_uids:
            uid_int = int(uid_bytes)
            if uid_int <= last_uid:
                continue
            typ, msg_data = M.uid("FETCH", uid_bytes, "(RFC822)")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw_msg = msg_data[0][1]
            if isinstance(raw_msg, str):
                raw_msg = raw_msg.encode()

            ok = _deliver_to_stalwart(target, delivery_pw, raw_msg, c["email"])
            if ok:
                delivered += 1
                max_uid = max(max_uid, uid_int)

        M.logout()

        c["last_uid"] = max_uid
        if uid_validity:
            c["uid_validity"] = uid_validity

        return delivered, None

    except Exception as e:
        try:
            M.logout()
        except Exception:
            pass
        return 0, str(e)


def _deliver_to_stalwart(target_mailbox, app_pw, raw_msg, source_email):
    """IMAP APPEND nella cartella External del destinatario su Stalwart."""
    try:
        D = imaplib.IMAP4_SSL(IMAP_DELIVERY_HOST, 993)
        D.login(target_mailbox, app_pw)

        # Crea cartella External se non esiste
        folder = "INBOX.External"
        D.create(folder)  # silenzioso se già esiste

        import imaplib
        # Aggiunge X-Imported-From header
        msg = _email_mod.message_from_bytes(raw_msg)
        if not msg.get("X-Imported-From"):
            try:
                raw_msg = f"X-Imported-From: {source_email}\r\n".encode() + raw_msg
            except Exception:
                pass

        D.append(folder, None, imaplib.Time2Internaldate(time.time()), raw_msg)
        D.logout()
        return True
    except Exception as e:
        frappe.logger().error(f"[mail_connectors] delivery fallita per {target_mailbox}: {e}")
        return False
