"""Sincronizzazione credenziali caselle @thanatos.agency tra i sistemi:
Stalwart (auth) · vault integrations.json (/secrets) · Email Account Frappe · store SSO webmail.

Modello: la password si propaga AL MOMENTO DEL CAMBIO (no pull ciechi da vault potenzialmente vecchio).
- reconcile(): semina/aggiorna il vault leggendo le password FUNZIONANTI degli Email Account (quelle
  con cui Frappe invia/riceve davvero) → /secrets diventa reale e completo. Sicuro.
- sync_one(email): propaga la password del vault all'Email Account corrispondente (usato dai trigger
  console/pannello dopo un cambio).
"""
import json
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
    """Prospetto: per ogni casella @thanatos.agency, presenza in vault / Email Account / store SSO."""
    _guard()
    flds = _load_vault().get("stalwart_mailboxes", {}).get("fields", {})
    try:
        sso = set(json.load(open("/etc/thanatos/webmail_secrets.json")).keys())
    except Exception:
        sso = set()
    eas = {e.email_id: e.name for e in frappe.get_all("Email Account",
           filters={"email_id": ["like", "%@" + DOMAIN]}, fields=["name", "email_id"])}
    out = []
    boxes = set(eas) | {k.replace("_thanatos_agency", "@thanatos.agency") for k in flds if k.endswith("_thanatos_agency")}
    for b in sorted(boxes):
        out.append({"mailbox": b, "in_vault": _key(b) in flds,
                    "email_account": eas.get(b, "-"), "webmail_sso": b in sso})
    return out
