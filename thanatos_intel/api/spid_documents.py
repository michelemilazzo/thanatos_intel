# -*- coding: utf-8 -*-
"""API flusso SPID self-service: l'operatore RICHIEDE documenti SPID-gated per una
pratica; il CLIENTE li recupera autenticandosi LUI con SPID e li carica in pratica.
Mai le credenziali SPID del cliente. Upload -> Investigation Evidence (catena di
custodia) + Consent Record.
"""
import os
import hashlib
import frappe
from frappe import _
from frappe.utils import now_datetime

from thanatos_intel.osint.spid_catalog import SPID_DOCS, doc_label, doc_guidance

_MAX_FILE_MB = 50
_ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic",
                ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv", ".zip", ".p7m"}


def _sha256(content):
    h = hashlib.sha256()
    h.update(content)
    return h.hexdigest()


def _validate_file(filename, content):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in _ALLOWED_EXT:
        frappe.throw(_("Tipo file non consentito: {0}").format(ext), frappe.ValidationError)
    if len(content) / (1024 * 1024) > _MAX_FILE_MB:
        frappe.throw(_("File troppo grande (max {0} MB).").format(_MAX_FILE_MB),
                     frappe.ValidationError)


def _guess_type(filename):
    low = (filename or "").lower()
    if low.endswith((".pdf", ".doc", ".docx", ".p7m", ".txt", ".csv")):
        return "Document"
    if low.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic")):
        return "Photo"
    return "File"


def _client_for_case(case):
    return frappe.db.get_value("Investigation Case", case, "client")


@frappe.whitelist(methods=["POST"])
def request_spid_documents(case, doc_keys, notes=""):
    """OPERATORE: crea le richieste di documenti SPID per una pratica.
    doc_keys: lista o stringa separata da virgole di chiavi del catalogo."""
    user = frappe.session.user
    from thanatos_intel.permissions import is_full_access
    if not (is_full_access(user) or "Investigator" in frappe.get_roles(user)):
        frappe.throw(_("Non autorizzato."), frappe.PermissionError)
    if not frappe.db.exists("Investigation Case", case):
        frappe.throw(_("Pratica non trovata."))

    if isinstance(doc_keys, str):
        try:
            import json
            doc_keys = json.loads(doc_keys)
        except Exception:
            doc_keys = [k.strip() for k in doc_keys.split(",")]
    keys = [k for k in (doc_keys or []) if k in SPID_DOCS]
    if not keys:
        frappe.throw(_("Nessun tipo documento valido. Disponibili: {0}").format(
            ", ".join(SPID_DOCS.keys())))

    return _create_spid_requests(case, keys, notes=notes, requested_by=user)


def _create_spid_requests(case, keys, notes="", requested_by=None):
    """Crea le richieste (uso interno: chiamato dal gate HTTP e dal webhook WA)."""
    keys = [k for k in (keys or []) if k in SPID_DOCS]
    if not keys:
        return {"created": [], "count": 0}
    client = _client_for_case(case)
    created = []
    for k in keys:
        doc = frappe.get_doc({
            "doctype": "SPID Document Request",
            "investigation_case": case,
            "client": client,
            "doc_key": k,
            "doc_label": doc_label(k),
            "status": "Richiesto",
            "requested_by": requested_by or frappe.session.user,
            "requested_on": now_datetime(),
            "notes": notes or "",
        })
        doc.insert(ignore_permissions=True)
        created.append(doc.name)
    frappe.db.commit()
    _notify_client(case, client, keys)
    return {"created": created, "count": len(created)}


