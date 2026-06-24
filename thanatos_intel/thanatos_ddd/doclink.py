"""Link firmati (HMAC + scadenza) per servire file privati via email senza login.

Solo file sotto /private/files/. Token = base64(file_url|exp|sig), sig = HMAC-SHA256
con la encryption_key del sito. Scadenza default 30 giorni.
"""
import os
import time
import hmac
import base64
import hashlib
import frappe


def _secret():
    k = (frappe.local.conf.get("encryption_key")
         or frappe.local.conf.get("secret_key") or "thanatos-doclink")
    return k.encode() if isinstance(k, str) else k


def make_token(file_url, ttl_days=30):
    exp = int(time.time()) + int(ttl_days) * 86400
    msg = f"{file_url}|{exp}"
    sig = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{msg}|{sig}".encode()).decode()


def signed_url(file_url, ttl_days=30):
    base = frappe.utils.get_url()
    return f"{base}/api/method/thanatos_intel.thanatos_ddd.doclink.view?t={make_token(file_url, ttl_days)}"


@frappe.whitelist(allow_guest=True)
def view(t):
    try:
        raw = base64.urlsafe_b64decode(t.encode()).decode()
        file_url, exp, sig = raw.rsplit("|", 2)
    except Exception:
        raise frappe.PermissionError("Link non valido")
    good = hmac.new(_secret(), f"{file_url}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig):
        raise frappe.PermissionError("Firma non valida")
    if int(exp) < int(time.time()):
        raise frappe.PermissionError("Link scaduto")
    if not file_url.startswith("/private/files/") or ".." in file_url:
        raise frappe.PermissionError("Percorso non ammesso")
    rel = file_url.split("/private/files/", 1)[1]
    path = frappe.get_site_path("private", "files", rel)
    if not os.path.exists(path):
        frappe.throw("File non trovato", frappe.DoesNotExistError)
    with open(path, "rb") as f:
        content = f.read()
    frappe.local.response.filename = os.path.basename(path)
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
