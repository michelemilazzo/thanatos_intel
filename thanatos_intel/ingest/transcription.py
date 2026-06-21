"""Trascrizione audio con diarizzazione voci.

Provider supportati (site_config.json):
  transcription_provider  : "assemblyai" | "openai" (default: assemblyai)
  assemblyai_api_key      : chiave AssemblyAI  (https://app.assemblyai.com)
  openai_api_key          : chiave OpenAI      (se provider=openai, solo trascrizione)

AssemblyAI: trascrizione + speaker labels A/B/C... → asincrono via job Frappe.
OpenAI Whisper: solo trascrizione (nessuna diarizzazione), sincrono.
"""
import json
import frappe
from frappe import _
from frappe.utils import now_datetime


def _provider():
    # default Whisper locale (gratis, privacy). assemblyai per diarizzazione voci.
    return frappe.conf.get("transcription_provider", "whisper")


# ─── Entry point (chiamato via enqueue) ──────────────────────────────────────

def transcribe_call_log(call_log_name: str):
    """Background job: trascrive il file audio del Call Log."""
    doc = frappe.get_doc("Call Log", call_log_name)
    if not doc.audio_file:
        _set_error(doc, "Nessun file audio allegato.")
        return

    provider = _provider()
    try:
        if provider == "openai":
            _transcribe_openai(doc)
        elif provider == "assemblyai":
            _transcribe_assemblyai(doc)
        else:
            _transcribe_whisper_local(doc)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"transcribe_call_log {call_log_name}")
        _set_error(doc, str(e)[:500])
        return
    # arricchimento AI: riassunto + azioni dalla trascrizione (best-effort)
    try:
        _ai_enrich_call(frappe.get_doc("Call Log", call_log_name))
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"ai_enrich {call_log_name}")


def _ai_enrich_call(doc):
    """Genera riassunto + azioni da fare dalla trascrizione via gateway MMOS AI."""
    text = (doc.transcript_text or "").strip()
    if not text or len(text) < 15:
        return
    from thanatos_intel.ai.doc_ingest import _gateway, _extract_json
    system = ("Sei l'assistente di un'agenzia investigativa (Thanatos). "
              "Analizza la trascrizione di una chiamata telefonica e rispondi SOLO in JSON valido "
              'con: {"summary": "riassunto conciso in italiano (max 4 frasi)", '
              '"action_items": ["azione 1", "azione 2"], '
              '"caller_intent": "motivo della chiamata in poche parole", '
              '"risk_flags": ["eventuali segnali di rischio/frode, altrimenti []"]}')
    res = _gateway(message=f"Trascrizione chiamata:\n{text[:6000]}",
                   system=system, task_type="extract")
    if not res:
        return
    content = res.get("reply") or res.get("message") or res.get("content") or ""
    parsed = _extract_json(content) or {}
    summary = (parsed.get("summary") or "").strip()
    intent = (parsed.get("caller_intent") or "").strip()
    actions = parsed.get("action_items") or []
    risks = parsed.get("risk_flags") or []

    if summary or intent:
        body = ""
        if intent:
            body += f"<p><b>Motivo:</b> {frappe.utils.escape_html(intent)}</p>"
        if summary:
            body += f"<p>{frappe.utils.escape_html(summary)}</p>"
        if risks:
            body += "<p><b>⚠️ Segnali:</b> " + ", ".join(frappe.utils.escape_html(str(r)) for r in risks) + "</p>"
        doc.db_set("summary", body)
    if actions:
        items = "".join(f"<li>{frappe.utils.escape_html(str(a))}</li>" for a in actions)
        doc.db_set("action_items", f"<ul>{items}</ul>")
    frappe.db.commit()


# ─── Whisper locale (ai-core, gratis, no diarizzazione) ──────────────────────

