"""WOPI host per Collabora Online — apre/edita i File privati (docx) dei casi.

Auth via access_token (redis TTL) legato a (File, utente, write), coniato dalla
pagina /office DOPO verifica permessi Frappe. Gli endpoint qui NON ricontrollano
i permessi doc (gia autorizzati dal token) e leggono/scrivono il file su disco
via get_site_path per non passare dal permission layer di get_doc.
Il param access_token viene rinominato wopi_token in nginx per non far scattare
l auth OAuth Bearer di Frappe, che darebbe 401 prima del dispatch allow_guest.
Ritorni werkzeug Response per evitare l involucro message di Frappe.
"""
import json
import os

import frappe
from frappe.utils import get_datetime, get_site_path
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
    token = frappe.form_dict.get("wopi_token") or frappe.form_dict.get("access_token") or ""
    data = frappe.cache().get_value(_tkey(token)) if token else None
    if not data or data.get("file") != file_id:
        return None
    return data


def _file_meta(file_id):
    m = frappe.db.get_value(
        "File", file_id, ["file_name", "file_url", "is_private", "owner", "modified"], as_dict=True
    )
    if not m:
        return None
    url = (m.file_url or "").lstrip("/")
    m.path = get_site_path(url) if url else None
    return m


@frappe.whitelist(allow_guest=True)
def check_file_info(file_id):
    data = _resolve(file_id)
    if not data:
        return Response("invalid token", status=401)
    m = _file_meta(file_id)
    if not m or not m.path:
        return Response("not found", status=404)
    size = os.path.getsize(m.path) if os.path.exists(m.path) else 0
    try:
        mtime = get_datetime(m.modified).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except Exception:
        mtime = ""
    payload = {
        "BaseFileName": m.file_name,
        "Size": size,
        "OwnerId": m.owner or "system",
        "UserId": data["user"],
        "UserFriendlyName": frappe.db.get_value("User", data["user"], "full_name") or data["user"],
        "UserCanWrite": bool(data.get("write")),
        "UserCanNotWriteRelative": True,
        "Version": str(m.modified),
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
    m = _file_meta(file_id)
    if not m or not m.path:
        return Response("not found", status=404)
    method = frappe.local.request.method.upper()

    if method == "POST":
        if not data.get("write"):
            return Response("read-only", status=403)
        body = frappe.local.request.get_data()
        with open(m.path, "wb") as fh:
            fh.write(body)
        frappe.db.set_value("File", file_id, "file_size", len(body), update_modified=True)
        frappe.db.commit()
        new_mod = frappe.db.get_value("File", file_id, "modified")
        return Response(
            json.dumps({"LastModifiedTime": str(new_mod)}),
            status=200, content_type="application/json",
        )

    with open(m.path, "rb") as fh:
        body = fh.read()
    return Response(body, status=200, content_type="application/octet-stream")
