"""Gestione caselle mail (Stalwart mailmx) da dentro Thanatos.

Crea / elenca / reset password / elimina mailbox via Stalwart admin API.
Creds da site_config (mmos_stalwart_url/admin_user/admin_pass) — mai inline.
La webmail vera è l'app Frappe `mail` su /mail (JMAP → Stalwart).

Accesso: solo ruoli amministrativi gestiscono tutte le caselle; un utente
può resettare solo la propria.
"""
import frappe
from frappe import _

ADMIN_ROLES = {"System Manager", "Investigation Manager", "Mail Admin"}


def _cfg():
    url = frappe.conf.get("mmos_stalwart_url")
    user = frappe.conf.get("mmos_stalwart_admin_user", "admin")
    pwd = frappe.conf.get("mmos_stalwart_admin_pass")
    if not (url and pwd):
        frappe.throw(_("Stalwart non configurato (mmos_stalwart_url / admin_pass)."))
    return {"url": url.rstrip("/"), "auth": (user, pwd)}


def _is_admin():
    return bool(set(frappe.get_roles()) & ADMIN_ROLES)


def _guard_admin():
    if not _is_admin():
        frappe.throw(_("Non autorizzato alla gestione caselle."), frappe.PermissionError)


def _bcrypt(password):
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


@frappe.whitelist()
def list_mailboxes():
    """Elenca le caselle (principal type=individual) su Stalwart."""
    _guard_admin()
    import requests
    cfg = _cfg()
    r = requests.get(f"{cfg['url']}/api/principal",
                     params={"types": "individual", "page": 1, "limit": 500},
                     auth=cfg["auth"], timeout=15)
    r.raise_for_status()
    data = r.json().get("data", r.json())
    items = data.get("items", data) if isinstance(data, dict) else data
    out = []
    for p in (items or []):
        if isinstance(p, str):
            out.append({"name": p})
        else:
            out.append({
                "name": p.get("name"),
                "description": p.get("description"),
                "emails": p.get("emails") or [],
                "quota": p.get("quota"),
            })
    return out


@frappe.whitelist(methods=["POST"])
def create_mailbox(email, password, display_name=None, quota=0):
    """Crea una nuova casella su Stalwart."""
    _guard_admin()
    email = (email or "").strip().lower()
    if "@" not in email:
        frappe.throw(_("Email non valida (serve la forma utente@dominio)."))
    if not password or len(password) < 8:
        frappe.throw(_("Password troppo corta (min. 8)."))
    import requests
    cfg = _cfg()
    payload = {
        "type": "individual",
        "name": email,
        "description": display_name or email,
        "secrets": [_bcrypt(password)],
        "emails": [email],
        "roles": ["user"],
    }
    if int(quota or 0) > 0:
        payload["quota"] = int(quota)
    r = requests.post(f"{cfg['url']}/api/principal", auth=cfg["auth"], json=payload, timeout=15)
    if r.status_code not in (200, 201, 204):
        frappe.throw(_("Stalwart create error {0}: {1}").format(r.status_code, r.text[:300]))
    return {"ok": True, "email": email}


@frappe.whitelist(methods=["POST"])
def set_password(email, password):
    """Reset password di una casella. Admin: chiunque; utente: solo la propria."""
    email = (email or "").strip().lower()
    if not _is_admin():
        own = (frappe.db.get_value("User Settings", {"user": frappe.session.user}, "username")
               or frappe.session.user)
        if email != (own or "").lower():
            frappe.throw(_("Puoi resettare solo la tua casella."), frappe.PermissionError)
    if not password or len(password) < 8:
        frappe.throw(_("Password troppo corta (min. 8)."))
    import requests
    cfg = _cfg()
    r = requests.patch(f"{cfg['url']}/api/principal/{email}", auth=cfg["auth"],
                       json=[{"action": "set", "field": "secrets", "value": [_bcrypt(password)]}],
                       timeout=15)
    if r.status_code not in (200, 204):
        frappe.throw(_("Stalwart patch error {0}: {1}").format(r.status_code, r.text[:300]))
    return {"ok": True, "email": email}


@frappe.whitelist(methods=["POST"])
def delete_mailbox(email):
    """Elimina una casella (irreversibile lato Stalwart)."""
    _guard_admin()
    email = (email or "").strip().lower()
    import requests
    cfg = _cfg()
    r = requests.delete(f"{cfg['url']}/api/principal/{email}", auth=cfg["auth"], timeout=15)
    if r.status_code not in (200, 204):
        frappe.throw(_("Stalwart delete error {0}: {1}").format(r.status_code, r.text[:300]))
    return {"ok": True, "email": email}
