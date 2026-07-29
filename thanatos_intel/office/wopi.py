"""WOPI host per Collabora Online — apre/edita i File privati (docx) dei casi.

Flusso: la pagina /office conia un access_token (redis, TTL) legato a
(File, utente, permesso di scrittura) dopo aver verificato i permessi Frappe.
Collabora richiama qui server-to-server passando solo il token:
  GET  /wopi/files/<id>            -> check_file_info (JSON WOPI top-level)
  GET  /wopi/files/<id>/contents   -> contents (bytes)
  POST /wopi/files/<id>/contents   -> contents (salva bytes)
Le route pulite /wopi/... sono mappate in nginx sui method qui sotto.
Gli endpoint restituiscono werkzeug Response per evitare l'involucro
{"message": ...} di Frappe, che Collabora non sa interpretare.
"""
import json
import os

import frappe
from frappe.utils import get_datetime
from werkzeug.wrappers import Response

TOKEN_TTL = 8 * 3600
EDITABLE_EXT = (".docx", ".odt", ".doc", ".rtf", ".xlsx", ".ods", ".pptx", ".odp")


def _tkey(token):
    return f"wopi_token:{token}"


def mint_token(file_name, write=True):
    token = frappe.generate_hash(length=48)
    frappe.cache().set_value(
        _tkey(token),
        {"file": file_name, "user": frappe.session.user, "write": 1 if write else 0},
        expires_in_sec=TOKEN_TTL,
    )
    return token


def _resolve(file_id):
    token = frappe.form_dict.get("access_token") or ""
    data = frappe.cache().get_value(_tkey(token)) if token else None
    if not data or data.get("file") != file_id:
        return None
    return data


@frappe.whitelist(allow_guest=True)
def check_file_info(file_id):
    data = _resolve(file_id)
    if not data:
        return Response("invalid token", status=401)
    doc = frappe.get_doc("File", file_id)
    path = doc.get_full_path()
    size = os.path.getsize(path) if os.path.exists(path) else 0
    try:
        mtime = get_datetime(doc.modified).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except Exception:
        mtime = ""
    payload = {
        "BaseFileName": doc.file_name,
        "Size": size,
        "OwnerId": doc.owner or "system",
        "UserId": data["user"],
        "UserFriendlyName": frappe.db.get_value("User", data["user"], "full_name") or data["user"],
        "UserCanWrite": bool(data.get("write")),
        "UserCanNotWriteRelative": True,
        "Version": str(doc.modified),
        "LastModifiedTime": mtime,
        "PostMessageOrigin": frappe.utils.get_url(),
        "EnableOwnerTermination": False,
    }
    return Response(json.dumps(payload), status=200, content_type="application/json")


@frappe.whitelist(allow_guest=True)
def contents(file_id):
    data = _resolve(file_id)
    if not data:
        return Response("invalid token", status=401)
    doc = frappe.get_doc("File", file_id)
    path = doc.get_full_path()
    method = frappe.local.request.method.upper()

    if method == "POST":
        if not data.get("write"):
            return Response("read-only", status=403)
        body = frappe.local.request.get_data()
        with open(path, "wb") as fh:
            fh.write(body)
        doc.db_set("file_size", len(body), update_modified=True)
        frappe.db.commit()
        return Response(
            json.dumps({"LastModifiedTime": str(doc.modified)}),
            status=200, content_type="application/json",
        )

    with open(path, "rb") as fh:
        body = fh.read()
    return Response(
        body, status=200,
        content_type="application/octet-stream",
    )
