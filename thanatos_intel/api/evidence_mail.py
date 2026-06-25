"""Intake email come PROVA su una pratica (Investigation Case).

Il cliente inoltra/carica un file .eml (o .msg) di un'email ricevuta su Gmail/Outlook.
Il file viene parsato: mittente/destinatario/data/oggetto/corpo + allegati interni.
Si crea una Investigation Evidence (tipo Email) con hash SHA-256 dell'.eml originale
(integrità = prova certa), gli allegati diventano evidenze collegate, e una
Communication "Received" agganciata al caso per la timeline/console.
"""
import email
import hashlib
import os
from email import policy
from email.parser import BytesParser

import frappe
from frappe import _
from frappe.utils import now_datetime

_MAX_MB = 30
_ATT_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".doc", ".docx",
            ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".zip", ".mp4", ".mp3", ".wav"}


def _sha256(b):
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _guess_type(fn):
    low = (fn or "").lower()
    if low.endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic")):
        return "Photo"
    if low.endswith((".mp4", ".mov", ".mkv", ".webm")):
        return "Video"
    if low.endswith((".mp3", ".wav", ".ogg")):
        return "Audio"
    if low.endswith((".pdf", ".doc", ".docx")):
        return "Document"
    return "File"


def _check_access(case):
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)
    from thanatos_intel.permissions import is_full_access, visible_case_names
    user = frappe.session.user
    if not is_full_access(user) and case not in (visible_case_names(user) or []):
        frappe.throw(_("Accesso negato a questa pratica."), frappe.PermissionError)
    if not frappe.db.exists("Investigation Case", case):
        frappe.throw(_("Pratica non trovata."))
    return user


@frappe.whitelist(methods=["POST"])
def submit_email_evidence(case: str = "", note: str = ""):
    user = _check_access(case)
    files = frappe.request.files.getlist("files") if frappe.request.files else []
    if not files:
        return {"error": "no files"}

    results, errors = [], []
    for f in files:
        try:
            raw = f.read()
            if len(raw) / (1024 * 1024) > _MAX_MB:
                raise frappe.ValidationError(f"File troppo grande (max {_MAX_MB} MB)")
            ext = os.path.splitext(f.filename or "")[1].lower()
            if ext not in (".eml", ".msg"):
                raise frappe.ValidationError("Carica un file email .eml (o .msg).")
            res = _ingest_one(case, user, f.filename, raw, note)
            results.append(res)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"submit_email_evidence {f.filename}")
            errors.append({"name": f.filename, "error": str(e)[:200]})

    frappe.db.commit()
    if results:
        _notify(case, user, results)
    return {"case": case, "imported": results, "errors": errors, "count": len(results)}


def _parse_eml(raw):
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    hdr = {k: (msg[k] or "") for k in ("from", "to", "cc", "subject", "date")}
    text = ""
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
        if body is not None:
            text = body.get_content()
            if body.get_content_type() == "text/html":
                text = frappe.utils.strip_html(text)
    except Exception:
        text = ""
    atts = []
    try:
        for part in msg.iter_attachments():
            fn = part.get_filename()
            if not fn:
                continue
            payload = part.get_payload(decode=True)
            if payload:
                atts.append((fn, payload))
    except Exception:
        pass
    return hdr, (text or "").strip(), atts


def _ingest_one(case, user, filename, raw, note):
    sha = _sha256(raw)
    hdr, body, atts = ({}, "", [])
    if filename.lower().endswith(".eml"):
        hdr, body, atts = _parse_eml(raw)

    # 1) file .eml originale (la prova integra)
    eml_file = frappe.get_doc({
        "doctype": "File", "file_name": filename, "is_private": 1, "content": raw,
        "attached_to_doctype": "Investigation Case", "attached_to_name": case,
    })
    eml_file.save(ignore_permissions=True)

    subject = hdr.get("subject") or filename
    src = hdr.get("from") or ""
    meta_note = (
        f"PROVA EMAIL caricata dal cliente {user} il {now_datetime():%Y-%m-%d %H:%M}\n"
        f"Da: {src}\nA: {hdr.get('to','')}\nData: {hdr.get('date','')}\n"
        f"Oggetto: {subject}\nSHA-256(.eml): {sha}\n"
    )
    if note:
        meta_note += f"Nota cliente: {note}\n"

    ev = frappe.get_doc({
        "doctype": "Investigation Evidence",
        "investigation_case": case,
        "evidence_name": (subject or filename)[:140],
        "evidence_type": "Email",
        "attached_file": eml_file.file_url,
        "hash_value": sha,
        "custody_status": "Received",
        "source": src[:140],
        "acquisition_date": now_datetime(),
        "acquired_by": user if frappe.db.exists("User", user) else None,
        "notes": meta_note,
    })
    ev.insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "Chain Of Custody Event", "event_type": "Created",
                    "related_reference": ev.name,
                    "notes": f"Email evidence | SHA256={sha} | user={user} | file={filename}"}).insert(ignore_permissions=True)

    # 2) allegati interni → evidenze collegate
    att_names = []
    for fn, payload in atts:
        ext = os.path.splitext(fn)[1].lower()
        if ext not in _ATT_EXT:
            continue
        asha = _sha256(payload)
        af = frappe.get_doc({
            "doctype": "File", "file_name": fn, "is_private": 1, "content": payload,
            "attached_to_doctype": "Investigation Case", "attached_to_name": case,
        })
        af.save(ignore_permissions=True)
        aev = frappe.get_doc({
            "doctype": "Investigation Evidence", "investigation_case": case,
            "evidence_name": fn[:140], "evidence_type": _guess_type(fn),
            "attached_file": af.file_url, "hash_value": asha, "custody_status": "Received",
            "source": f"Allegato email da {src}"[:140], "acquisition_date": now_datetime(),
            "acquired_by": user if frappe.db.exists("User", user) else None,
            "notes": f"Allegato estratto dall'email «{subject}» (prova {ev.name}) | SHA-256={asha}",
        })
        aev.insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "Chain Of Custody Event", "event_type": "Created",
                        "related_reference": aev.name,
                        "notes": f"Email attachment | SHA256={asha} | parent={ev.name}"}).insert(ignore_permissions=True)
        att_names.append(fn)

    # 3) Communication "Received" per timeline/console
    try:
        comm = frappe.get_doc({
            "doctype": "Communication", "communication_type": "Communication",
            "communication_medium": "Email", "sent_or_received": "Received",
            "subject": f"[PROVA] {subject}"[:140],
            "content": frappe.utils.escape_html(body or "")[:50000] or "(corpo email non disponibile)",
            "sender": src[:140], "reference_doctype": "Investigation Case", "reference_name": case,
        })
        comm.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "submit_email_evidence communication")

    return {"evidence": ev.name, "subject": subject, "from": src,
            "attachments": att_names, "sha256": sha}


def _notify(case, user, results):
    try:
        from thanatos_intel.workflow.notify import _email_operator
        n = len(results)
        items = "".join(f"<li>{frappe.utils.escape_html(r['subject'])} — da {frappe.utils.escape_html(r['from'])}"
                        f"{(' (+%d allegati)' % len(r['attachments'])) if r['attachments'] else ''}</li>"
                        for r in results[:10])
        _email_operator(
            case,
            subject=f"[Thanatos] Cliente ha inviato {n} email come prova — {case}",
            message=f"Il cliente ha caricato <strong>{n}</strong> email come prova nella pratica <strong>{case}</strong>:<ul>{items}</ul>",
            from_user=user)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "submit_email_evidence notify")
