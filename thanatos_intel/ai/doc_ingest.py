"""MMOS AI — Ingest documenti.

Orchestrazione end-to-end di un documento allegato a un caso:
  1. OCR (ai.ocr_service.ocr_file) — testo + campi regex
  2. Estrazione intelligente via MMOS AI gateway (classifica, entità, sintesi, risk)
  3. Crea un reperto Investigation Evidence (catena di custodia SHA-256)
  4. Conta i token a billing (ai_meter)

L'AI fa il lavoro: l'operatore carica, MMOS AI ingerisce e struttura.
"""
import json
import frappe
from frappe import _
from frappe.utils import now_datetime

from thanatos_intel.ai.ocr_service import ocr_file

EXTRACT_SYSTEM = (
    "Sei un analista forense documentale di Thanatos Intel (agenzia ISO). Ricevi il testo "
    "OCR di un documento e i suoi metadati forensi. Analizza il documento e VALUTANE "
    "L'AUTENTICITA'. Rispondi SOLO con JSON valido, nessun testo fuori dal JSON, struttura: "
    '{"document_type": "passport|id_card|company_doc|financial_doc|contract|generic", '
    '"language": "iso", "summary": "sintesi in italiano (max 60 parole)", '
    '"entities": [{"name":"", "type":"person|company|address|account|other", "role":""}], '
    '"key_fields": {}, "dates": [], "risk_flags": ["eventuali anomalie/red flag"], '
    '"authenticity": "autentico|dubbio|manomesso|contraffatto|non_determinabile", '
    '"authenticity_confidence": 0.0, '
    '"authenticity_indicators": ["indizi concreti a supporto del verdetto"]}\n'
    "REGOLE AUTENTICITA' (sii prudente, ISO): valuta coerenza interna (date/importi/nomi/"
    "P.IVA), presenza e plausibilita' di numeri di protocollo/visti/firme, congruenza tra i "
    "metadati forniti (produttore, date creazione/modifica, firma digitale, revisioni "
    "incrementali) e il contenuto. Segnala: date di modifica successive sospette, piu' "
    "revisioni incrementali, produttori da editing (Photoshop, GIMP), assenza di firma "
    "digitale dove attesa, font/allineamenti incoerenti, importi/totali che non quadrano. "
    "NON dichiarare 'autentico' senza elementi positivi: in assenza di indizi usa "
    "'non_determinabile'; se ci sono anomalie usa 'dubbio'; usa 'manomesso'/'contraffatto' "
    "solo con indizi forti. authenticity_confidence in [0,1]."
)


def _gateway(message, system="", task_type="extract", session_id=None):
    """Chiama il gateway MMOS AI (POST /chat). Ritorna il dict risposta o None."""
    import requests
    url = (frappe.conf.get("mmos_ai_gateway_url") or "").rstrip("/")
    key = frappe.conf.get("mmos_ai_gateway_key")
    if not url or not key:
        return None
    try:
        r = requests.post(
            f"{url}/chat",
            json={"session_id": session_id or f"{frappe.local.site}:{frappe.session.user}:{frappe.generate_hash(length=8)}",
                  "task_type": task_type, "message": message, "system": system},
            headers={"X-MMOS-AI-KEY": key, "Content-Type": "application/json"},
            timeout=180,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "doc_ingest gateway")
        return None


def _extract_json(text):
    if not text:
        return None
    # togli eventuale fence ```json
    t = text.strip()
    if "```" in t:
        import re as _re
        m = _re.search(r"```(?:json)?\s*(.*?)```", t, _re.DOTALL)
        if m:
            t = m.group(1)
    try:
        return json.loads(t)
    except Exception:
        pass
    import re
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _normalize(parsed):
    """Normalizza l'output AI nel nostro schema, accettando sia il nostro
    formato sia il formato 'actions' (doctype/fields) dell'assistant gateway."""
    if not parsed:
        return None
    if "entities" in parsed or "summary" in parsed or "key_fields" in parsed:
        return parsed
    if "actions" in parsed and isinstance(parsed["actions"], list):
        ents, fields, labels = [], {}, []
        for a in parsed["actions"]:
            f = a.get("fields", {}) or {}
            dt = (a.get("doctype") or "")
            labels.append(a.get("label", ""))
            name = (f.get("customer_name") or f.get("company_name") or f.get("supplier_name")
                    or (str(f.get("first_name", "")) + " " + str(f.get("last_name", ""))).strip()
                    or a.get("label", ""))
            if dt == "Contact" or f.get("first_name"):
                typ = "person"
            elif dt in ("Customer", "Supplier", "Company") or f.get("customer_type") == "Company":
                typ = "company"
            else:
                typ = "other"
            if name and name.strip():
                ents.append({"name": name.strip(), "type": typ, "role": f.get("designation", "")})
            for k, v in f.items():
                if isinstance(v, (str, int, float)):
                    fields[k] = v
        return {"document_type": "generic", "summary": "; ".join(x for x in labels if x),
                "entities": ents, "key_fields": fields, "risk_flags": []}
    return parsed


