"""Video Verification — endpoint upload + finalize.

Flow lato browser (WebRTC):
1. /portal/ddd/video?case=DDD-... apre la pagina
2. Pagina chiede getUserMedia, scatta selfie, scatta foto documento,
   registra 8s di video, invia tutto a finalize_session.
"""
import frappe
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file


@frappe.whitelist()
def open_session(ddd_case: str, applicant: str = None):
    s = frappe.get_doc({
        "doctype": "Video Verification Session",
        "ddd_case": ddd_case,
        "applicant": applicant or frappe.db.get_value(
            "Diplomatic Eligibility Case", ddd_case, "applicant"),
        "session_status": "In Progress",
        "scheduled_on": now_datetime(),
    })
    s.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"session": s.name}


@frappe.whitelist(methods=["POST"])
def finalize_session(session: str):
    s = frappe.get_doc("Video Verification Session", session)
    files = frappe.request.files
    for key, fld in (("selfie", "selfie_file"),
                     ("document", "doc_capture_file"),
                     ("video", "recording_file")):
        f = files.get(key) if files else None
        if not f:
            continue
        fd = save_file(f.filename, f.read(),
                       "Video Verification Session", s.name,
                       is_private=1)
        setattr(s, fld, fd.file_url)
    s.session_status = "Completed"
    s.save(ignore_permissions=True)
    frappe.db.commit()

    from thanatos_intel.thanatos_ddd.facecheck import run_face_match_and_liveness
    return run_face_match_and_liveness(s.name)
