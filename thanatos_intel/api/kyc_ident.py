"""Identificazione live per KYC Check.

Flow:
1. Operatore sul form KYC Check → bottone "Identificazione live" → make_link genera URL con token monouso (48h).
2. Il cliente apre /kyc-ident?token=... (guest), cattura selfie + documento + video 8s dal browser.
3. submit salva i file sul KYC Check, esegue face match + liveness (facecheck DDD) e scrive esito e status.
"""
import json
import os

import frappe
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file

CACHE_PREFIX = "kyc_ident:"
TTL = 48 * 3600


@frappe.whitelist()
def make_link(kyc_check):
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    if not frappe.db.exists("KYC Check", kyc_check):
        frappe.throw("KYC Check inesistente")
    token = frappe.generate_hash(length=32)
    frappe.cache().set_value(CACHE_PREFIX + token, kyc_check, expires_in_sec=TTL)
    return {"url": frappe.utils.get_url("/kyc-ident?token=" + token), "expires_hours": 48}


def _resolve(token):
    kyc = frappe.cache().get_value(CACHE_PREFIX + (token or ""))
    if not kyc:
        frappe.throw("Link di identificazione non valido o scaduto", frappe.PermissionError)
    return kyc


@frappe.whitelist(allow_guest=True)
def info(token):
    kyc = _resolve(token)
    d = frappe.db.get_value("KYC Check", kyc,
                            ["full_name", "first_name", "last_name", "document_type"], as_dict=True)
    return {"name_display": d.full_name or ("%s %s" % (d.first_name or "", d.last_name or "")).strip(),
            "document_type": d.document_type or ""}


def _path(url):
    p = frappe.get_site_path("private", "files", url.split("/private/files/")[-1])
    if not os.path.exists(p):
        p = frappe.get_site_path("public", "files", url.split("/files/")[-1])
    return p if os.path.exists(p) else None


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit(token):
    kyc_name = _resolve(token)
    doc = frappe.get_doc("KYC Check", kyc_name)
    files = frappe.request.files

    fields = {"selfie": "selfie_photo", "doc_front": "document_front", "doc_back": "document_back"}
    saved = {}
    for key, fld in fields.items():
        f = files.get(key) if files else None
        if not f:
            continue
        fd = save_file("%s_%s.jpg" % (key, kyc_name), f.read(), "KYC Check", kyc_name, is_private=1)
        doc.set(fld, fd.file_url)
        saved[fld] = fd.file_url

    video_path = None
    f = files.get("video") if files else None
    if f:
        fd = save_file("liveness_%s.webm" % kyc_name, f.read(), "KYC Check", kyc_name, is_private=1)
        video_path = _path(fd.file_url)

    if "selfie_photo" not in saved or "document_front" not in saved:
        frappe.throw("Servono selfie e fronte documento")

    from thanatos_intel.thanatos_ddd.facecheck import face_match, liveness_basic
    res = {"face": face_match(_path(doc.selfie_photo), _path(doc.document_front))}
    if video_path:
        res["liveness"] = liveness_basic(video_path)

    face_ok = bool(res["face"].get("verified"))
    alive_ok = bool(res.get("liveness", {}).get("alive"))
    if face_ok and (alive_ok or not video_path):
        outcome = "PASS"
    elif face_ok or alive_ok:
        outcome = "REVIEW"
    else:
        outcome = "FAIL"

    doc.status = "In Review" if outcome == "PASS" else "Manual Review"
    note = "AUTO-IDENT %s — esito %s | face: %s" % (
        now_datetime().strftime("%Y-%m-%d %H:%M"), outcome, json.dumps(res["face"]))
    if "liveness" in res:
        note += " | liveness: %s" % json.dumps(res["liveness"])
    doc.reviewer_notes = note
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.cache().delete_value(CACHE_PREFIX + token)
    return {"ok": True, "outcome": outcome, "face": res["face"], "liveness": res.get("liveness")}
