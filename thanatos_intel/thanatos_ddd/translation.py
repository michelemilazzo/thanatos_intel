"""Client LibreTranslate (self-hosted su ai-mmos-core:5000)."""
import frappe
import requests

LT_URL = (frappe.conf.get("libretranslate_url")
          if hasattr(frappe, "conf") else None) or "http://172.17.0.1:5000"


@frappe.whitelist()
def translate(text: str, source: str = "auto", target: str = "en") -> dict:
    """Traduce testo via LibreTranslate. Ritorna {translatedText, detectedLanguage}."""
    if not text or not text.strip():
        return {"translatedText": "", "detectedLanguage": source}
    try:
        r = requests.post(f"{LT_URL}/translate",
                          json={"q": text, "source": source, "target": target,
                                "format": "text"},
                          timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        frappe.log_error(str(e), "DddTranslate")
        return {"translatedText": text, "detectedLanguage": "unknown",
                "error": str(e)[:200]}


@frappe.whitelist()
def translate_passport_raw(passport_analysis: str, target: str = "en") -> dict:
    """Traduce il raw_text di un Passport Analysis nella lingua target."""
    pa = frappe.get_doc("Passport Analysis", passport_analysis)
    res = translate(pa.raw_text or "", source="auto", target=target)
    return {"passport_analysis": passport_analysis,
            "detected": res.get("detectedLanguage"),
            "translated": res.get("translatedText")}


@frappe.whitelist()
def list_languages() -> list:
    try:
        return requests.get(f"{LT_URL}/languages", timeout=10).json()
    except Exception as e:
        frappe.log_error(str(e), "DddTranslateLangs")
        return []