_AUTH_MAP = {"autentico": "Autentico", "dubbio": "Dubbio", "manomesso": "Manomesso",
             "contraffatto": "Contraffatto", "non_determinabile": "Non determinabile"}


def _ensure_evidence_authfields():
    """Crea (idempotente) i campi forensi su Investigation Evidence. Pipeline ISO."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_field
    specs = [
        {"fieldname": "authenticity", "label": "Autenticità", "fieldtype": "Select",
         "options": "\nAutentico\nDubbio\nManomesso\nContraffatto\nNon determinabile",
         "insert_after": "evidence_type"},
        {"fieldname": "authenticity_confidence", "label": "Confidenza autenticità",
         "fieldtype": "Float", "insert_after": "authenticity"},
        {"fieldname": "authenticity_indicators", "label": "Indicatori autenticità",
         "fieldtype": "Small Text", "insert_after": "authenticity_confidence"},
        {"fieldname": "forensics_json", "label": "Metadati forensi", "fieldtype": "Small Text",
         "insert_after": "authenticity_indicators"},
        {"fieldname": "investigative_questions", "label": "Domande investigative",
         "fieldtype": "Long Text", "insert_after": "forensics_json"},
    ]
    for s in specs:
        if not frappe.db.exists("Custom Field", f"Investigation Evidence-{s['fieldname']}"):
            try:
                create_custom_field("Investigation Evidence", s)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "ensure authfields")


def _sha256(path):
    import hashlib
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _doc_forensics(file_url):
    """Metadati forensi di base: nativo/scansione, date metadati PDF, firma digitale,
    produttore, revisioni incrementali, hash SHA-256."""
    import os
    info = {}
    try:
        fd = frappe.get_doc("File", {"file_url": file_url})
        path = fd.get_full_path()
        info["file_ext"] = os.path.splitext(path)[1].lower()
        info["size_bytes"] = os.path.getsize(path)
        info["sha256"] = _sha256(path)
        if info["file_ext"] == ".pdf":
            try:
                from pypdf import PdfReader
                r = PdfReader(path)
                meta = r.metadata or {}
                info["pdf_producer"] = str(meta.get("/Producer", "") or "")
                info["pdf_creator"] = str(meta.get("/Creator", "") or "")
                info["pdf_created"] = str(meta.get("/CreationDate", "") or "")
                info["pdf_modified"] = str(meta.get("/ModDate", "") or "")
                info["num_pages"] = len(r.pages)
                has_sig = False
                try:
                    root = r.trailer["/Root"]
                    if "/AcroForm" in root:
                        for f in (root["/AcroForm"].get("/Fields", []) or []):
                            obj = f.get_object()
                            if obj.get("/FT") == "/Sig" and obj.get("/V"):
                                has_sig = True
                                break
                except Exception:
                    pass
                info["has_digital_signature"] = has_sig
                with open(path, "rb") as fh:
                    info["incremental_updates"] = max(0, fh.read().count(b"%%EOF") - 1)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "doc forensics pdf")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "doc forensics")
    return info


def _create_evidence(file_url, case, parsed, ocr, forensics=None):
    forensics = forensics or {}
    parsed = parsed or {}
    auth_raw = (parsed.get("authenticity") or "non_determinabile").lower().replace(" ", "_")
    auth = _AUTH_MAP.get(auth_raw, "Non determinabile")
    indicators = parsed.get("authenticity_indicators") or []
    note_lines = []
    if parsed:
        note_lines.append("— Sintesi AI —")
        note_lines.append(parsed.get("summary") or "")
        note_lines.append(f"Autenticità: {auth}"
                          + (f" — {'; '.join(indicators)}" if indicators else ""))
        if parsed.get("risk_flags"):
            note_lines.append("Red flag: " + "; ".join(parsed["risk_flags"]))
        if parsed.get("key_fields"):
            note_lines.append("Campi: " + json.dumps(parsed["key_fields"], ensure_ascii=False))
    note_lines.append(f"OCR provider: {ocr.get('provider')} · confidenza: {ocr.get('confidence')}")
    ev = frappe.get_doc({
        "doctype": "Investigation Evidence",
        "investigation_case": case,
        "evidence_name": (parsed.get("document_type") or "Documento") + " — AI ingest",
        "evidence_type": "Document",
        "attached_file": file_url,
        "acquisition_date": now_datetime(),
        "source": "MMOS AI ingest",
        "hash_value": forensics.get("sha256") or "",
        "custody_status": "Verified" if auth == "Autentico" else "Received",
        "authenticity": auth,
        "authenticity_confidence": parsed.get("authenticity_confidence") or 0,
        "authenticity_indicators": "; ".join(indicators)[:500],
        "forensics_json": json.dumps(forensics, ensure_ascii=False)[:500],
        "notes": "\n".join([l for l in note_lines if l]),
    })
    ev.flags.ignore_mandatory = True
    ev.insert(ignore_permissions=True)
    return ev.name


def _meter(ai, case):
    if not ai:
        return
    try:
        usage = ai.get("usage") or {}
        tin, tout = usage.get("tokens_in", 0), usage.get("tokens_out", 0)
        if not (tin or tout):
            return
        client = frappe.db.get_value("Investigation Case", case, "client")
        from thanatos_intel.billing.ai_meter import record_usage
        record_usage(client=client, model=ai.get("model", "default"),
                     tokens_in=tin, tokens_out=tout, reference=case)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "doc_ingest meter")


def _read_text_fallback(file_url):
    import os
    try:
        fd = frappe.get_doc("File", {"file_url": file_url})
        ext = os.path.splitext(fd.file_name or "")[1].lower()
        if ext in (".docx", ".doc"):
            import docx as _docx
            doc = _docx.Document(fd.get_full_path())
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        content = fd.get_content()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        return content or ""
    except Exception:
        frappe.log_error(frappe.get_traceback(), "doc_ingest fallback")
        return ""


@frappe.whitelist()
def ingest_document(file_url, investigation_case, document_type="generic"):
    """Orchestratore: OCR + estrazione AI + reperto in catena di custodia.
    Usato dal bottone sul caso e dal canale operatore WhatsApp."""
    if not file_url or not investigation_case:
        frappe.throw(_("file_url e investigation_case sono obbligatori"))

    _ensure_evidence_authfields()
    forensics = _doc_forensics(file_url)

    try:
        ocr = ocr_file(file_url, document_type) or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ingest_document ocr")
        ocr = {}
    text = (ocr.get("raw_text") or "").strip()
    if not text:
        text = (_read_text_fallback(file_url) or "").strip()
        if text:
            ocr.setdefault("provider", "text-extract")

    parsed, ai = None, None
    if text:
        from thanatos_intel.ai.case_architect import _resp_text
        fblock = "\n".join(f"{k}: {v}" for k, v in forensics.items() if k != "sha256")
        ai = _gateway(f"Metadati forensi del file:\n{fblock}\n\nTesto del documento:\n\n{text[:12000]}",
                      system=EXTRACT_SYSTEM, task_type="extract")
        parsed = _normalize(_extract_json(_resp_text(ai)))

    evidence = _create_evidence(file_url, investigation_case, parsed, ocr, forensics)
    _meter(ai, investigation_case)
    return {
        "ok": True,
        "evidence": evidence,
        "extracted": parsed or {},
        "authenticity": _AUTH_MAP.get((parsed or {}).get("authenticity", ""), "Non determinabile"),
        "ocr": {"provider": ocr.get("provider"), "confidence": ocr.get("confidence")},
        "ai_available": bool(ai),
    }
