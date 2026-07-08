"""Download unificato dei reperti/documenti di un caso.

Risolve il 403 del link nativo `/private/files/...` (che richiede permesso diretto e
sessione sullo stesso dominio) offrendo un endpoint con TRE vie di autorizzazione:
  (1) operatore con permesso di lettura sul caso;
  (2) cliente proprietario del caso, se il documento e' 'Condiviso col cliente';
  (3) token firmato a tempo -> link condivisibile (email/WhatsApp), senza login.

`share_link` genera l'URL a tempo (solo operatori). `dl` serve il file.
"""
import os
import time
import hmac
import hashlib

import frappe
from frappe.utils import get_url


def _resolve(file):
    if file and frappe.db.exists("File", file):
        return frappe.get_doc("File", file)
    nm = frappe.db.get_value("File", {"file_url": file}, "name")
    return frappe.get_doc("File", nm) if nm else None


def _secret():
    s = frappe.local.conf.get("case_file_link_secret")
    if not s:
        from frappe.utils.password import get_encryption_key
        s = get_encryption_key()
    return s.encode() if isinstance(s, str) else s


def _sign(fname, exp):
    return hmac.new(_secret(), ("%s:%s" % (fname, exp)).encode(),
                    hashlib.sha256).hexdigest()[:40]


def _case_of(f):
    return f.attached_to_name if f.attached_to_doctype == "Investigation Case" else None


def _client_owns(user, case):
    cl = frappe.db.get_value("Investigation Client", {"platform_user": user}, "name")
    if not cl:
        return False
    return frappe.db.get_value("Investigation Case", case, "client") == cl


def _full_path(f):
    try:
        return f.get_full_path()
    except Exception:
        return frappe.get_site_path((f.file_url or "").lstrip("/"))


@frappe.whitelist()
def share_link(file, ttl_hours=48):
    """URL di download a tempo (token firmato). Richiede permesso operatore sul caso."""
    f = _resolve(file)
    if not f:
        frappe.throw("File non trovato")
    case = _case_of(f)
    if case and not frappe.has_permission("Investigation Case", "read", case):
        raise frappe.PermissionError
    exp = int(time.time()) + int(ttl_hours) * 3600
    sig = _sign(f.name, exp)
    url = get_url("/api/method/thanatos_intel.reporting.case_file.dl"
                  "?file=%s&exp=%s&sig=%s" % (f.name, exp, sig))
    return {"url": url, "expires": exp, "ttl_hours": int(ttl_hours)}


@frappe.whitelist(allow_guest=True)
def dl(file, exp=None, sig=None):
    """Serve il file se autorizzato via token a tempo / operatore / cliente proprietario."""
    f = _resolve(file)
    if not f:
        frappe.local.response["http_status_code"] = 404
        return "Not found"

    case = _case_of(f)
    user = frappe.session.user
    ok = False

    # (3) token a tempo
    if exp and sig:
        try:
            if int(exp) > int(time.time()) and hmac.compare_digest(sig, _sign(f.name, int(exp))):
                ok = True
        except Exception:
            ok = False

    # (1) operatore con permesso sul caso
    if not ok and user != "Guest" and case:
        if frappe.has_permission("Investigation Case", "read", case, user=user):
            ok = True

    # (2) cliente proprietario + documento condiviso
    if not ok and user != "Guest" and case:
        if _client_owns(user, case) and f.get("visibilita_cliente") == "Condiviso col cliente":
            ok = True

    if not ok:
        frappe.local.response["http_status_code"] = 403
        return "Accesso negato"

    path = _full_path(f)
    if not path or not os.path.exists(path):
        frappe.local.response["http_status_code"] = 404
        return "File mancante su disco"
    with open(path, "rb") as fh:
        content = fh.read()
    frappe.local.response.filename = f.file_name or os.path.basename(path)
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
