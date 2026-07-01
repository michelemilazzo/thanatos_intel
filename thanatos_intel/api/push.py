"""Web Push notifications (VAPID) per la PWA Thanatos Switchboard.

Chiavi VAPID in site_config:
  vapid_public_key   (base64url, share col frontend)
  vapid_private_key  (base64url, mai esposta)
  vapid_subject      (mailto: dell'admin, obbligatorio da RFC 8292)

Le subscriptions dei browser sono in DocType 'Push Subscription' (unica per
endpoint). Il record viene rimosso al primo 404/410 dal push service
(subscription revocata).
"""
import json
import frappe
from frappe import _
from frappe.utils import now_datetime


# ─── Frontend API ───────────────────────────────────────────────────────────

@frappe.whitelist()
def get_public_key():
    """Ritorna la VAPID public key da usare nel PushManager.subscribe."""
    key = frappe.local.conf.get("vapid_public_key")
    if not key:
        frappe.throw(_("Web Push non configurato (manca vapid_public_key)."))
    return {"public_key": key}


@frappe.whitelist()
def subscribe(endpoint, p256dh, auth, user_agent=None):
    """Registra una subscription per l'utente loggato. Idempotente sull'endpoint."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Login richiesto."), frappe.PermissionError)
    existing = frappe.db.get_value("Ops Push Subscription", {"endpoint": endpoint}, "name")
    if existing:
        doc = frappe.get_doc("Ops Push Subscription", existing)
        doc.p256dh = p256dh
        doc.auth = auth
        doc.user = frappe.session.user
        doc.user_agent = (user_agent or "")[:500]
        doc.last_seen = now_datetime()
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype": "Ops Push Subscription",
            "user": frappe.session.user,
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": (user_agent or "")[:500],
            "last_seen": now_datetime(),
        })
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": doc.name}


@frappe.whitelist()
def send_test_push():
    """Invia una push di test all'utente loggato (per verificare l'installazione)."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Login richiesto."), frappe.PermissionError)
    r = send_push_to_user(frappe.session.user,
                          "Thanatos Switchboard",
                          "Notifiche push attive ✓",
                          url="/ops/", tag="test-push")
    return r


@frappe.whitelist()
def unsubscribe(endpoint):
    if frappe.session.user == "Guest":
        return {"ok": True}
    name = frappe.db.get_value("Ops Push Subscription",
                               {"endpoint": endpoint, "user": frappe.session.user},
                               "name")
    if name:
        frappe.delete_doc("Ops Push Subscription", name, ignore_permissions=True, force=True)
        frappe.db.commit()
    return {"ok": True}


# ─── Server-side sender ─────────────────────────────────────────────────────

def send_push_to_user(user, title, body="", url="/ops/", tag=None,
                      lead=None, urgent=False):
    """Invia una notifica push a TUTTE le subscription attive di un utente.
    Non solleva errori (best-effort). Rimuove subscription revocate (404/410)."""
    return _send_to_subs(
        subs=frappe.get_all("Ops Push Subscription",
                            filters={"user": user},
                            fields=["name", "endpoint", "p256dh", "auth"]),
        payload={"title": title, "body": body, "url": url,
                 "tag": tag, "lead": lead, "urgent": bool(urgent)},
    )


def send_push_to_role(role, title, body="", url="/ops/", tag=None,
                      lead=None, urgent=False, exclude_users=None):
    """Invia una push a TUTTI gli utenti con un dato ruolo (che hanno subscribed)."""
    exclude = set(exclude_users or [])
    users = [u for u in frappe.get_all(
                "Has Role", filters={"role": role}, fields=["parent"], pluck="parent")
             if u not in exclude and u not in ("Guest", "Administrator")]
    if not users:
        return {"sent": 0}
    subs = frappe.get_all("Ops Push Subscription",
                          filters={"user": ["in", users]},
                          fields=["name", "endpoint", "p256dh", "auth"])
    return _send_to_subs(subs, {"title": title, "body": body, "url": url,
                                 "tag": tag, "lead": lead, "urgent": bool(urgent)})


def _send_to_subs(subs, payload):
    if not subs:
        return {"sent": 0, "revoked": 0}
    conf = frappe.local.conf
    priv = conf.get("vapid_private_key")
    subj = conf.get("vapid_subject") or "mailto:admin@thanatos.agency"
    if not priv:
        frappe.log_error("VAPID private key mancante — nessuna push inviata",
                         "push_api")
        return {"sent": 0, "revoked": 0, "error": "no vapid"}
    try:
        from pywebpush import webpush, WebPushException
    except Exception:
        frappe.log_error(frappe.get_traceback(), "push_api import")
        return {"sent": 0, "revoked": 0, "error": "pywebpush missing"}

    priv_pem = _b64url_to_pem(priv)
    sent, revoked = 0, 0
    body = json.dumps(payload, ensure_ascii=False)
    for s in subs:
        try:
            webpush(
                subscription_info={"endpoint": s.endpoint,
                                   "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                data=body,
                vapid_private_key=priv_pem,
                vapid_claims={"sub": subj},
                ttl=86400,
            )
            sent += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", 0)
            if code in (404, 410):
                try:
                    frappe.delete_doc("Ops Push Subscription", s.name,
                                      ignore_permissions=True, force=True)
                    revoked += 1
                except Exception:
                    pass
            else:
                frappe.log_error(f"push {code} on {s.endpoint[:60]}: {e}",
                                 "push_api")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "push_api send")
    frappe.db.commit()
    return {"sent": sent, "revoked": revoked}


def _b64url_to_pem(b64url):
    """pywebpush accetta la privata come PEM o come DER. Convertiamo la nostra
    ES256 (32-byte scalar in base64url) in un PEM PKCS8 fresco."""
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    pad = 4 - (len(b64url) % 4)
    raw = base64.urlsafe_b64decode(b64url + ("=" * pad if pad != 4 else ""))
    scalar = int.from_bytes(raw, "big")
    key = ec.derive_private_key(scalar, ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


# ─── Hook: quando arriva un nuovo Intel Lead Message inbound ────────────────

def on_new_inbound_message(lead_name, sender_name, preview):
    """Invocato da ingest/whatsapp.py quando arriva un messaggio inbound.
    Notifica gli operatori assegnati o, se non assegnato, tutti gli Investigator."""
    lead = frappe.db.get_value("Intel Lead", lead_name,
                               ["assigned_to", "source_name",
                                "source_identifier"], as_dict=True) or {}
    title = f"💬 {sender_name or lead.source_name or lead.source_identifier or 'Sconosciuto'}"
    body = (preview or "")[:140]
    url = "/ops/"
    if lead.assigned_to:
        send_push_to_user(lead.assigned_to, title, body, url=url,
                          tag=f"lead-{lead_name}", lead=lead_name)
    else:
        send_push_to_role("Investigator", title, body, url=url,
                          tag=f"lead-{lead_name}", lead=lead_name)
