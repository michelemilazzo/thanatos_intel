"""Provisioning caselle webmail Thanatos (solo System Manager).

Per un utente: crea (se manca) la casella Stalwart @thanatos.agency e le associa una
APP-PASSWORD dedicata alla webmail, scritta nello store condiviso letto dal plugin SSO
di Roundcube (/etc/thanatos/webmail_secrets.json). Nessuna chiave globale.

Le credenziali admin Stalwart si leggono dal vault admin_settings.json (sezione mailserver).
ESECUZIONE REALE (dry_run=0) crea credenziali sul mailserver: operazione sensibile, riservata
allo staff dal pannello desk.
"""
import json
import os
import secrets as _secrets
from urllib.parse import quote

import frappe
import requests

SECRETS_FILE = "/etc/thanatos/webmail_secrets.json"
VAULT = "/home/frappe/.secrets/admin_settings.json"
DOMAIN = "thanatos.agency"


def _guard():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Solo un amministratore può fare provisioning delle caselle.", frappe.PermissionError)


def _stalwart():
    with open(VAULT) as f:
        ms = json.load(f).get("mailserver", {})
    url = (ms.get("url") or ms.get("admin_url") or "http://10.10.0.3:8080").rstrip("/")
    user = ms.get("admin_user") or ms.get("user") or "admin"
    pw = ms.get("admin_password") or ms.get("password")
    if not pw:
        frappe.throw("Credenziali admin Stalwart non trovate nel vault.")
    return url, (user, pw)


def _bcrypt(pw):
    try:
        import bcrypt
        return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()
    except Exception:
        from passlib.hash import bcrypt as _b
        return _b.using(rounds=12).hash(pw)


def _account_exists(url, auth, mailbox):
    r = requests.get(f"{url}/api/principal/{quote(mailbox, safe='')}", auth=auth, timeout=15)
    if r.status_code != 200:
        return False
    try:
        j = r.json()
    except Exception:
        return False
    # Stalwart risponde 200 anche se manca, con {"error":"notFound"}
    return bool(j.get("data")) and not j.get("error")


def _write_secret(mailbox, app_pw):
    data = {}
    if os.path.exists(SECRETS_FILE):
        try:
            data = json.load(open(SECRETS_FILE)) or {}
        except Exception:
            data = {}
    data[mailbox] = app_pw
    tmp = SECRETS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, SECRETS_FILE)
    try:
        os.chmod(SECRETS_FILE, 0o640)
    except Exception:
        pass


def _write_vault(mailbox, password):
    """Scrive la password nel vault (mostrato da /secrets) per tenere tutto in sync."""
    vp = "/home/frappe/.secrets/integrations.json"
    try:
        v = json.load(open(vp))
        sm = v.setdefault("stalwart_mailboxes", {"label": "Caselle Stalwart", "category": "mail", "fields": {}})
        key = mailbox.replace("@", "_").replace(".", "_")
        sm.setdefault("fields", {})[key] = {"label": mailbox, "type": "password", "value": password}
        json.dump(v, open(vp, "w"), indent=2)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "mail_provisioning _write_vault")


@frappe.whitelist()
def preview(user=None, mailbox=None):
    """Dry-run: mostra cosa farebbe il provisioning, senza creare nulla."""
    _guard()
    mailbox = (mailbox or "").strip().lower()
    if not mailbox.endswith("@" + DOMAIN):
        frappe.throw(f"La casella deve essere @{DOMAIN}.")
    url, auth = _stalwart()
    exists = _account_exists(url, auth, mailbox)
    webmail_enabled = mailbox in _enabled_set()
    return {
        "mailbox": mailbox, "user": user,
        "account_exists": exists,
        "will_create_account": not exists,
        "will_set_app_password": True,
        "already_webmail_enabled": webmail_enabled,
    }


def _enabled_set():
    try:
        return set((json.load(open(SECRETS_FILE)) or {}).keys())
    except Exception:
        return set()


@frappe.whitelist()
def list_enabled():
    _guard()
    return sorted(_enabled_set())


@frappe.whitelist()
def provision(user=None, mailbox=None, full_name=None, quota_mb=1024):
    """ESECUZIONE REALE: crea casella (se manca) + app-password webmail. Solo System Manager."""
    _guard()
    mailbox = (mailbox or "").strip().lower()
    if not mailbox.endswith("@" + DOMAIN):
        frappe.throw(f"La casella deve essere @{DOMAIN}.")
    url, auth = _stalwart()

    created = False
    if not _account_exists(url, auth, mailbox):
        main_pw = _secrets.token_urlsafe(16)
        payload = {
            "type": "individual", "name": mailbox,
            "secrets": [_bcrypt(main_pw)], "roles": ["user"],
            "emails": [mailbox],
            "description": full_name or "",
            "quota": int(quota_mb) * 1024 * 1024,
        }
        r = requests.post(f"{url}/api/principal", auth=auth, timeout=20, json=payload)
        if r.status_code >= 400:
            frappe.throw(f"Creazione casella fallita: {r.status_code} {r.text[:200]}")
        created = True

    # MODELLO single-managed: una sola password gestita per casella, identica per
    # password-login, SSO webmail e Email Account Frappe (Stalwart onora solo il 1o secret bcrypt).
    app_pw = _secrets.token_urlsafe(18)
    r = requests.patch(
        f"{url}/api/principal/{quote(mailbox, safe='')}", auth=auth, timeout=20,
        json=[{"action": "set", "field": "secrets", "value": [_bcrypt(app_pw)]}])
    if r.status_code >= 400:
        frappe.throw(f"Impostazione password fallita: {r.status_code} {r.text[:200]}")
    requests.get(f"{url}/api/reload", auth=auth, timeout=15)

    _write_secret(mailbox, app_pw)
    _write_vault(mailbox, app_pw)
    # propaga all'Email Account Frappe (se esiste)
    try:
        from thanatos_intel.mail_sync import sync_one
        sync_one(mailbox)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "provision sync_one")

    frappe.logger().info(f"[mail_provisioning] {mailbox} created={created} webmail-enabled by {frappe.session.user}")
    return {"mailbox": mailbox, "account_created": created, "webmail_enabled": True}
