"""OCR Service — estrazione testo e campi strutturati da documenti.

Supporta:
  - Immagini: JPEG, PNG, TIFF, BMP, WEBP
  - PDF: testo nativo (pypdf) + fallback rasterizzato (pdf2image + Tesseract)
  - Documenti supportati: passport, id_card, driving_license, company_doc,
                          financial_doc, contract, generic

Lingue default: eng+ita+ron.
Auto-install: se una lingua non è disponibile localmente viene installata
automaticamente via apt (tesseract-ocr-{lang}).
"""

import os
import re
import subprocess
import frappe


# ---------------------------------------------------------------------------
# Fallback VISION AI — per immagini dove Tesseract fallisce (bassa risoluzione,
# foto/thumbnail compresse, documenti identita' con font decorativi/MRZ).
# Usa un modello multimodale via OpenRouter (chiave nel vault ai_engines,
# fallback site_config). Nessuna regressione se la chiave manca: si torna al
# comportamento Tesseract-only.
# ---------------------------------------------------------------------------
_VISION_DOC_TYPES = {"passport", "id_card", "driving_license"}


def _vision_secret(field):
    try:
        from thanatos_intel.ai.ops_brain import _vault
        return _vault(field, "ai_engines")
    except Exception:
        return None


def _vision_ocr_image(image_path: str) -> str:
    """Legge un'immagine con un modello vision AI e ritorna il testo/i campi
    rilevanti come testo libero (poi ri-parsato dagli _EXTRACTORS esistenti).
    Ritorna '' se non disponibile o in errore (nessuna eccezione propagata)."""
    import base64
    import requests

    key = _vision_secret("openrouter_key")
    if not key:
        return ""
    base_url = (_vision_secret("openrouter_url") or "https://openrouter.ai/api/v1").rstrip("/")
    model = _vision_secret("vision_model") or "nvidia/nemotron-nano-12b-v2-vl:free"

    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(image_path)[1].lstrip(".").lower() or "jpeg"
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        prompt = (
            "Trascrivi TUTTO il testo leggibile in questa immagine di documento, "
            "riga per riga, incluse eventuali righe MRZ (le due righe in fondo ai "
            "passaporti con simboli < e maiuscole). Non riassumere, non tradurre: "
            "trascrizione letterale, anche se il documento è ruotato o di bassa "
            "qualità. Se vedi campi come nome, cognome, data di nascita, numero "
            "documento, elencali chiaramente."
        )
        r = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "HTTP-Referer": "https://thanatos.agency",
                     "X-Title": "Thanatos OCR Vision",
                     "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }],
                "temperature": 0.1,
            },
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        return (d.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ocr_service vision fallback")
        return ""


SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}
TESSERACT_LANGS = "eng+ita+ron"
OCR_DPI = 300

# Tesseract lang code → apt package name (dove diverso dal pattern tesseract-ocr-{lang})
_APT_OVERRIDES = {
    "chi_sim": "tesseract-ocr-chi-sim",
    "chi_tra": "tesseract-ocr-chi-tra",
    "chi_sim_vert": "tesseract-ocr-chi-sim",
    "chi_tra_vert": "tesseract-ocr-chi-tra",
}

# Lingua ISO 639-1/2 → codice Tesseract
_ISO_TO_TESS = {
    "en": "eng", "it": "ita", "ro": "ron", "fr": "fra", "de": "deu",
    "es": "spa", "pt": "por", "ru": "rus", "ar": "ara", "zh": "chi_sim",
    "ja": "jpn", "ko": "kor", "nl": "nld", "pl": "pol", "uk": "ukr",
    "tr": "tur", "sv": "swe", "no": "nor", "da": "dan", "fi": "fin",
    "cs": "ces", "sk": "slk", "hu": "hun", "hr": "hrv", "sr": "srp",
    "bg": "bul", "el": "ell", "he": "heb", "hi": "hin", "th": "tha",
    "vi": "vie", "id": "ind", "ms": "msa", "fa": "fas",
    # già in formato tess
    "eng": "eng", "ita": "ita", "ron": "ron", "fra": "fra", "deu": "deu",
    "spa": "spa", "por": "por", "rus": "rus", "ara": "ara",
    "jpn": "jpn", "kor": "kor", "nld": "nld", "pol": "pol",
}


