"""OCR Service — estrazione testo e campi strutturati da documenti.

Supporta:
  - Immagini: JPEG, PNG, TIFF, BMP, WEBP
  - PDF: testo nativo (pypdf) + fallback rasterizzato (pdf2image + Tesseract)
  - Documenti supportati: passport, id_card, driving_license, company_doc,
                          financial_doc, contract, generic

Lingue default: eng+ita+ron (Tesseract language packs installati sul server).
"""

import os
import re
import frappe

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}
TESSERACT_LANGS = "eng+ita+ron"
OCR_DPI = 300


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_text_from_file(file_path: str, lang: str = TESSERACT_LANGS) -> tuple[str, str]:
    """Returns (text, provider) where provider is 'native_pdf'|'tesseract_pdf'|'tesseract_image'."""
    ext = os.path.splitext(file_path)[1].lower()
    text = ""

    if ext == ".pdf":
        # 1. Try native text extraction
        try:
            import pypdf
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    text += (page.extract_text() or "") + "\n"
            if text.strip() and len(text.strip()) > 30:
                return text.strip(), "native_pdf"
        except Exception as e:
            frappe.log_error(f"pypdf: {e}", "OCRService")

        # 2. Scanned PDF → rasterize + OCR
        try:
            from pdf2image import convert_from_path
            import pytesseract
            pages = convert_from_path(file_path, dpi=OCR_DPI)
            for img in pages:
                text += pytesseract.image_to_string(img, lang=lang) + "\n"
            return text.strip(), "tesseract_pdf"
        except Exception as e:
            frappe.log_error(f"pdf2image OCR: {e}", "OCRService")
            return "", "error"

    if ext in SUPPORTED_IMAGE_EXT:
        try:
            from PIL import Image
            import pytesseract
            img = Image.open(file_path)
            # Upscale small images for better OCR
            w, h = img.size
            if w < 1000 or h < 1000:
                scale = max(1000 / w, 1000 / h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            text = pytesseract.image_to_string(img, lang=lang)
            return text.strip(), "tesseract_image"
        except Exception as e:
            frappe.log_error(f"pytesseract image: {e}", "OCRService")
            return "", "error"

    return "", "unsupported"


def _avg_confidence(file_path: str, lang: str = TESSERACT_LANGS) -> float:
    """Returns mean OCR confidence 0–100 for image files."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_IMAGE_EXT:
        return 0.0
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(file_path)
        data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
        confs = [c for c in data["conf"] if isinstance(c, (int, float)) and c >= 0]
        return round(sum(confs) / len(confs) / 100.0, 3) if confs else 0.0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Document-type field extractors
# ---------------------------------------------------------------------------

def _extract_passport_fields(text: str) -> dict:
    """Quick regex extraction (full MRZ parse is in passport/analyzer.py)."""
    fields = {}
    # MRZ lines TD3
    mrz = re.findall(r"[A-Z0-9<]{44}", text.upper())
    if len(mrz) >= 2:
        fields["mrz_line_1"] = mrz[0]
        fields["mrz_line_2"] = mrz[1]
    # Common labels
    for label, pattern in [
        ("surname",   r"(?:Surname|Cognome|Nume)[:\s]+([A-Z][A-Za-z\-']+)"),
        ("given_names", r"(?:Given names|Nome|Prenume)[:\s]+([A-Z][A-Za-z\s]+)"),
        ("passport_number", r"(?:No\.|Number|Numero)[:\s]*([A-Z]{2}[0-9]{7})"),
        ("nationality", r"(?:Nationality|Nazionalità|Cetățenie)[:\s]+([A-Z]{3}|[A-Za-z]+)"),
        ("dob",        r"(?:Date of birth|Data di nascita|Data naşterii)[:\s]*([\d]{1,2}[/\.\-][\d]{1,2}[/\.\-][\d]{2,4})"),
        ("expiry",     r"(?:Date of expiry|Scadenza|Data expirării)[:\s]*([\d]{1,2}[/\.\-][\d]{1,2}[/\.\-][\d]{2,4})"),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            fields[label] = m.group(1).strip()
    return fields


def _extract_id_card_fields(text: str) -> dict:
    fields = {}
    for label, pattern in [
        ("surname",    r"(?:Cognome|Surname|Nume)[:\s]+([A-Za-z\s\-']+)"),
        ("given_names",r"(?:Nome|Given name|Prenume)[:\s]+([A-Za-z\s]+)"),
        ("fiscal_code",r"([A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z])"),
        ("dob",        r"(?:Nato il|Born|Născut)[:\s]*([\d]{1,2}[/\.\-][\d]{1,2}[/\.\-][\d]{2,4})"),
        ("address",    r"(?:Residenza|Indirizzo|Address)[:\s]+([^\n]+)"),
        ("doc_number", r"(?:N\.|No\.|Numero)[:\s]*([A-Z]{2}[0-9]{5,7}[A-Z]?)"),
        ("expiry",     r"(?:Scad\.|Scadenza|Expiry)[:\s]*([\d]{1,2}[/\.\-][\d]{1,2}[/\.\-][\d]{2,4})"),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            fields[label] = m.group(1).strip()
    return fields


def _extract_company_doc_fields(text: str) -> dict:
    fields = {}
    for label, pattern in [
        ("company_name",   r"(?:Società|Company|Companie)[:\s]+([A-Z][^\n]{3,60})"),
        ("vat_number",     r"(?:P\.IVA|VAT|TVA|CUI)[:\s]*((?:IT)?[0-9]{11}|[A-Z]{2}[0-9A-Z]+)"),
        ("fiscal_code",    r"(?:C\.F\.|Cod Fiscal)[:\s]*([A-Z0-9]{11,16})"),
        ("reg_number",     r"(?:N\. REA|Reg\. Imprese|Nr\. Reg\. Com)[:\s]*([A-Z0-9\-/]+)"),
        ("address",        r"(?:Sede|Address|Sediu)[:\s]+([^\n]{10,100})"),
        ("share_capital",  r"(?:Capitale|Capital)[:\s]*([\d.,]+\s*(?:EUR|RON|USD))"),
        ("legal_rep",      r"(?:Legale Repr|Rappresentante|Administrator)[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)"),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            fields[label] = m.group(1).strip()
    return fields


def _extract_financial_doc_fields(text: str) -> dict:
    fields = {}
    for label, pattern in [
        ("iban",      r"(?:IBAN)[:\s]*([A-Z]{2}[0-9]{2}[A-Z0-9]{4,30})"),
        ("bic",       r"(?:BIC|SWIFT)[:\s]*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)"),
        ("amount",    r"(?:Totale|Total|Suma)[:\s]*([\d.,]+\s*(?:EUR|RON|USD|GBP)?)"),
        ("date",      r"(?:Data|Date)[:\s]*([\d]{1,2}[/\.\-][\d]{1,2}[/\.\-][\d]{2,4})"),
        ("invoice_no",r"(?:Fattura|Invoice|Nr\. Factură)[:\s]*([A-Z0-9/\-]+)"),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            fields[label] = m.group(1).strip()
    return fields


_EXTRACTORS = {
    "passport":       _extract_passport_fields,
    "id_card":        _extract_id_card_fields,
    "company_doc":    _extract_company_doc_fields,
    "financial_doc":  _extract_financial_doc_fields,
    "driving_license":_extract_id_card_fields,  # subset overlap
}

_REQUIRED_FIELDS = {
    "passport":       ["surname", "given_names", "passport_number", "dob", "expiry", "nationality"],
    "id_card":        ["surname", "given_names", "doc_number", "dob", "fiscal_code"],
    "driving_license":["surname", "given_names", "doc_number", "dob"],
    "company_doc":    ["company_name", "vat_number", "reg_number", "address"],
    "financial_doc":  ["iban", "amount"],
    "contract":       [],
    "generic":        [],
}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class OCRService:
    """
    Estrae testo e campi strutturati da documenti tramite Tesseract OCR.

    Uso:
        svc = OCRService()
        result = svc.extract("passport", source="/path/to/passport.jpg")
        # oppure
        result = svc.extract_from_frappe_url("id_card", "/private/files/carta.pdf")
    """

    def __init__(self, lang: str = TESSERACT_LANGS):
        self.lang = lang

    def extract(self, document_type: str, source=None) -> dict:
        """
        document_type: 'passport'|'id_card'|'driving_license'|'company_doc'|
                       'financial_doc'|'contract'|'generic'
        source: absolute file path, or None (returns empty result)
        """
        if not source:
            return self._empty(document_type, "no_source")

        if not os.path.exists(source):
            return self._empty(document_type, "file_not_found")

        text, provider = _extract_text_from_file(source, self.lang)

        if provider == "error" or not text:
            return self._empty(document_type, provider or "no_text")

        extractor = _EXTRACTORS.get(document_type)
        fields = extractor(text) if extractor else {}

        required = _REQUIRED_FIELDS.get(document_type, [])
        missing = [f for f in required if not fields.get(f)]

        confidence = _avg_confidence(source, self.lang) if provider == "tesseract_image" else (
            0.85 if provider == "native_pdf" else 0.70
        )

        return {
            "document_type": document_type,
            "fields": fields,
            "raw_text": text[:5000],
            "confidence": confidence,
            "missing_fields": missing,
            "provider": provider,
            "lang": self.lang,
        }

    def extract_from_frappe_url(self, document_type: str, file_url: str) -> dict:
        """Risolve un file URL Frappe (/private/files/... o /files/...) e chiama extract()."""
        if "/private/files/" in file_url:
            path = frappe.get_site_path("private", "files",
                                        file_url.split("/private/files/")[-1])
        else:
            path = frappe.get_site_path("public", "files",
                                        file_url.lstrip("/files/"))
        return self.extract(document_type, source=path)

    def extract_text_only(self, file_path: str) -> str:
        """Restituisce solo il testo grezzo senza parsing strutturato."""
        text, _ = _extract_text_from_file(file_path, self.lang)
        return text

    @staticmethod
    def _empty(document_type: str, reason: str) -> dict:
        return {
            "document_type": document_type,
            "fields": {},
            "raw_text": "",
            "confidence": 0.0,
            "missing_fields": [],
            "provider": reason,
        }


# ---------------------------------------------------------------------------
# Frappe whitelist API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def ocr_file(file_url: str, document_type: str = "generic") -> dict:
    """POST-able da desk/portal: estrae testo e campi da un file Frappe."""
    svc = OCRService()
    return svc.extract_from_frappe_url(document_type, file_url)
