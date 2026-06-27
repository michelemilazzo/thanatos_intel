"""Sincronizzazione credenziali caselle @thanatos.agency tra i sistemi:
Stalwart (auth) · vault integrations.json (/secrets) · Email Account Frappe · store SSO webmail.

Modello: la password si propaga AL MOMENTO DEL CAMBIO (no pull ciechi da vault potenzialmente vecchio).
- reconcile(): semina/aggiorna il vault leggendo le password FUNZIONANTI degli Email Account (quelle
  con cui Frappe invia/riceve davvero) → /secrets diventa reale e completo. Sicuro.
- sync_one(email): propaga la password del vault all'Email Account corrispondente (usato dai trigger
  console/pannello dopo un cambio).
"""
import json
import imaplib

import frappe

VAULT = "/home/frappe/.secrets/integrations.json"
DOMAIN = "thanatos.agency"


def _field_value(f):
    if isinstance(f, dict):
        return f.get("value")
    if isinstance(f, str):
        return f
    return None


def _guard():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Solo System Manager.", frappe.PermissionError)


def _key(email):
    return email.replace("@", "_").replace(".", "_")


def _load_vault():
    return json.load(open(VAULT))


def _save_vault(v):
    json.dump(v, open(VAULT, "w"), indent=2)


IMAP_HOST = "mailmx.onekeyco.com"


def _imap_ok(email, pw):
    if not pw:
        return False
    try:
        M = imaplib.IMAP4_SSL(IMAP_HOST, 993)
        M.login(email, pw)
        M.logout()
        return True
    except Exception:
        return False


def _ea_for(email):
    name = frappe.db.get_value("Email Account", {"email_id": email}, "name")
    return frappe.get_doc("Email Account", name) if name else None


@frappe.whitelist()
def reconcile():
    """Semina il vault dalle password reali degli Email Account @thanatos.agency.
    Non ritorna password (solo stato)."""
    _guard()
    v = _load_vault()
    sm = v.setdefault("stalwart_mailboxes", {"label": "Caselle Stalwart", "category": "mail", "fields": {}})
    flds = sm.setdefault("fields", {})
    report = []
    for ea in frappe.get_all("Email Account", filters={"email_id": ["like", "%@" + DOMAIN]},
                             fields=["name", "email_id"]):
        try:
            doc = frappe.get_doc("Email Account", ea.name)
            pw = doc.get_password("password", raise_exception=False)
        except Exception:
            pw = None
        if not pw:
            report.append({"mailbox": ea.email_id, "status": "no-password-in-frappe"})
            continue
        k = _key(ea.email_id)
        existing = _field_value(flds.get(k))
        if existing == pw:
            report.append({"mailbox": ea.email_id, "status": "already-in-vault"})
        else:
            flds[k] = {"label": ea.email_id, "type": "password", "value": pw}
            report.append({"mailbox": ea.email_id, "status": "seeded-to-vault"})
    _save_vault(v)
    return report


@frappe.whitelist()
def sync_one(email=None):
    """Propaga la password del vault all'Email Account corrispondente (dopo un cambio)."""
    email = (email or "").strip().lower()
    flds = _load_vault().get("stalwart_mailboxes", {}).get("fields", {})
    pw_target = _field_value(flds.get(_key(email)))
    if not pw_target:
        return {"mailbox": email, "status": "no-vault-pw"}
    ea = _ea_for(email)
    if not ea:
        return {"mailbox": email, "status": "no-email-account"}
    try:
        cur = ea.get_password("password", raise_exception=False)
    except Exception:
        cur = None
    if cur == pw_target:
        return {"mailbox": email, "status": "in-sync"}
    if getattr(ea, "enable_automatic_linking", 0) and not ea.enable_incoming:
        ea.enable_automatic_linking = 0
    ea.password = pw_target
    ea.save(ignore_permissions=True)
    frappe.db.commit()
    return {"mailbox": email, "status": "updated"}


