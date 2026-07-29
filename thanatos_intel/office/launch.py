"""Costruisce l'URL del client Collabora per un File, con permessi verificati."""
import xml.etree.ElementTree as ET

import frappe
import requests

from thanatos_intel.office.wopi import EDITABLE_EXT, mint_token

DISCOVERY_INTERNAL = "http://127.0.0.1:9980/hosting/discovery"
# host pubblico su cui il browser carica il client Collabora (proxy nginx /office)
PUBLIC_COLLABORA = "/office-online"


def _can_access_file(file_name):
    doc = frappe.get_doc("File", file_name)
    if frappe.session.user == "Administrator":
        return doc
    # permesso via documento allegato (Investigation Case ecc.)
    if doc.attached_to_doctype and doc.attached_to_name:
        if not frappe.has_permission(doc.attached_to_doctype, doc=doc.attached_to_name, ptype="read"):
            raise frappe.PermissionError("Nessun accesso al documento collegato")
    elif not frappe.has_permission("File", doc=file_name, ptype="read"):
        raise frappe.PermissionError("Nessun accesso al file")
    return doc


def _can_write_file(doc):
    if frappe.session.user == "Administrator":
        return True
    if doc.attached_to_doctype and doc.attached_to_name:
        return frappe.has_permission(doc.attached_to_doctype, doc=doc.attached_to_name, ptype="write")
    return frappe.has_permission("File", doc=doc.name, ptype="write")


def _urlsrc(ext):
    xml = requests.get(DISCOVERY_INTERNAL, timeout=8, verify=False).text
    root = ET.fromstring(xml)
    ext = ext.lstrip(".").lower()
    best = None
    for action in root.iter("action"):
        if action.get("ext", "").lower() == ext:
            best = action.get("urlsrc")
            if action.get("name") == "edit":
                break
    if not best:
        raise frappe.ValidationError(f"Collabora non supporta l'estensione .{ext}")
    # riscrive host interno -> proxy pubblico /office
    idx = best.find("/browser/")
    return PUBLIC_COLLABORA + best[idx:] if idx >= 0 else best


@frappe.whitelist()
def editor_url(file_name):
    if frappe.session.user in ("Guest", None, ""):
        raise frappe.PermissionError("Login richiesto")
    doc = _can_access_file(file_name)
    fn = (doc.file_name or "").lower()
    if not any(fn.endswith(e) for e in EDITABLE_EXT):
        raise frappe.ValidationError("Tipo di file non apribile in Office online")
    ext = "." + fn.rsplit(".", 1)[-1]
    write = _can_write_file(doc)
    token = mint_token(doc.name, write=write)
    urlsrc = _urlsrc(ext)
    wopi_src = frappe.utils.get_url() + "/wopi/files/" + doc.name
    sep = "&" if urlsrc.endswith("?") else ("&" if "?" in urlsrc else "?")
    full = f"{urlsrc}WOPISrc={frappe.utils.quote(wopi_src)}" if urlsrc.endswith("?") else f"{urlsrc}{sep}WOPISrc={frappe.utils.quote(wopi_src)}"
    return {"src": full, "access_token": token, "file_name": doc.file_name, "can_write": write}
