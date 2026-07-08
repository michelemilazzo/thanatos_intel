"""Passport Analyzer — MRZ parse + ICAO check-digit validation.

Estrae testo dal file (PDF via pypdf; immagine via pytesseract se installato),
trova le 2 righe MRZ TD3 (44 char ciascuna), valida i check digit ICAO 9303,
distingue Diplomatic/Service/Official dal document code, calcola risk score
e crea un record Passport Analysis collegato al Case/Evidence.
"""
import re
import os
import json
import datetime
import frappe

ICAO_VALUES = {**{str(i): i for i in range(10)},
               **{c: i + 10 for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
               "<": 0}

WEIGHTS = [7, 3, 1]

DOC_CODE_MAP = {
    "P":  ("Regular", 0),
    "PD": ("Diplomatic", 1),
    "PS": ("Service", 1),
    "PO": ("Official", 1),
    "PE": ("Emergency", 0),
}


def _check_digit(field: str) -> str:
    s = 0
    for i, c in enumerate(field):
        s += ICAO_VALUES.get(c, 0) * WEIGHTS[i % 3]
    return str(s % 10)


def _extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    if ext == ".pdf":
        try:
            import pypdf
            with open(file_path, "rb") as f:
                r = pypdf.PdfReader(f)
                for p in r.pages:
                    text += p.extract_text() or ""
        except Exception as e:
            frappe.log_error(f"pypdf fail: {e}", "PassportAnalyzer")
    if not text.strip() and ext == ".pdf":
        # PDF scan → rasterizza ogni pagina + OCR
        try:
            from pdf2image import convert_from_path
            import pytesseract
            for img in convert_from_path(file_path, dpi=300):
                text += pytesseract.image_to_string(img, lang="eng+ita") + "\n"
        except Exception as e:
            frappe.log_error(f"pdf2image OCR fail: {e}", "PassportAnalyzer")
    if not text.strip():
        try:
            from PIL import Image
            import pytesseract
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img, lang="eng+ita")
        except Exception as e:
            frappe.log_error(f"OCR fail: {e}", "PassportAnalyzer")
    # pass MRZ-mirato: banda inferiore, upscale, threshold, whitelist OCR-B.
    # Le righe MRZ vengono ACCODATE così _find_mrz le può agganciare anche quando
    # l'OCR generale del documento è sporco.
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"):
        mrz = _mrz_ocr(file_path)
        if mrz:
            text = (text or "") + "\n" + mrz
    # Fallback vision AI: tesseract (generale + MRZ-mirato) non ha trovato
    # nulla di utile — tipico su thumbnail WhatsApp compresse. Stesso motore
    # usato da ocr_service.py (OpenRouter, autorizzato dall'utente per l'uso
    # su WhatsApp).
    if not text.strip() and ext in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"):
        try:
            from thanatos_intel.ai.ocr_service import _vision_ocr_image
            vtext = _vision_ocr_image(file_path)
            if vtext:
                text = vtext
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PassportAnalyzer vision fallback")
    return text


_MRZ_WL = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"


def _mrz_ocr(file_path: str) -> str:
    """OCR ottimizzato per la banda MRZ (ICAO 9303): ritaglia il terzo inferiore,
    ingrandisce, binarizza e usa tesseract con whitelist OCR-B. Prova la banda e,
    in fallback, l'immagine intera."""
    try:
        import cv2
        import numpy as np
        import pytesseract
    except Exception:
        return ""
    try:
        img = cv2.imread(file_path)
        if img is None:
            return ""
        h, w = img.shape[:2]
        cfg = f"--psm 6 --oem 1 -c tessedit_char_whitelist={_MRZ_WL}"
        out = []
        for crop in (img[int(h * 0.68):, :], img):
            g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            scale = max(1, int(1600 / max(1, g.shape[1])))
            if scale > 1:
                g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            g = cv2.GaussianBlur(g, (3, 3), 0)
            g = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            txt = pytesseract.image_to_string(g, config=cfg)
            for ln in txt.splitlines():
                c = "".join(ch for ch in ln.upper() if ch in _MRZ_WL)
                if c.count("<") >= 3 and 30 <= len(c) <= 50:
                    out.append(c)
        return "\n".join(out)
    except Exception as e:
        frappe.log_error(f"MRZ OCR fail: {e}", "PassportAnalyzer")
        return ""


def _find_mrz(text: str):
    """Locate the two TD3 MRZ lines (44 chars each, A-Z0-9<)."""
    cleaned = []
    for raw in text.splitlines():
        line = re.sub(r"[^A-Z0-9<]", "", raw.upper())
        if 40 <= len(line) <= 50:
            cleaned.append(line[:44].ljust(44, "<"))
    for i in range(len(cleaned) - 1):
        if cleaned[i].startswith("P") and len(cleaned[i + 1]) == 44:
            return cleaned[i], cleaned[i + 1]
    # tolleranza: riga1 con molti '<' (nome) seguita da riga2 alfanumerica densa
    for i in range(len(cleaned) - 1):
        l1, l2 = cleaned[i], cleaned[i + 1]
        if l1.count("<") >= 5 and sum(c.isdigit() for c in l2) >= 10:
            return l1, l2
    return None, None


def _parse_yyMMdd(s: str):
    try:
        y, m, d = int(s[0:2]), int(s[2:4]), int(s[4:6])
        century = 2000 if y < 50 else 1900
        return datetime.date(century + y, m, d)
    except Exception:
        return None