def _audio_bytes(doc) -> bytes:
    """Restituisce i bytes del file audio del Call Log."""
    import requests
    file_url = doc.audio_file
    if file_url and file_url.startswith("/"):
        from frappe.utils.file_manager import get_file
        _fname, content = get_file(file_url)
        return content
    r = requests.get(file_url, timeout=60)
    r.raise_for_status()
    return r.content


def _transcribe_whisper_local(doc):
    import requests

    url = frappe.conf.get("whisper_url", "http://10.10.0.4:18092")
    content = _audio_bytes(doc)
    # diarizzazione attiva (2 speaker default) per separare le voci della chiamata
    r = requests.post(
        f"{url}/transcribe",
        files={"audio": ("call.ogg", content)},
        data={"diarize": "true", "num_speakers": 2,
              "language": frappe.conf.get("call_transcription_language", "it")},
        timeout=900,
    )
    r.raise_for_status()
    data = r.json()
    full_text = (data.get("text") or "").strip()
    segments = [
        {"speaker": s.get("speaker", "A"), "start_ms": s.get("start_ms", 0),
         "end_ms": s.get("end_ms", 0), "text": s.get("text", "")}
        for s in (data.get("segments") or [])
    ]
    if not segments and full_text:
        segments = [{"speaker": "A", "start_ms": 0, "end_ms": 0, "text": full_text}]

    doc.db_set("transcript_raw", json.dumps(segments))
    doc.db_set("transcript_text", full_text)
    doc.db_set("transcription_status", "Completato")
    frappe.db.commit()
    _notify_done(doc)


# ─── AssemblyAI ──────────────────────────────────────────────────────────────

def _transcribe_assemblyai(doc):
    import requests, time

    api_key = frappe.conf.get("assemblyai_api_key")
    if not api_key:
        _set_error(doc, "assemblyai_api_key mancante in site_config.")
        return

    headers = {"authorization": api_key, "content-type": "application/json"}

    # 1. Ottieni URL pubblico o upload diretto
    audio_url = _resolve_audio_url(doc)

    # 2. Richiesta trascrizione con speaker_labels
    resp = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json={
            "audio_url": audio_url,
            "speaker_labels": True,
            "language_detection": True,
        },
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    job_id = resp.json()["id"]
    doc.db_set("transcription_job_id", job_id)
    doc.db_set("transcription_status", "In elaborazione")
    frappe.db.commit()

    # 3. Poll fino al completamento (max 10 min)
    for _ in range(120):
        time.sleep(5)
        poll = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{job_id}",
            headers=headers, timeout=15,
        ).json()
        status = poll.get("status")
        if status == "completed":
            _store_assemblyai_result(doc, poll)
            return
        if status == "error":
            _set_error(doc, poll.get("error", "Errore AssemblyAI sconosciuto"))
            return

    _set_error(doc, "Timeout trascrizione (>10 minuti).")


def _resolve_audio_url(doc) -> str:
    """Restituisce URL pubblico del file audio, o lo carica su AssemblyAI."""
    import requests

    api_key = frappe.conf.get("assemblyai_api_key")
    file_url = doc.audio_file

    # Se è un path interno Frappe, lo leggo e carico su AssemblyAI
    if file_url and file_url.startswith("/"):
        file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["file_url", "is_private"], as_dict=True)
        if not file_doc:
            frappe.throw(_("File non trovato: {0}").format(file_url))
        # Leggi bytes dal filesystem Frappe
        from frappe.utils.file_manager import get_file
        fname, content = get_file(file_url)
        upload_resp = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers={"authorization": api_key},
            data=content,
            timeout=120,
        )
        upload_resp.raise_for_status()
        return upload_resp.json()["upload_url"]

    return file_url  # URL già pubblico (es. S3, recording_url)