def _ensure_lang(lang_code: str) -> bool:
    """Verifica che il language pack Tesseract sia installato, altrimenti lo installa.
    Ritorna True se disponibile dopo l'operazione.
    """
    try:
        import pytesseract
        available = pytesseract.get_languages()
        if lang_code in available:
            return True
        # Non disponibile — installa
        pkg = _APT_OVERRIDES.get(lang_code, f"tesseract-ocr-{lang_code}")
        frappe.log_error(f"Tesseract lang '{lang_code}' mancante — installo {pkg}", "OCRService")
        result = subprocess.run(
            ["apt-get", "install", "-y", "--no-install-recommends", pkg],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            frappe.log_error(f"Installato {pkg} con successo", "OCRService")
            return True
        frappe.log_error(f"apt install {pkg} fallito: {result.stderr[:300]}", "OCRService")
        return False
    except Exception as e:
        frappe.log_error(f"_ensure_lang error: {e}", "OCRService")
        return False


def _build_lang_string(langs) -> str:
    """Costruisce la stringa lingua per Tesseract (es. 'eng+ita+fra').
    Accetta stringa 'eng+ita' o lista ['eng','ita'] o codici ISO.
    Garantisce eng come base. Auto-installa lingue mancanti.
    """
    if not langs:
        return TESSERACT_LANGS

    if isinstance(langs, str):
        parts = [l.strip() for l in langs.replace(",", "+").split("+") if l.strip()]
    else:
        parts = [str(l).strip() for l in langs if l]

    # Normalizza ISO → Tesseract
    tess_parts = []
    for p in parts:
        tess = _ISO_TO_TESS.get(p.lower(), p)
        tess_parts.append(tess)

    # Aggiungi eng come base se non presente
    if "eng" not in tess_parts:
        tess_parts.insert(0, "eng")

    # Rimuovi duplicati mantenendo ordine
    seen = set()
    unique = [x for x in tess_parts if not (x in seen or seen.add(x))]

    # Verifica/installa ogni lingua
    valid = []
    for lang in unique:
        if _ensure_lang(lang):
            valid.append(lang)
        else:
            frappe.log_error(f"Lingua '{lang}' non disponibile, saltata", "OCRService")

    return "+".join(valid) if valid else TESSERACT_LANGS


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

    if ext in (".docx", ".doc"):
        try:
            import docx as _docx
            doc = _docx.Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            if text.strip():
                return text.strip(), "python_docx"
        except Exception as e:
            frappe.log_error(str(e), "OCRService docx")
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
        result = svc.extract("passport", source="/path/to/doc.jpg", lang="fra")
        result = svc.extract("contract", source="/path/to/doc.pdf", lang=["deu","eng"])
        result = svc.extract_from_frappe_url("id_card", "/private/files/carta.pdf")
    """

    def __init__(self, lang=None):
        self.lang = _build_lang_string(lang) if lang else TESSERACT_LANGS

    def extract(self, document_type: str, source=None, lang=None) -> dict:
        """
        document_type: 'passport'|'id_card'|'driving_license'|'company_doc'|
                       'financial_doc'|'contract'|'generic'
        source: absolute file path, or None (returns empty result)
        lang: stringa 'fra' / 'fra+eng', lista ['fra','eng'], o codice ISO 'fr'.
              Se None usa il lang dell'istanza. La lingua viene auto-installata
              se non disponibile localmente.
        """
        if not source:
            return self._empty(document_type, "no_source")

        if not os.path.exists(source):
            return self._empty(document_type, "file_not_found")

        active_lang = _build_lang_string(lang) if lang else self.lang
        text, provider = _extract_text_from_file(source, active_lang)

        # Fallback VISION AI: Tesseract vuoto, oppure documento identità dove
        # la lettura visiva accurata (MRZ, foto compresse) conta di più.
        used_vision = False
        is_image = os.path.splitext(source)[1].lower() in SUPPORTED_IMAGE_EXT
        if is_image and (not text or document_type in _VISION_DOC_TYPES):
            vtext = _vision_ocr_image(source)
            if vtext and len(vtext) > len(text or ""):
                text = vtext
                provider = "vision_ai"
                used_vision = True

        if provider == "error" or not text:
            return self._empty(document_type, provider or "no_text")

        extractor = _EXTRACTORS.get(document_type)
        fields = extractor(text) if extractor else {}

        required = _REQUIRED_FIELDS.get(document_type, [])
        missing = [f for f in required if not fields.get(f)]

        if used_vision:
            confidence = 0.75
        else:
            confidence = _avg_confidence(source, active_lang) if provider == "tesseract_image" else (
                0.85 if provider == "native_pdf" else 0.70
            )

        return {
            "document_type": document_type,
            "fields": fields,
            "raw_text": text[:5000],
            "confidence": confidence,
            "missing_fields": missing,
            "provider": provider,
            "lang": active_lang,
        }

    def extract_from_frappe_url(self, document_type: str, file_url: str, lang=None) -> dict:
        """Risolve un file URL Frappe (/private/files/... o /files/...) e chiama extract()."""
        if "/private/files/" in file_url:
            path = frappe.get_site_path("private", "files",
                                        file_url.split("/private/files/")[-1])
        else:
            path = frappe.get_site_path("public", "files",
                                        file_url.lstrip("/files/"))
        return self.extract(document_type, source=path, lang=lang)

    def extract_text_only(self, file_path: str, lang=None) -> str:
        """Restituisce solo il testo grezzo senza parsing strutturato."""
        active_lang = _build_lang_string(lang) if lang else self.lang
        text, _ = _extract_text_from_file(file_path, active_lang)
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
def ocr_file(file_url: str, document_type: str = "generic", lang: str = None) -> dict:
    """POST-able da desk/portal: estrae testo e campi da un file Frappe.

    lang: codice lingua o lista separata da '+' (es. 'fra', 'deu+eng', 'zh').
          Se la lingua non è installata viene installata automaticamente.
          Supporta codici ISO 639-1 (it, fr, de, ru...) e Tesseract (ita, fra, deu...).
    """
    svc = OCRService()
    return svc.extract_from_frappe_url(document_type, file_url, lang=lang)