import json, os, secrets as _secrets
from urllib.parse import quote
import requests

APP_VAULT_KEY = "stalwart_app_passwords"


def _appsec(label, apppw):
    return "$app$" + label + "$" + _bcrypt(apppw)


def _label_of(sec):
    parts = str(sec).split("$")
    return parts[2] if str(sec).startswith("$app$") and len(parts) > 3 else None


def _get_secrets(url, auth, mailbox):
    r = requests.get(f"{url}/api/principal/{quote(mailbox, safe='')}", auth=auth, timeout=15)
    if r.status_code == 200 and (r.json().get("data")):
        return r.json()["data"].get("secrets") or []
    return []


def _set_secrets(url, auth, mailbox, secs):
    r = requests.patch(f"{url}/api/principal/{quote(mailbox, safe='')}", auth=auth, timeout=20,
                       json=[{"action": "set", "field": "secrets", "value": secs}])
    if r.status_code >= 400:
        frappe.throw(f"Stalwart: {r.status_code} {r.text[:200]}")
    requests.get(f"{url}/api/reload", auth=auth, timeout=15)


def _app_vault_write(mailbox, label, apppw):
    vp = "/home/frappe/.secrets/integrations.json"
    try:
        v = json.load(open(vp))
        s = v.setdefault(APP_VAULT_KEY, {"label": "App-password caselle (client esterni)", "category": "mail", "fields": {}})
        k = mailbox.replace("@", "_").replace(".", "_") + "__" + label
        s.setdefault("fields", {})[k] = {"label": f"{mailbox} · {label}", "type": "password", "value": apppw}
        json.dump(v, open(vp, "w"), indent=2)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "app_vault_write")


def _app_vault_del(mailbox, label):
    vp = "/home/frappe/.secrets/integrations.json"
    try:
        v = json.load(open(vp))
        k = mailbox.replace("@", "_").replace(".", "_") + "__" + label
        (v.get(APP_VAULT_KEY, {}).get("fields", {})).pop(k, None)
        json.dump(v, open(vp, "w"), indent=2)
    except Exception:
        pass


@frappe.whitelist()
def list_app_passwords(mailbox=None):
    _guard()
    mailbox = (mailbox or "").strip().lower()
    url, auth = _stalwart()
    labels = [l for l in (_label_of(s) for s in _get_secrets(url, auth, mailbox)) if l]
    return {"mailbox": mailbox, "labels": labels}


@frappe.whitelist()
def create_app_password(mailbox=None, label="outlook"):
    """Crea una app-password $app$ (client esterni: Outlook/Thunderbird/telefono).
    Coesiste con la password principale; non la rompe. Ritorna la pw UNA VOLTA."""
    _guard()
    mailbox = (mailbox or "").strip().lower()
    label = "".join(c for c in (label or "outlook") if c.isalnum() or c in "-_").lower()[:24] or "outlook"
    if not mailbox.endswith("@" + DOMAIN):
        frappe.throw(f"La casella deve essere @{DOMAIN}.")
    url, auth = _stalwart()
    secs = _get_secrets(url, auth, mailbox)
    if not secs:
        frappe.throw("Casella inesistente: crea/provisiona prima la casella.")
    secs = [s for s in secs if _label_of(s) != label]  # sostituisci se stesso label
    apppw = _secrets.token_urlsafe(15)
    secs.append(_appsec(label, apppw))
    _set_secrets(url, auth, mailbox, secs)
    _app_vault_write(mailbox, label, apppw)
    return {"mailbox": mailbox, "label": label, "app_password": apppw,
            "imap": "mailmx.onekeyco.com  ·  993 SSL", "smtp": "mailmx.onekeyco.com  ·  587 STARTTLS"}


@frappe.whitelist()
def revoke_app_password(mailbox=None, label=None):
    _guard()
    mailbox = (mailbox or "").strip().lower()
    url, auth = _stalwart()
    secs = _get_secrets(url, auth, mailbox)
    new = [s for s in secs if _label_of(s) != label]
    if len(new) == len(secs):
        return {"mailbox": mailbox, "label": label, "status": "not-found"}
    _set_secrets(url, auth, mailbox, new)
    _app_vault_del(mailbox, label)
    return {"mailbox": mailbox, "label": label, "status": "revoked"}
