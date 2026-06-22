"""
Legacy Digitale — Thanatos Intel.

Flusso:
  1. Cliente designa delegato da /portal/legacy → insert Client Legacy Delegate (status=Active)
  2. Sistema invia email al delegato con link /portal/legacy/request?token=<invite_token>
  3. Delegato carica documento e invia richiesta → status=Requested
  4. Staff approva (desk) → status=Granted → sistema genera access_token e invia link
  5. Delegato accede a /portal/legacy/view?token=<access_token> (read-only)
  6. Scheduler: dopo waiting_hours da requested_at → auto-grant se non già fatto
  7. Scheduler: dopo access_expires_at → status=Expired
"""
import frappe
from frappe import _
from frappe.utils import now_datetime, add_days, add_to_date


# ── helpers ──────────────────────────────────────────────────────────────────

def _my_client():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login richiesto."), frappe.PermissionError)
    c = frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")
    if not c:
        frappe.throw(_("Profilo cliente non trovato."))
    return c


def _get_by_invite_token(token):
    name = frappe.db.get_value("Client Legacy Delegate", {"invite_token": token}, "name")
    if not name:
        frappe.throw(_("Link non valido o scaduto."))
    return frappe.get_doc("Client Legacy Delegate", name)


def _get_by_access_token(token):
    name = frappe.db.get_value(
        "Client Legacy Delegate",
        {"access_token": token, "status": "Granted"},
        "name",
    )
    return frappe.get_doc("Client Legacy Delegate", name) if name else None


# ── client actions ────────────────────────────────────────────────────────────

