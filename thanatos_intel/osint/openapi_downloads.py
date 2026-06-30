"""Scarico file dalla sezione Downloads di openapi (export PDF/visure/report) e
consegna al caso. Auth = Basic (user openapi + Downloads Key), URL firmato via
redirect (allow_redirects). Config: openapi_downloads_user / openapi_downloads_key.
"""
import urllib.parse
import frappe


def _creds():
    return frappe.conf.get("openapi_downloads_user"), frappe.conf.get("openapi_downloads_key")


def download_bytes(category, filename):
    import requests
    user, key = _creds()
    if not (user and key):
        frappe.throw("Credenziali download openapi mancanti (openapi_downloads_user/key in site_config).")
    url = "https://console.openapi.com/downloads/%s/%s" % (
        urllib.parse.quote(category), urllib.parse.quote(filename))
    r = requests.get(url, auth=(user, key), allow_redirects=True, timeout=90)
    r.raise_for_status()
    return r.content, (r.headers.get("content-type") or "application/octet-stream")


@frappe.whitelist()
def import_to_case(case, filename, category="console", doc_kind="Altro", self_mode=0):
    """Scarica `filename` dalla categoria Downloads openapi e lo allega al caso,
    poi consegna (cartella Drive + portale/email se self_mode)."""
    if not frappe.db.exists("Investigation Case", case):
        frappe.throw("Caso non trovato")
    content, ctype = download_bytes(category, filename)
    from frappe.utils.file_manager import save_file
    f = save_file(filename, content, "Investigation Case", case, is_private=1)
    from thanatos_intel.reporting.case_file_delivery import deliver_case_file
    res = deliver_case_file(case, f.file_url, file_name=filename, doc_kind=doc_kind, self_mode=int(self_mode or 0))
    res["downloaded_bytes"] = len(content)
    res["file_url"] = f.file_url
    return res
