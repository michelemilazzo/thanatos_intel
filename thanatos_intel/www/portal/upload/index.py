"""Upload documenti lato CLIENTE.

Il cliente carica file su una delle PROPRIE pratiche (Investigation Case visibili).
Endpoint whitelisted con check row-level riusando visible_case_names().
"""
import hashlib
import frappe
from frappe import _
from frappe.utils import now_datetime


no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/upload"
        raise frappe.Redirect

    user = frappe.session.user
    from thanatos_intel.permissions import is_full_access, visible_case_names

    if is_full_access(user):
        cases = frappe.get_all("Investigation Case",
                               fields=["name", "case_number", "case_title"],
                               order_by="creation desc", limit=50)
    else:
        names = visible_case_names(user) or []
        cases = frappe.get_all("Investigation Case",
                               filters={"name": ["in", names]},
                               fields=["name", "case_number", "case_title"],
                               order_by="creation desc", limit=50) if names else []

    preselect = frappe.form_dict.get("case")
    if preselect and preselect not in [c["name"] for c in cases]:
        preselect = None

    context.cases = cases
    context.preselect = preselect
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Carica documento — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context


def _sha256(content: bytes) -> str:
    h = hashlib.sha256()
    h.update(content)
    return h.hexdigest()


def _guess_type(filename: str) -> str:
    low = (filename or "").lower()
    if low.endswith((".pdf", ".doc", ".docx")):
        return "Document"
    if low.endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
        return "Photo"
    if low.endswith((".eml", ".msg")):
        return "Email"
    if low.endswith((".mp4", ".mov", ".mkv", ".webm")):
        return "Video"
    if low.endswith((".mp3", ".wav", ".ogg")):
        return "Audio"
    return "File"


@frappe.whitelist(methods=["POST"])
_MAX_FILE_MB = 50
_ALLOWED_EXT = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".zip", ".7z", ".tar", ".gz",
    ".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav",
    ".eml", ".msg",
}


def _validate_file(filename: str, content: bytes):
    import os
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in _ALLOWED_EXT:
        frappe.throw(_(f"Tipo file non consentito: {ext}. Formati accettati: PDF, immagini, Office, ZIP, video."),
                     frappe.ValidationError)
    size_mb = len(content) / (1024 * 1024)
    if size_mb > _MAX_FILE_MB:
        frappe.throw(_(f"File troppo grande: {size_mb:.1f} MB. Limite: {_MAX_FILE_MB} MB."),
                     frappe.ValidationError)


def client_upload(case: str = ""):
    """Allega i file caricati dal cliente a una sua pratica."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)

    from thanatos_intel.permissions import is_full_access, visible_case_names
    user = frappe.session.user
    if not is_full_access(user):
        names = visible_case_names(user) or []
        if case not in names:
            frappe.throw(_("Accesso negato a questa pratica."), frappe.PermissionError)

    if not frappe.db.exists("Investigation Case", case):
        frappe.throw(_("Pratica non trovata."))

    files = frappe.request.files.getlist("files") if frappe.request.files else []
    if not files:
        return {"error": "no files"}

    uploaded, errors = [], []
    for f in files:
        try:
            content = f.read()
            _validate_file(f.filename, content)
            sha = _sha256(content)
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": f.filename,
                "is_private": 1,
                "content": content,
                "attached_to_doctype": "Investigation Case",
                "attached_to_name": case,
            })
            file_doc.save(ignore_permissions=True)

            ev_doc = frappe.get_doc({
                "doctype": "Investigation Evidence",
                "investigation_case": case,
                "evidence_name": f.filename,
                "evidence_type": _guess_type(f.filename),
                "attached_file": file_doc.file_url,
                "hash_value": sha,
                "custody_status": "Received",
                "notes": f"Caricato dal cliente {user} il {now_datetime():%Y-%m-%d %H:%M}",
            })
            ev_doc.insert(ignore_permissions=True)

            frappe.get_doc({
                "doctype": "Chain Of Custody Event",
                "event_type": "Created",
                "related_reference": ev_doc.name,
                "notes": f"Client upload {f.filename} | SHA256={sha} | user={user}",
            }).insert(ignore_permissions=True)

            uploaded.append({"name": f.filename, "size": len(content), "sha256": sha})
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"client_upload {f.filename}")
            errors.append({"name": f.filename, "error": str(e)[:200]})

    frappe.db.commit()

    if uploaded:
        try:
            from thanatos_intel.workflow.notify import _email_operator
            names_list = ", ".join(u["name"] for u in uploaded[:5])
            _email_operator(
                case,
                subject=f"[Thanatos] Cliente ha caricato {len(uploaded)} file — {case}",
                message=(
                    f"Il cliente ha caricato <strong>{len(uploaded)}</strong> file "
                    f"nella pratica <strong>{case}</strong>:<br>"
                    f"<ul style='margin:8px 0'>{''.join('<li>'+u['name']+'</li>' for u in uploaded[:10])}</ul>"
                ),
                from_user=user,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "client_upload notify operator")

    return {"case": case, "uploaded": uploaded, "errors": errors, "count": len(uploaded)}