def _notify_client(case, client, keys):
    """Avvisa il cliente (email best-effort) che ci sono documenti da caricare."""
    try:
        pu = frappe.db.get_value("Investigation Client", client, "platform_user") if client else None
        if not pu:
            return
        labels = "".join(f"<li>{doc_label(k)}</li>" for k in keys)
        url = frappe.utils.get_url("/portal/documenti-spid")
        frappe.sendmail(
            recipients=[pu],
            subject=f"[Thanatos] Documenti da caricare — pratica {case}",
            message=(f"Gentile cliente,<br>per la pratica <b>{case}</b> ti chiediamo di "
                     f"recuperare e caricare i seguenti documenti:<ul>{labels}</ul>"
                     f"Puoi caricarli in sicurezza qui: <a href='{url}'>{url}</a><br><br>"
                     "I documenti li recuperi TU autenticandoti con SPID sui siti ufficiali "
                     "(ti guidiamo passo-passo nel portale). Noi non ti chiediamo mai le "
                     "credenziali SPID."),
            now=False,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SPID notify client")


def my_spid_requests(user=None):
    """Richieste SPID del cliente loggato (per la pagina portale), con guida."""
    user = user or frappe.session.user
    from thanatos_intel.permissions import is_full_access, visible_case_names
    if is_full_access(user):
        rows = frappe.get_all("SPID Document Request",
                              fields=["name", "investigation_case", "doc_key", "doc_label", "status", "help_requested"],
                              order_by="creation desc", limit=100)
    else:
        names = visible_case_names(user) or []
        if not names:
            return []
        rows = frappe.get_all("SPID Document Request",
                              filters={"investigation_case": ["in", names]},
                              fields=["name", "investigation_case", "doc_key", "doc_label", "status", "help_requested"],
                              order_by="creation desc", limit=100)
    for r in rows:
        g = doc_guidance(r["doc_key"])
        r["ente"] = g["ente"]
        r["url"] = g["url"]
        r["istruzioni"] = g["istruzioni"]
        r["steps"] = g.get("steps", [])
    return rows


@frappe.whitelist(methods=["POST"])
def submit_spid_document(request, consent=0):
    """CLIENTE: carica il documento SPID recuperato per una richiesta.
    Richiede consenso esplicito. Crea Evidence (custodia) + Consent Record."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)
    if not frappe.db.exists("SPID Document Request", request):
        frappe.throw(_("Richiesta non trovata."))
    req = frappe.get_doc("SPID Document Request", request)

    # row-level: la pratica della richiesta dev'essere visibile al cliente
    from thanatos_intel.permissions import is_full_access, visible_case_names
    if not is_full_access(user):
        if req.investigation_case not in (visible_case_names(user) or []):
            frappe.throw(_("Accesso negato a questa richiesta."), frappe.PermissionError)

    if str(consent) not in ("1", "true", "True", "on"):
        frappe.throw(_("È necessario prestare il consenso prima di caricare il documento."),
                     frappe.ValidationError)

    files = frappe.request.files.getlist("file") if frappe.request.files else []
    if not files:
        files = frappe.request.files.getlist("files") if frappe.request.files else []
    if not files:
        frappe.throw(_("Nessun file caricato."))
    f = files[0]
    content = f.read()
    _validate_file(f.filename, content)
    sha = _sha256(content)
    case = req.investigation_case

    file_doc = frappe.get_doc({
        "doctype": "File", "file_name": f.filename, "is_private": 1, "content": content,
        "attached_to_doctype": "Investigation Case", "attached_to_name": case,
    })
    file_doc.save(ignore_permissions=True)

    ev = frappe.get_doc({
        "doctype": "Investigation Evidence",
        "investigation_case": case,
        "evidence_name": f"{req.doc_label} — {f.filename}",
        "evidence_type": _guess_type(f.filename),
        "attached_file": file_doc.file_url,
        "hash_value": sha,
        "custody_status": "Received",
        "source": "Cliente (self-service SPID)",
        "acquired_by": user,
        "notes": f"Documento SPID «{req.doc_label}» recuperato e caricato dal cliente "
                 f"{user} il {now_datetime():%Y-%m-%d %H:%M} (richiesta {req.name}).",
    })
    ev.insert(ignore_permissions=True)

    frappe.get_doc({
        "doctype": "Chain Of Custody Event", "event_type": "Created",
        "related_reference": ev.name,
        "notes": f"Upload cliente SPID {f.filename} | SHA256={sha} | user={user} | req={req.name}",
    }).insert(ignore_permissions=True)

    consent_doc = frappe.get_doc({
        "doctype": "Consent Record",
        "client": req.client,
        "data_subject": frappe.db.get_value("Investigation Client", req.client, "client_name") or user,
        "email": user,
        "purpose": f"Recupero e conferimento documento «{req.doc_label}» per pratica {case}"[:140],
        "legal_basis": "Consenso",
        "channel": "portale SPID self-service",
        "given_on": now_datetime(),
        "evidence": file_doc.file_url,
    })
    consent_doc.insert(ignore_permissions=True)

    req.status = "Caricato"
    req.consent_given = 1
    req.consent_on = now_datetime()
    req.consent_record = consent_doc.name
    req.evidence = ev.name
    req.sha256 = sha
    req.save(ignore_permissions=True)
    frappe.db.commit()

    try:
        from thanatos_intel.workflow.notify import _email_operator
        _email_operator(case,
                        subject=f"[Thanatos] Cliente ha caricato «{req.doc_label}» — {case}",
                        message=(f"Il cliente ha caricato il documento SPID "
                                 f"<b>{req.doc_label}</b> nella pratica <b>{case}</b> "
                                 f"(reperto {ev.name}, SHA256 {sha[:16]}…), con consenso registrato."),
                        from_user=user)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SPID submit notify")

    return {"ok": True, "evidence": ev.name, "status": "Caricato"}


@frappe.whitelist(methods=["POST"])
def request_spid_help(request, note=""):
    """CLIENTE: chiede assistenza per una richiesta (non sa usare SPID / non ce l'ha).
    Marca la richiesta e avvisa l'operatore, che lo ricontatta."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)
    if not frappe.db.exists("SPID Document Request", request):
        frappe.throw(_("Richiesta non trovata."))
    req = frappe.get_doc("SPID Document Request", request)
    from thanatos_intel.permissions import is_full_access, visible_case_names
    if not is_full_access(user) and req.investigation_case not in (visible_case_names(user) or []):
        frappe.throw(_("Accesso negato."), frappe.PermissionError)
    req.help_requested = 1
    req.help_note = (note or "")[:500]
    req.save(ignore_permissions=True)
    frappe.db.commit()
    try:
        from thanatos_intel.workflow.notify import _email_operator
        _email_operator(
            req.investigation_case,
            subject=f"[Thanatos] Cliente chiede assistenza SPID — {req.doc_label}",
            message=(f"Il cliente ha chiesto aiuto per recuperare <b>{req.doc_label}</b> "
                     f"(pratica <b>{req.investigation_case}</b>).<br>Nota del cliente: "
                     f"{(note or '-')}<br><br>Contattalo per assisterlo, oppure valuta "
                     "delega SPID / procura / recupero alternativo."),
            from_user=user)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SPID help notify")
    try:
        from thanatos_intel.ingest.wa_bot import notify_operators
        notify_operators(
            f"🆘 *Assistenza SPID* — il cliente non riesce a recuperare «{req.doc_label}» "
            f"(pratica {req.investigation_case}).\nNota: {note or '—'}\nRicontattalo per "
            "aiutarlo, o valuta mandato/procura.")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SPID help wa")
    return {"ok": True}