@frappe.whitelist()
def add_delegate(delegate_name: str, delegate_email: str, relationship: str = "",
                 delegate_phone: str = "", waiting_hours: int = 72, access_days: int = 30) -> dict:
    client = _my_client()
    existing = frappe.db.get_value(
        "Client Legacy Delegate",
        {"client": client, "delegate_email": delegate_email, "status": ["!=", "Revoked"]},
        "name",
    )
    if existing:
        frappe.throw(_("Questo indirizzo email è già registrato come delegato."))

    doc = frappe.get_doc({
        "doctype": "Client Legacy Delegate",
        "client": client,
        "delegate_name": delegate_name,
        "delegate_email": delegate_email,
        "relationship": relationship,
        "delegate_phone": delegate_phone,
        "waiting_hours": waiting_hours,
        "access_days": access_days,
        "status": "Active",
        "invite_sent_at": now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    _send_invite(doc)
    return {"name": doc.name, "invite_token": doc.invite_token}


@frappe.whitelist()
def revoke_delegate(delegate_name_id: str) -> dict:
    client = _my_client()
    doc = frappe.get_doc("Client Legacy Delegate", delegate_name_id)
    if doc.client != client:
        frappe.throw(_("Non autorizzato."), frappe.PermissionError)
    doc.status = "Revoked"
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def my_delegates() -> list:
    client = _my_client()
    return frappe.get_all(
        "Client Legacy Delegate",
        filters={"client": client, "status": ["!=", "Revoked"]},
        fields=["name", "delegate_name", "delegate_email", "relationship",
                "status", "invite_sent_at", "requested_at", "granted_at", "access_expires_at"],
        order_by="creation desc",
    )


# ── delegate request flow ────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_invite_info(token: str) -> dict:
    doc = _get_by_invite_token(token)
    if doc.status == "Revoked":
        frappe.throw(_("Questo invito è stato revocato."))
    client_name = frappe.db.get_value("Investigation Client", doc.client, "client_name") or doc.client
    return {
        "delegate_name": doc.delegate_name,
        "client_display": client_name,
        "status": doc.status,
    }


@frappe.whitelist(allow_guest=True)
def submit_request(token: str, document_type: str = "", delegate_notes: str = "",
                   document_file: str = "") -> dict:
    doc = _get_by_invite_token(token)
    if doc.status not in ("Active", "Requested"):
        frappe.throw(_("Richiesta non consentita in questo stato."))

    doc.status = "Requested"
    doc.requested_at = now_datetime()
    doc.document_type = document_type
    doc.delegate_notes = delegate_notes
    if document_file:
        doc.document_file = document_file
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    _notify_staff_request(doc)
    return {"ok": True, "message": _("Richiesta inviata. Riceverà una notifica quando l'accesso sarà attivato.")}


# ── token-based view ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_legacy_view(token: str) -> dict:
    doc = _get_by_access_token(token)
    if not doc:
        return {"valid": False}
    if doc.access_expires_at and now_datetime() > doc.access_expires_at:
        doc.status = "Expired"
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"valid": False, "expired": True}

    client_name = frappe.db.get_value("Investigation Client", doc.client, "client_name") or doc.client

    cases = frappe.get_all(
        "Investigation Case",
        filters={"client": doc.client},
        fields=["name", "title", "status", "case_type", "creation", "modified"],
        order_by="creation desc",
        limit=50,
    )

    vault_items = frappe.get_all(
        "Client Vault Item",
        filters={"client": doc.client},
        fields=["name", "item_type", "label", "expires_at", "creation"],
        order_by="creation desc",
        limit=100,
    )

    return {
        "valid": True,
        "client_display": client_name,
        "delegate_name": doc.delegate_name,
        "access_expires_at": str(doc.access_expires_at),
        "cases": cases,
        "vault_items": vault_items,
    }


# ── scheduler ────────────────────────────────────────────────────────────────

def auto_grant_pending():
    """Attiva automaticamente gli accessi dopo waiting_hours da requested_at."""
    rows = frappe.db.sql("""
        SELECT name, requested_at, waiting_hours
        FROM `tabClient Legacy Delegate`
        WHERE status = 'Requested'
    """, as_dict=True)

    for r in rows:
        if not r.requested_at:
            continue
        threshold = add_to_date(r.requested_at, hours=int(r.waiting_hours or 72))
        if now_datetime() >= threshold:
            doc = frappe.get_doc("Client Legacy Delegate", r.name)
            doc.status = "Granted"
            doc.reviewed_by = "Administrator"
            doc.save(ignore_permissions=True)

    frappe.db.commit()


def expire_old_access():
    """Marca Expired gli accessi scaduti."""
    frappe.db.sql("""
        UPDATE `tabClient Legacy Delegate`
        SET status = 'Expired'
        WHERE status = 'Granted'
          AND access_expires_at IS NOT NULL
          AND access_expires_at < NOW()
    """)
    frappe.db.commit()


# ── internal helpers ──────────────────────────────────────────────────────────

def _send_invite(doc):
    client_name = frappe.db.get_value("Investigation Client", doc.client, "client_name") or doc.client
    url = f"https://thanatos.agency/portal/legacy/request?token={doc.invite_token}"
    try:
        frappe.sendmail(
            recipients=[doc.delegate_email],
            subject=f"Sei stato designato come delegato Legacy — {client_name} | Thanatos Intel",
            message=f"""
<p>Gentile {doc.delegate_name},</p>
<p>Il nostro cliente <strong>{client_name}</strong> ti ha designato come
<em>Delegato di Successione</em> per le sue pratiche Thanatos Intel.</p>
<p>Se dovessi averne necessità (ad esempio in caso di decesso o incapacità del cliente),
potrai richiedere l'accesso in sola lettura ai fascicoli tramite il link seguente:</p>
<p><a href="{url}" style="background:#C8A96E;color:#0A0E1A;padding:12px 24px;
text-decoration:none;display:inline-block">Accedi alla pagina di richiesta →</a></p>
<p>Non è richiesta alcuna azione immediata. Conserva questa email in luogo sicuro.</p>
<p style="color:#666;font-size:12px">Thanatos Intel · uso riservato</p>
""",
            now=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Legacy invite email failed")


def _notify_staff_request(doc):
    client_name = frappe.db.get_value("Investigation Client", doc.client, "client_name") or doc.client
    desk_url = f"https://thanatos.agency/app/client-legacy-delegate/{doc.name}"
    try:
        frappe.sendmail(
            recipients=["cases@thanatos.agency"],
            subject=f"[LEGACY] Richiesta accesso da {doc.delegate_name} per {client_name}",
            message=f"""
<p>Nuova richiesta di accesso Legacy Digitale:</p>
<table style="border-collapse:collapse;width:100%">
<tr><td style="padding:6px 12px;border:1px solid #ddd"><b>Cliente</b></td>
    <td style="padding:6px 12px;border:1px solid #ddd">{client_name}</td></tr>
<tr><td style="padding:6px 12px;border:1px solid #ddd"><b>Delegato</b></td>
    <td style="padding:6px 12px;border:1px solid #ddd">{doc.delegate_name} &lt;{doc.delegate_email}&gt;</td></tr>
<tr><td style="padding:6px 12px;border:1px solid #ddd"><b>Relazione</b></td>
    <td style="padding:6px 12px;border:1px solid #ddd">{doc.relationship or '—'}</td></tr>
<tr><td style="padding:6px 12px;border:1px solid #ddd"><b>Tipo documento</b></td>
    <td style="padding:6px 12px;border:1px solid #ddd">{doc.document_type or '—'}</td></tr>
<tr><td style="padding:6px 12px;border:1px solid #ddd"><b>Note delegato</b></td>
    <td style="padding:6px 12px;border:1px solid #ddd">{doc.delegate_notes or '—'}</td></tr>
<tr><td style="padding:6px 12px;border:1px solid #ddd"><b>Attesa automatica</b></td>
    <td style="padding:6px 12px;border:1px solid #ddd">{doc.waiting_hours} ore</td></tr>
</table>
<p><a href="{desk_url}">Revisiona nel desk →</a></p>
<p style="color:#888;font-size:12px">Accesso sarà attivato automaticamente dopo {doc.waiting_hours}h
se non approvato/rifiutato manualmente.</p>
""",
            now=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Legacy staff notification failed")
