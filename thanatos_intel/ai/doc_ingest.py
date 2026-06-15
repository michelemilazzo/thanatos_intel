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
    "Sei un analista investigativo di Thanatos Intel. Ricevi il testo OCR di un documento. "
    "Rispondi SOLO con JSON valido, nessun testo fuori dal JSON, con questa struttura: "
    '{"document_type": "passport|id_card|company_doc|financial_doc|contract|generic", '
    '"language": "iso", "summary": "sintesi in italiano (max 60 parole)", '
    '"entities": [{"name":"", "type":"person|company|address|account|other", "role":""}], '
    '"key_fields": {}, "dates": [], "risk_flags": ["eventuali anomalie/red flag"]}'
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
            json={"session_id": session_id or frappe.generate_hash(length=12),
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


def _create_evidence(file_url, case, parsed, ocr):
    note_lines = []
    if parsed:
        note_lines.append("— Sintesi AI —")
        note_lines.append(parsed.get("summary") or "")
        if parsed.get("risk_flags"):
            note_lines.append("Red flag: " + "; ".join(parsed["risk_flags"]))
        if parsed.get("key_fields"):
            note_lines.append("Campi: " + json.dumps(parsed["key_fields"], ensure_ascii=False))
    note_lines.append(f"OCR provider: {ocr.get('provider')} · confidenza: {ocr.get('confidence')}")
    ev = frappe.get_doc({
        "doctype": "Investigation Evidence",
        "investigation_case": case,
        "evidence_name": (parsed or {}).get("document_type", "Documento") + " — AI ingest",
        "evidence_type": "Document",
        "attached_file": file_url,
        "acquisition_date": now_datetime(),
        "source": "MMOS AI ingest",
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
    """Legge il testo da file non-OCR (txt/md/csv/json/log) via File.get_content()."""
    try:
        fd = frappe.get_doc("File", {"file_url": file_url})
        content = fd.get_content()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        return content or ""
    except Exception:
        return ""


@frappe.whitelist()
def ingest_document(file_url, investigation_case, document_type="generic", create_evidence=1):
    """Ingest completo di un documento allegato a un caso."""
    if not frappe.db.exists("Investigation Case", investigation_case):
        frappe.throw(_("Caso non trovato"))

    # 1. OCR
    ocr = ocr_file(file_url, document_type=document_type)
    text = (ocr or {}).get("raw_text", "") or ""
    if not text.strip():
        text = _read_text_fallback(file_url)
        if text:
            ocr = dict(ocr or {}, provider="plain_text", confidence=1.0)

    # 2. AI extraction
    ai = _gateway(message=f"Tipo dichiarato: {document_type}\n\nTesto OCR:\n{text[:9000]}",
                  system=EXTRACT_SYSTEM, task_type="extract")
    parsed = _normalize(_extract_json(ai.get("reply"))) if ai else None

    # 3. Evidence (catena custodia)
    evidence = None
    if int(create_evidence or 0):
        evidence = _create_evidence(file_url, investigation_case, parsed, ocr or {})

    # 4. billing
    _meter(ai, investigation_case)

    return {
        "ok": True,
        "ai_available": bool(ai),
        "ocr": {"provider": (ocr or {}).get("provider"),
                "confidence": (ocr or {}).get("confidence"),
                "chars": len(text)},
        "extracted": parsed,
        "evidence": evidence,
    }
