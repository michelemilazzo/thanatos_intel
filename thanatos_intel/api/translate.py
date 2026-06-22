"""
Traduzione documenti via LibreTranslate self-hosted.
Cache su disco (DB) per evitare chiamate ripetute sullo stesso testo.
"""
import frappe
import hashlib
import json
import re
import requests
from html import unescape

DEFAULT_URL = "http://10.10.0.4:5000"
TIMEOUT = 30
CACHE_DOCTYPE = None  # uso Frappe cache redis con prefix


def _lt_url():
    return frappe.conf.get("libretranslate_url") or DEFAULT_URL


def _cache_key(text: str, source: str, target: str) -> str:
    h = hashlib.sha1(f"{source}|{target}|{text}".encode()).hexdigest()
    return f"libretrans::{h}"


def _split_html(html: str):
    """Estrae i text-node traducibili da HTML, lascia tag intatti."""
    parts = re.split(r"(<[^>]+>)", html)
    return parts


@frappe.whitelist()
def translate(text: str, target: str = "en", source: str = "it") -> str:
    if not text or not text.strip():
        return text
    key = _cache_key(text, source, target)
    cached = frappe.cache.get_value(key)
    if cached:
        return cached
    try:
        r = requests.post(
            f"{_lt_url()}/translate",
            json={"q": text, "source": source, "target": target, "format": "text"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            out = r.json().get("translatedText", text)
            frappe.cache.set_value(key, out, expires_in_sec=86400 * 30)  # 30 giorni
            return out
        return text
    except Exception as e:
        frappe.log_error(f"LibreTranslate fail: {e}", "translate")
        return text


@frappe.whitelist()
def translate_html(html: str, target: str = "en", source: str = "it") -> str:
    """Traduce solo i text-node, preservando i tag HTML."""
    if not html or not html.strip():
        return html
    parts = _split_html(html)
    out = []
    for p in parts:
        if p.startswith("<") and p.endswith(">"):
            out.append(p)
        else:
            txt = p.strip()
            if txt:
                # mantieni eventuali spazi laterali
                lead = p[: len(p) - len(p.lstrip())]
                trail = p[len(p.rstrip()):]
                out.append(lead + translate(txt, target=target, source=source) + trail)
            else:
                out.append(p)
    return "".join(out)


@frappe.whitelist()
def supported_languages() -> list:
    try:
        r = requests.get(f"{_lt_url()}/languages", timeout=5)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


@frappe.whitelist()
def translate_mandate_pdf(name: str, target_lang: str = "en") -> dict:
    """Genera un PDF del mandato tradotto e lo attacca al doc."""
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request as WzRequest
    from frappe.utils.pdf import get_pdf
    from frappe.utils.file_manager import save_file

    d = frappe.get_doc("Agency Mandate", name)
    # Traduzione body
    src_lang = (frappe.conf.get("mandate_source_lang") or "it")
    if target_lang == src_lang:
        return {"ok": False, "error": "stessa lingua origine"}

    translated_body = translate_html(d.mandate_body or "", target=target_lang, source=src_lang)

    # Render PDF con body sostituito (in memoria, senza salvare doc)
    original_body = d.mandate_body
    d.mandate_body = translated_body
    try:
        builder = EnvironBuilder(method="GET", path="/printview", headers=[("Cookie", "sid=Administrator")])
        frappe.local.request = WzRequest(builder.get_environ())
        frappe.local.form_dict = frappe._dict()
        if not getattr(frappe.local, "session_obj", None):
            import frappe.sessions as _fsessions
            frappe.local.session_obj = _fsessions.Session(user="Administrator", resume=False)
        html = frappe.get_print("Agency Mandate", name, "Mandato d'Incarico", doc=d)
        pdf = get_pdf(html)
        fname = f"{name}_{target_lang}.pdf"
        fdoc = save_file(fname, pdf, "Agency Mandate", name, is_private=1)
        return {"ok": True, "file_url": fdoc.file_url, "lang": target_lang}
    finally:
        d.mandate_body = original_body


@frappe.whitelist()
def translate_proforma_pdf(name: str, target_lang: str = "en") -> dict:
    """Traduce step_title della proforma e genera PDF."""
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request as WzRequest
    from frappe.utils.pdf import get_pdf
    from frappe.utils.file_manager import save_file

    d = frappe.get_doc("Diplomatic Proforma", name)
    src_lang = (frappe.conf.get("mandate_source_lang") or "it")
    if target_lang == src_lang:
        return {"ok": False, "error": "stessa lingua origine"}

    original_title = d.step_title
    d.step_title = translate(d.step_title or "", target=target_lang, source=src_lang)
    try:
        builder = EnvironBuilder(method="GET", path="/printview", headers=[("Cookie", "sid=Administrator")])
        frappe.local.request = WzRequest(builder.get_environ())
        frappe.local.form_dict = frappe._dict()
        if not getattr(frappe.local, "session_obj", None):
            import frappe.sessions as _fsessions
            frappe.local.session_obj = _fsessions.Session(user="Administrator", resume=False)
        html = frappe.get_print("Diplomatic Proforma", name, "Proforma DDD", doc=d)
        pdf = get_pdf(html)
        fname = f"{name}_{target_lang}.pdf"
        fdoc = save_file(fname, pdf, "Diplomatic Proforma", name, is_private=1)
        return {"ok": True, "file_url": fdoc.file_url, "lang": target_lang}
    finally:
        d.step_title = original_title


# ----------- ACCETTAZIONE PROFORMA via Signature Request -------------------
@frappe.whitelist()
def create_proforma_signature(name: str) -> dict:
    """Crea Signature Request Basic per firma per accettazione della proforma."""
    from frappe.utils import add_to_date, now_datetime
    pf = frappe.get_doc("Diplomatic Proforma", name)
    # PDF source: usa ultimo PDF allegato
    last = frappe.db.sql("""SELECT file_url FROM `tabFile`
        WHERE attached_to_doctype=%s AND attached_to_name=%s
        AND file_url LIKE %s ORDER BY creation DESC LIMIT 1""",
        ("Diplomatic Proforma", name, "%.pdf"))
    if not last:
        # genera PDF italiano standard se non c'è
        return {"ok": False, "error": "Nessun PDF allegato. Genera prima il PDF (Print / Genera PDF tradotto)."}

    # Recupero email cliente da intestatario_fattura → Customer → Contact
    customer = None
    mandate = frappe.get_doc("Agency Mandate", pf.mandate) if pf.mandate else None
    if mandate and mandate.intestatario_fattura:
        customer = mandate.intestatario_fattura
    signer_email = None
    signer_name = customer or "Cliente"
    if customer:
        row = frappe.db.sql("""SELECT c.email_id, c.first_name, c.last_name
            FROM `tabContact` c JOIN `tabDynamic Link` dl ON dl.parent=c.name
            WHERE dl.link_doctype='Customer' AND dl.link_name=%s LIMIT 1""", (customer,), as_dict=1)
        if row:
            signer_email = row[0].email_id
            signer_name = f"{row[0].first_name or ''} {row[0].last_name or ''}".strip() or customer
    # Fallback: applicant del mandato
    if not signer_email and mandate and mandate.applicant:
        try:
            ap = frappe.get_doc("Applicant Profile", mandate.applicant)
            signer_email = ap.email
            signer_name = ap.full_legal_name or signer_name
        except Exception:
            pass

    if not signer_email:
        return {"ok": False, "error": "Impossibile risolvere email firmatario"}

    # Riusa se esiste già un draft per la stessa proforma
    existing = frappe.db.get_value("Signature Request", {
        "reference_doctype":"Diplomatic Proforma", "reference_name":name, "status":"Draft"}, "name")
    if existing:
        sr = frappe.get_doc("Signature Request", existing)
    else:
        sr = frappe.new_doc("Signature Request")
        sr.reference_doctype = "Diplomatic Proforma"
        sr.reference_name = name
    sr.source_pdf = last[0][0]
    sr.signing_plan = "Basic / Sealed"
    sr.signing_mode = "Single"
    sr.signer_email = signer_email
    sr.signer_name = signer_name + " — Accettazione proforma"
    sr.status = "Draft"
    sr.expires_at = add_to_date(now_datetime(), days=7)
    sr.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": sr.name, "signer_email": signer_email}