def parse_mrz(l1: str, l2: str) -> dict:
    out = {"mrz_line_1": l1, "mrz_line_2": l2, "checksum_details": [],
           "mrz_valid": False}
    if not l1 or not l2:
        return out
    doc_code = l1[0:2].replace("<", "")
    issuing = l1[2:5]
    names = l1[5:].split("<<", 1)
    surname = (names[0] or "").replace("<", " ").strip()
    given = (names[1] if len(names) > 1 else "").replace("<", " ").strip()

    passport_no = l2[0:9]
    pn_cd = l2[9]
    nationality = l2[10:13]
    dob_raw = l2[13:19]; dob_cd = l2[19]
    sex = l2[20]
    expiry_raw = l2[21:27]; exp_cd = l2[27]
    personal = l2[28:42]; pers_cd = l2[42]
    composite_cd = l2[43]

    def chk(name, val, expected):
        actual = _check_digit(val)
        ok = actual == expected
        out["checksum_details"].append({
            "field": name, "value": val,
            "expected": expected, "actual": actual, "ok": ok,
        })
        return ok

    checks = [
        chk("passport_no", passport_no, pn_cd),
        chk("dob",         dob_raw,     dob_cd),
        chk("expiry",      expiry_raw,  exp_cd),
        chk("personal",    personal,    pers_cd),
        chk("composite",
            passport_no + pn_cd + dob_raw + dob_cd + expiry_raw + exp_cd + personal + pers_cd,
            composite_cd),
    ]
    out["mrz_valid"] = all(checks)

    ptype, is_dipl = DOC_CODE_MAP.get(doc_code, ("Unknown", 0))
    out.update({
        "passport_type": ptype,
        "is_diplomatic": is_dipl,
        "document_code": doc_code,
        "issuing_country": issuing.replace("<", ""),
        "surname": surname,
        "given_names": given,
        "passport_number": passport_no.replace("<", ""),
        "nationality": nationality.replace("<", ""),
        "dob": _parse_yyMMdd(dob_raw),
        "sex": sex if sex in ("M", "F") else ("X" if sex == "<" else ""),
        "expiry": _parse_yyMMdd(expiry_raw),
    })
    return out


def analyze(file_path: str) -> dict:
    text = _extract_text(file_path)
    l1, l2 = _find_mrz(text)
    res = parse_mrz(l1, l2) if l1 else {
        "mrz_valid": False, "checksum_details": [],
        "anomalies": ["MRZ non rilevata: scan illeggibile o non passaporto ICAO TD3"],
    }
    res["raw_text"] = text[:4000]

    anomalies = res.get("anomalies", []) if isinstance(res.get("anomalies"), list) else []
    risk = 0
    if l1 and not res.get("mrz_valid"):
        anomalies.append("Check digit MRZ falliti: documento sospetto / alterato")
        risk += 50
    if res.get("expiry") and res["expiry"] < datetime.date.today():
        anomalies.append(f"Scaduto il {res['expiry']}")
        res["expired"] = 1
        risk += 20
    if res.get("issuing_country") != res.get("nationality"):
        anomalies.append(f"Nazionalità ({res.get('nationality')}) ≠ Stato emittente ({res.get('issuing_country')})")
        risk += 15
    if res.get("is_diplomatic"):
        anomalies.append("Passaporto DIPLOMATICO — verifica accreditamento MAECI")
        risk += 10

    res["anomalies"] = "\n".join(anomalies) if anomalies else ""
    if not l1:
        # MRZ non letta: NON è una falsificazione — è illeggibile (scan/foto scarsa)
        res["mrz_unreadable"] = 1
        res["risk_score"] = 0
        res["verdict"] = "Inconclusive"
    else:
        res["risk_score"] = min(risk, 100)
        res["verdict"] = ("Authentic" if risk < 20 else
                          "Suspect" if risk < 50 else
                          "Forged" if risk < 80 else "Inconclusive")
    res["checksum_details"] = json.dumps(res["checksum_details"], indent=2, default=str)
    return res


def analyze_evidence(evidence_name: str, case: str = None) -> str:
    ev = frappe.get_doc("Investigation Evidence", evidence_name)
    file_url = ev.get("attached_file") or ev.get("file_url") or ev.get("source_file")
    if not file_url:
        frappe.throw("Evidence senza file allegato")
    path = frappe.get_site_path("private", "files",
                                file_url.split("/private/files/")[-1])
    if not os.path.exists(path):
        path = frappe.get_site_path("public", "files",
                                    file_url.split("/files/")[-1])
    res = analyze(path)
    doc = frappe.get_doc({
        "doctype": "Passport Analysis",
        "investigation_case": case or ev.get("investigation_case"),
        "evidence": evidence_name,
        "source_file": file_url,
        **{k: v for k, v in res.items() if v not in (None, "")},
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


@frappe.whitelist()
def analyze_file(file_url: str, investigation_case: str = None,
                 evidence: str = None) -> dict:
    path = frappe.get_site_path("private", "files",
                                file_url.split("/private/files/")[-1])
    if not os.path.exists(path):
        path = frappe.get_site_path("public", "files",
                                    file_url.split("/files/")[-1])
    res = analyze(path)
    doc = frappe.get_doc({
        "doctype": "Passport Analysis",
        "investigation_case": investigation_case,
        "evidence": evidence,
        "source_file": file_url,
        **{k: v for k, v in res.items() if v not in (None, "")},
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, **res}