@frappe.whitelist()
def status():
    """Salute per OGNI casella @thanatos.agency (lista reale da Stalwart): vault/Email Account/SSO/auth + uso + verdetto."""
    _guard()
    flds = _load_vault().get("stalwart_mailboxes", {}).get("fields", {})
    try:
        sso = set(json.load(open("/etc/thanatos/webmail_secrets.json")).keys())
    except Exception:
        sso = set()
    # Email Account per casella (con in/out)
    eas = {}
    for e in frappe.get_all("Email Account", filters={"email_id": ["like", "%@" + DOMAIN]},
                            fields=["name", "email_id", "enable_incoming", "enable_outgoing"]):
        eas[e.email_id] = e
    # lista REALE da Stalwart
    boxes = []
    try:
        from thanatos_intel.api.mail_provisioning import _stalwart
        from urllib.parse import quote  # noqa
        import requests
        url, auth = _stalwart()
        r = requests.get(url + "/api/principal", params={"types": "individual", "limit": 500}, auth=auth, timeout=20)
        items = (r.json().get("data") or {}).get("items") or r.json().get("data") or []
        for it in items:
            nm = it.get("name") or ""
            if nm.endswith("@" + DOMAIN):
                boxes.append(nm)
    except Exception:
        pass
    # unione con vault/EA per non perdere nulla
    boxes = sorted(set(boxes) | set(eas) | {b for b in (k.replace("_thanatos_agency", "@thanatos.agency")
                   for k in flds if k.endswith("_thanatos_agency")) if "@" in b})
    out = []
    for b in boxes:
        vpw = _field_value(flds.get(_key(b)))
        ea = eas.get(b)
        ea_pw = None
        if ea:
            try:
                ea_pw = frappe.get_doc("Email Account", ea.name).get_password("password", raise_exception=False)
            except Exception:
                ea_pw = None
        auth = _imap_ok(b, vpw) if vpw else False
        if not vpw:
            verdict = "NO-VAULT"
        elif not auth:
            verdict = "BROKEN"
        elif ea and ea_pw != vpw:
            verdict = "DRIFT"
        else:
            verdict = "OK"
        uso = []
        if ea:
            if ea.enable_incoming: uso.append("in")
            if ea.enable_outgoing: uso.append("out")
        if b in sso: uso.append("webmail/SSO")
        out.append({"mailbox": b, "in_vault": bool(vpw), "email_account": (ea.name if ea else "-"),
                    "ea_in_sync": (ea_pw == vpw) if ea else None, "webmail_sso": b in sso,
                    "auth_ok": auth, "uso": ", ".join(uso) or "—", "verdict": verdict})
    return out


@frappe.whitelist()
def heal():
    """Riallinea in sicurezza: se il vault autentica -> allinea l'Email Account al vault;
    se il vault e' rotto ma l'Email Account autentica -> semina il vault dall'Email Account."""
    _guard()
    fixed = []
    for row in status():
        b = row["mailbox"]
        if row["verdict"] == "DRIFT" and row["email_account"] != "-":
            r = sync_one(b)
            fixed.append({"mailbox": b, "action": "ea<-vault", "status": r.get("status")})
        elif row["verdict"] == "BROKEN" and row["email_account"] != "-":
            # il vault non autentica: prova a seminare dal Email Account (se questa autentica)
            try:
                ea_pw = frappe.get_doc("Email Account", row["email_account"]).get_password("password", raise_exception=False)
            except Exception:
                ea_pw = None
            if ea_pw and _imap_ok(b, ea_pw):
                v = _load_vault()
                v.setdefault("stalwart_mailboxes", {}).setdefault("fields", {})[_key(b)] = {
                    "label": b, "type": "password", "value": ea_pw}
                _save_vault(v)
                if b in (json.load(open("/etc/thanatos/webmail_secrets.json")) if __import__("os").path.exists("/etc/thanatos/webmail_secrets.json") else {}):
                    sp = "/etc/thanatos/webmail_secrets.json"
                    d = json.load(open(sp)); d[b] = ea_pw; json.dump(d, open(sp, "w"))
                fixed.append({"mailbox": b, "action": "vault<-ea (seed)", "status": "healed"})
            else:
                fixed.append({"mailbox": b, "action": "none", "status": "needs-manual-reset"})
    return {"fixed": fixed}