def _store_assemblyai_result(doc, result: dict):
    utterances = result.get("utterances") or []
    words = result.get("words") or []
    full_text = result.get("text") or ""

    # Costruisce segmenti speaker
    segments = [
        {
            "speaker": u.get("speaker", "?"),
            "start_ms": u.get("start", 0),
            "end_ms": u.get("end", 0),
            "text": u.get("text", ""),
        }
        for u in utterances
    ]

    doc.db_set("transcript_raw", json.dumps(segments))
    doc.db_set("transcript_text", full_text)
    doc.db_set("transcription_status", "Completato")
    doc.db_set("transcription_job_id", result.get("id", ""))
    frappe.db.commit()

    # Notifica operatore
    _notify_done(doc)


# ─── OpenAI Whisper ──────────────────────────────────────────────────────────

def _transcribe_openai(doc):
    import requests

    api_key = frappe.conf.get("openai_api_key")
    if not api_key:
        _set_error(doc, "openai_api_key mancante in site_config.")
        return

    file_url = doc.audio_file
    if file_url and file_url.startswith("/"):
        from frappe.utils.file_manager import get_file
        fname, content = get_file(file_url)
    else:
        r = requests.get(file_url, timeout=60)
        r.raise_for_status()
        content = r.content
        fname = file_url.split("/")[-1] or "audio.mp3"

    resp = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": (fname, content)},
        data={"model": "whisper-1", "response_format": "verbose_json"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    full_text = data.get("text", "")
    # Whisper non ha diarizzazione: creiamo un unico segmento
    segments = [{"speaker": "A", "start_ms": 0, "end_ms": 0, "text": full_text}]

    doc.db_set("transcript_raw", json.dumps(segments))
    doc.db_set("transcript_text", full_text)
    doc.db_set("transcription_status", "Completato")
    frappe.db.commit()
    _notify_done(doc)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _set_error(doc, message: str):
    doc.db_set("transcription_status", "Errore")
    frappe.log_error(message, f"Transcription {doc.name}")
    frappe.db.commit()


def _notify_done(doc):
    user = doc.handled_by or doc.owner
    if not user:
        return
    try:
        frappe.publish_realtime(
            event="msgprint",
            message={"message": f"✅ Trascrizione completata: <b>{doc.name}</b>", "indicator": "green"},
            user=user,
        )
        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": "Trascrizione chiamata completata",
            "email_content": f"La trascrizione di {doc.name} è pronta.",
            "for_user": user,
            "type": "Alert",
            "document_type": "Call Log",
            "document_name": doc.name,
            "from_user": "Administrator",
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass


def render_transcript_html(segments: list, speaker_a: str = "Operatore", speaker_b: str = "") -> str:
    """Genera HTML con bolle per ogni segmento speaker."""
    if not segments:
        return "<p style='color:#666'>Nessun segmento disponibile.</p>"

    labels = {"A": speaker_a or "Operatore"}
    if speaker_b:
        labels["B"] = speaker_b

    def _fmt_ms(ms):
        s = int(ms / 1000)
        return f"{s // 60}:{s % 60:02d}"

    rows = []
    for seg in segments:
        sp = seg.get("speaker", "?")
        label = labels.get(sp, f"Speaker {sp}")
        is_a = sp == "A"
        align = "flex-start" if is_a else "flex-end"
        bg = "#1e2435" if is_a else "#C8A96E"
        color = "#e8e8e8" if is_a else "#0A0E1A"
        ts = _fmt_ms(seg.get("start_ms", 0))
        text = frappe.utils.escape_html(seg.get("text", ""))
        rows.append(
            f'<div style="display:flex;justify-content:{align};margin:4px 0">'
            f'<div style="max-width:75%;background:{bg};color:{color};'
            f'border-radius:10px;padding:8px 12px;font-size:13px;line-height:1.5">'
            f'<div style="font-size:10px;font-weight:bold;margin-bottom:3px;opacity:.7">'
            f'{label} · {ts}</div>'
            f'{text}'
            f'</div></div>'
        )

    return (
        '<div style="background:#0d1117;border-radius:8px;padding:12px;'
        'max-height:500px;overflow-y:auto">' + "".join(rows) + "</div>"
    )
