"""Document analyzer — estrae metadati PDF/Office, esegue check automatici,
crea Document Metadata + Document Check + Document Verdict."""
import json
import os
from datetime import datetime

import frappe
from frappe.utils import now_datetime


@frappe.whitelist()
def analyze(document_intake: str) -> dict:
    """Analizza un Document Intake e ritorna verdict + metadata + checks."""
    intake = frappe.get_doc("Document Intake", document_intake)
    path = _path(intake.file_url)
    if not path or not os.path.exists(path):
        frappe.throw(f"File non trovato: {intake.file_url}")

    meta = _extract_metadata(path)
    checks = _run_checks(intake, meta, path)

    md = frappe.get_doc({
        "doctype": "Document Metadata",
        "title": intake.doc_label,
        "document_intake": intake.name,
        "author": meta.get("author"),
        "creator_software": meta.get("creator"),
        "producer": meta.get("producer"),
        "created_at_meta": meta.get("creation_date"),
        "modified_at_meta": meta.get("mod_date"),
        "has_anomalies": meta.get("has_anomalies", 0),
        "anomalies_notes": meta.get("anomalies_notes", ""),
        "raw_json": json.dumps(meta, default=str),
    }).insert(ignore_permissions=True)

    score = _score_from_checks(checks)
    verdict_label = _verdict_from_score(score)
    verdict = frappe.get_doc({
        "doctype": "Document Verdict",
        "title": f"Verdict {intake.doc_label}",
        "document_intake": intake.name,
        "overall_verdict": verdict_label,
        "risk_score": score,
        "analyst": frappe.session.user,
        "issued_at": now_datetime(),
        "rationale": "\n".join([f"[{c['severity']}] {c['check_name']}: {c['details']}" for c in checks]),
    }).insert(ignore_permissions=True)

    intake.metadata = md.name
    intake.verdict = verdict.name
    intake.page_count = meta.get("page_count")
    intake.status = "Needs Review" if verdict_label in ("Suspicious", "Forged", "Inconclusive") else "Completed"
    intake.set("checks", [])
    for c in checks:
        intake.append("checks", c)
    intake.save(ignore_permissions=True)
    frappe.db.commit()
    return {"verdict": verdict_label, "risk_score": score,
            "metadata": md.name, "checks": len(checks)}


def _path(file_url: str) -> str:
    if not file_url:
        return ""
    if file_url.startswith("/private/files/"):
        return frappe.get_site_path() + file_url
    if file_url.startswith("/files/"):
        return frappe.get_site_path("public") + file_url
    return frappe.get_site_path() + file_url


def _extract_metadata(path: str) -> dict:
    meta = {"path": path, "size": os.path.getsize(path)}
    if path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            r = PdfReader(path)
            info = r.metadata or {}
            meta.update({
                "page_count": len(r.pages),
                "author": str(info.get("/Author") or ""),
                "creator": str(info.get("/Creator") or ""),
                "producer": str(info.get("/Producer") or ""),
                "title": str(info.get("/Title") or ""),
                "creation_date": _parse_pdf_date(info.get("/CreationDate")),
                "mod_date": _parse_pdf_date(info.get("/ModDate")),
                "encrypted": r.is_encrypted,
            })
            anomalies = []
            if meta["creation_date"] and meta["mod_date"]:
                try:
                    delta = (meta["mod_date"] - meta["creation_date"]).total_seconds()
                    if delta < -1:
                        anomalies.append("ModDate prima di CreationDate")
                    if delta > 365 * 86400 * 5:
                        anomalies.append("modifica >5 anni dopo creazione")
                except Exception:
                    pass
            if not meta["author"] and not meta["creator"]:
                anomalies.append("metadati autore/creator vuoti")
            meta["has_anomalies"] = 1 if anomalies else 0
            meta["anomalies_notes"] = " · ".join(anomalies)
        except Exception as e:
            meta["error"] = str(e)[:200]
    return meta


def _parse_pdf_date(v):
    if not v:
        return None
    s = str(v)
    if s.startswith("D:"):
        s = s[2:]
    try:
        return datetime.strptime(s[:14], "%Y%m%d%H%M%S")
    except Exception:
        try:
            return datetime.strptime(s[:8], "%Y%m%d")
        except Exception:
            return None


def _run_checks(intake, meta: dict, path: str):
    checks = []
    if meta.get("has_anomalies"):
        checks.append({"check_name": "metadata_anomalies", "result": "Fail",
                       "severity": "High", "details": meta.get("anomalies_notes", "")})
    else:
        checks.append({"check_name": "metadata_anomalies", "result": "Pass",
                       "severity": "Info", "details": "Nessuna anomalia"})
    if meta.get("encrypted"):
        checks.append({"check_name": "encryption", "result": "Warning",
                       "severity": "Medium", "details": "PDF cifrato"})
    if intake.sha256:
        dup = frappe.db.count("Document Intake", {"sha256": intake.sha256, "name": ["!=", intake.name]})
        if dup:
            checks.append({"check_name": "duplicate_hash", "result": "Fail",
                           "severity": "High", "details": f"SHA-256 già presente in {dup} documenti"})
        else:
            checks.append({"check_name": "duplicate_hash", "result": "Pass",
                           "severity": "Info", "details": "Hash univoco"})
    if meta.get("page_count") == 0:
        checks.append({"check_name": "pages", "result": "Fail",
                       "severity": "Critical", "details": "Documento senza pagine"})
    return checks


def _score_from_checks(checks):
    s = 0
    weight = {"Critical": 35, "High": 20, "Medium": 10, "Low": 4, "Info": 0}
    for c in checks:
        if c["result"] in ("Fail", "Warning"):
            s += weight.get(c["severity"], 0)
    return min(100, s)


def _verdict_from_score(s: int) -> str:
    if s >= 60:
        return "Forged"
    if s >= 35:
        return "Suspicious"
    if s >= 15:
        return "Inconclusive"
    if s > 0:
        return "Likely Authentic"
    return "Authentic"
