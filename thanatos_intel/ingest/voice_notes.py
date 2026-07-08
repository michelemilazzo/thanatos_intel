"""Note vocali WhatsApp → download media Meta + trascrizione AssemblyAI.

Flusso (background job da webhook):
  1. scarica l'audio dal media_id Meta (URL temporaneo + auth)
  2. lo allega come File all'Intel Lead
  3. trascrive con AssemblyAI (language detection)
  4. aggiorna il contenuto del lead e dell'ultimo messaggio inbound con la trascrizione
"""
import frappe
from frappe.utils.password import get_decrypted_password


_GRAPH = "https://graph.facebook.com/v21.0"


def _target_msg(lead_name, wa_message_id):
    """Trova il messaggio inbound da aggiornare: per wa_message_id se noto,
    altrimenti l'ultimo inbound del lead."""
    if wa_message_id:
        rows = frappe.db.sql(
            """SELECT name, content FROM `tabIntel Lead Message`
               WHERE parent=%s AND wa_message_id=%s LIMIT 1""",
            (lead_name, wa_message_id), as_dict=True,
        )
        if rows:
            return rows
    return frappe.db.sql(
        """SELECT name, content FROM `tabIntel Lead Message`
           WHERE parent=%s AND direction='Inbound'
           ORDER BY sent_at DESC LIMIT 1""",
        (lead_name,), as_dict=True,
    )


def _resolve_token(wa_phone: str | None) -> tuple[str, str]:
    """Restituisce (access_token, wa_doc_name) del numero Meta da usare."""
    name = wa_phone
    if not name:
        name = frappe.db.get_value(
            "WhatsApp Number",
            {"provider": "Meta Cloud API", "is_active": 1},
            "name",
        )
    if not name:
        raise ValueError("Nessun WhatsApp Number Meta attivo")
    token = get_decrypted_password("WhatsApp Number", name, "meta_access_token")
    if not token:
        raise ValueError("meta_access_token mancante")
    return token, name


def download_meta_media(media_id: str, access_token: str) -> tuple[bytes, str]:
    """Scarica i bytes del media da Meta. Restituisce (content, mime_type)."""
    import requests

    meta = requests.get(
        f"{_GRAPH}/{media_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    meta.raise_for_status()
    info = meta.json()
    url = info.get("url")
    mime = info.get("mime_type", "audio/ogg")
    if not url:
        raise ValueError("URL media non disponibile")

    binr = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )
    binr.raise_for_status()
    return binr.content, mime


def _transcribe_whisper(content: bytes) -> str:
    """Trascrizione via Whisper locale su ai-core (gratis, privacy-preserving)."""
    import requests

    url = frappe.conf.get("whisper_url", "http://10.10.0.4:18092")
    r = requests.post(
        f"{url}/transcribe",
        files={"audio": ("voice.ogg", content)},
        timeout=180,
    )
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


def _transcribe_assemblyai(content: bytes, api_key: str) -> str:
    import requests
    import time

    up = requests.post(
        "https://api.assemblyai.com/v2/upload",
        headers={"authorization": api_key},
        data=content,
        timeout=120,
    )
    up.raise_for_status()
    audio_url = up.json()["upload_url"]

    job = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json={"audio_url": audio_url, "language_detection": True},
        headers={"authorization": api_key, "content-type": "application/json"},
        timeout=30,
    )
    job.raise_for_status()
    job_id = job.json()["id"]

    for _ in range(90):  # max ~7.5 min
        time.sleep(5)
        poll = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{job_id}",
            headers={"authorization": api_key}, timeout=15,
        ).json()
        if poll.get("status") == "completed":
            return poll.get("text", "") or ""
        if poll.get("status") == "error":
            raise ValueError(poll.get("error", "errore AssemblyAI"))
    raise TimeoutError("Timeout trascrizione nota vocale")


def _transcribe(content: bytes) -> str:
    """Trascrive: priorità Whisper locale, fallback AssemblyAI se configurato."""
    try:
        return _transcribe_whisper(content)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whisper locale fallito")
        api_key = frappe.conf.get("assemblyai_api_key")
        if api_key:
            return _transcribe_assemblyai(content, api_key)
        raise


def process_voice_note(lead_name: str, media_id: str, wa_phone: str | None = None,
                       wa_message_id: str = "", notify_bot: bool = True):
    """Background job: scarica, allega e trascrive la nota vocale."""
    try:
        token, _ = _resolve_token(wa_phone)
        content, mime = download_meta_media(media_id, token)

        ext = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
               "audio/amr": "amr", "audio/wav": "wav"}.get(mime.split(";")[0], "ogg")
        fname = f"wa-voice-{media_id[:12]}.{ext}"

        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": fname,
            "attached_to_doctype": "Intel Lead",
            "attached_to_name": lead_name,
            "is_private": 1,
            "content": content,
        }).insert(ignore_permissions=True)

        text = ""
        try:
            text = _transcribe(content)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"voice transcribe {lead_name}")

        label = f"🎤 {text}" if text else "🎤 [nota vocale ricevuta — trascrizione non disponibile]"

        # aggiorna l'ultimo messaggio inbound del lead
        msg = _target_msg(lead_name, wa_message_id)
        if msg:
            frappe.db.set_value("Intel Lead Message", msg[0].name, {
                "content": label,
                "media_url": file_doc.file_url,
            })

        # aggiorna il contenuto del lead se era placeholder
        cur = frappe.db.get_value("Intel Lead", lead_name, "content") or ""
        if cur.strip() in ("[audio]", "[media]", ""):
            frappe.db.set_value("Intel Lead", lead_name, "content", label)

        frappe.db.commit()

        # bot AI risponde alla nota vocale trascritta
        if text and notify_bot:
            try:
                from thanatos_intel.ingest.wa_bot import trigger_for_lead
                trigger_for_lead(lead_name, wa_phone)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"wa_bot voice {lead_name}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"process_voice_note {lead_name}")


_MEDIA_META = {
    "image": ("📷", "immagine", {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}, "jpg"),
    "video": ("🎥", "video", {"video/mp4": "mp4", "video/3gpp": "3gp"}, "mp4"),
    "document": ("📄", "documento", {"application/pdf": "pdf"}, "bin"),
}


def process_media_attachment(lead_name: str, media_id: str, media_type: str,
                             filename: str = "", wa_phone: str | None = None,
                             wa_message_id: str = "", notify_bot: bool = True):
    """Background job: scarica e allega un media (immagine/video/documento) all'Intel Lead."""
    try:
        token, _ = _resolve_token(wa_phone)
        content, mime = download_meta_media(media_id, token)

        icon, word, ext_map, default_ext = _MEDIA_META.get(
            media_type, ("📎", "allegato", {}, "bin"))
        ext = ext_map.get(mime.split(";")[0], default_ext)
        fname = filename or f"wa-{media_type}-{media_id[:12]}.{ext}"

        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": fname,
            "attached_to_doctype": "Intel Lead",
            "attached_to_name": lead_name,
            "is_private": 1,
            "content": content,
        }).insert(ignore_permissions=True)

        label = f"{icon} {fname}" if filename else f"{icon} [{word}]"

        msg = _target_msg(lead_name, wa_message_id)
        if msg:
            # se c'era una didascalia, la conserva
            cap = (msg[0].content or "").strip()
            new_content = f"{label}\n{cap}" if cap and not cap.startswith("[") else label
            frappe.db.set_value("Intel Lead Message", msg[0].name, {
                "content": new_content,
                "media_url": file_doc.file_url,
            })

        cur = frappe.db.get_value("Intel Lead", lead_name, "content") or ""
        if cur.strip() in (f"[{media_type}]", "[media]", ""):
            frappe.db.set_value("Intel Lead", lead_name, "content", label)

        frappe.db.commit()

        # Auto-ingest: ogni immagine/documento arrivato su WA diventa SUBITO
        # un reperto — nessun comando manuale richiesto. Il routing (caso
        # esistente agganciato / caso esistente per stesso soggetto / caso
        # nuovo) e' deciso da auto_ingest_case_media().
        if media_type in ("image", "document"):
            frappe.enqueue(
                "thanatos_intel.ingest.voice_notes.auto_ingest_case_media",
                queue="long", timeout=300,
                lead_name=lead_name, file_url=file_doc.file_url, wa_phone=wa_phone,
            )

        # bot AI prende atto del media ricevuto e prosegue la conversazione
        if notify_bot:
            try:
                from thanatos_intel.ingest.wa_bot import trigger_for_lead
                trigger_for_lead(lead_name, wa_phone)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"wa_bot media {lead_name}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"process_media_attachment {lead_name}")


_PIVA_RE = __import__("re").compile(r"\b\d{11}\b")
_CF_RE = __import__("re").compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")


def _match_existing_case_by_identifier(text):
    """Cerca un caso APERTO che gia' contiene lo stesso identificativo forte
    (P.IVA 11 cifre o Codice Fiscale) del nuovo documento, tra le sintesi AI
    dei reperti gia' presenti. Match UNIVOCO -> ritorna il caso; se
    ambiguo (l'identificativo compare in piu' casi aperti) o assente,
    ritorna None — si preferisce aprire un caso nuovo piuttosto che
    sbagliare l'aggancio."""
    ids = set(_PIVA_RE.findall(text or "")) | set(_CF_RE.findall((text or "").upper()))
    for ident in ids:
        rows = frappe.db.sql("""
            SELECT DISTINCT ie.investigation_case AS c
            FROM `tabInvestigation Evidence` ie
            JOIN `tabInvestigation Case` ic ON ic.name = ie.investigation_case
            WHERE ie.notes LIKE %s AND ic.status NOT IN ('Closed', 'Cancelled')
        """, (f"%{ident}%",), as_dict=True)
        cases = {r["c"] for r in rows}
        if len(cases) == 1:
            return cases.pop()
    return None


@frappe.whitelist()
def auto_ingest_case_media(lead_name, file_url, wa_phone=None):
    """Ingest automatico di un'immagine/documento appena arrivato su WhatsApp.

    Routing:
      1) chat gia' agganciata a un caso -> reperto in quel caso
      2) chat senza caso -> cerca un caso APERTO con lo stesso P.IVA/CF gia'
         visto nei reperti (match univoco); se trovato, aggancia la chat li'
      3) nessun match -> apre un caso NUOVO (stessa pipeline di "apri un caso",
         classifica tutti gli allegati recenti del lead)

    Se il documento e' un'identita' (passport/id_card) lancia anche
    l'analyzer MRZ dedicato per i dati anagrafici strutturati (nome, data di
    nascita, numero documento). Notifica sempre l'operatore con l'esito."""
    from thanatos_intel.ai.doc_ingest import ingest_document
    from thanatos_intel.ai.ocr_service import ocr_file
    from thanatos_intel.ingest.operator_console import _reply, run_open_case

    sender = frappe.db.get_value("Intel Lead", lead_name, "source_identifier")
    case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
    matched_now = False

    if not case:
        # Lock per evitare che piu' media arrivati in rapida successione
        # (parallelizzati su piu' worker) aprano CIASCUNO un caso nuovo per
        # lo stesso lead. Solo chi prende il lock decide; gli altri aspettano
        # il suo esito invece di duplicare.
        import time
        lock_key = f"auto_ingest_case_lock:{lead_name}"
        got_lock = bool(frappe.cache.set(lock_key, "1", nx=True, ex=120))
        if not got_lock:
            for _ in range(10):
                time.sleep(1.5)
                case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
                if case:
                    break
            if not case:
                # l'altro job non ha ancora finito: ri-accoda invece di
                # rischiare un caso duplicato (evita anche loop stretti)
                frappe.enqueue(
                    "thanatos_intel.ingest.voice_notes.auto_ingest_case_media",
                    queue="long", timeout=300,
                    lead_name=lead_name, file_url=file_url, wa_phone=wa_phone,
                )
                return {"ok": False, "reason": "requeued, case decision in progress"}
        else:
            try:
                # doppio controllo: un altro job potrebbe aver appena
                # agganciato il caso mentre aspettavamo il lock
                case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
                if not case:
                    try:
                        from thanatos_intel.ai.doc_ingest import _read_text_fallback
                        ocr = ocr_file(file_url, "generic") or {}
                        text = (ocr.get("raw_text") or "").strip()
                        if not text:
                            text = (_read_text_fallback(file_url) or "").strip()
                        case = _match_existing_case_by_identifier(text)
                    except Exception:
                        frappe.log_error(frappe.get_traceback(), "auto_ingest match_existing")
                        case = None
                    if case:
                        frappe.db.set_value("Intel Lead", lead_name, "linked_case", case)
                        frappe.db.commit()
                        matched_now = True
                    else:
                        # nessun caso esistente corrisponde: ne apre uno nuovo
                        # (stessa logica di "apri un caso")
                        result = run_open_case(lead_name, wa_phone=wa_phone,
                                               sender=sender, operator=None)
                        frappe.cache.delete(lock_key)
                        return result
            finally:
                frappe.cache.delete(lock_key)

    try:
        r = ingest_document(file_url=file_url, investigation_case=case,
                            document_type="generic") or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"auto_ingest_case_media {case}")
        return {"ok": False}

    ex = r.get("extracted") or {}
    doc_type = ex.get("document_type", "generic")
    summary = (ex.get("summary") or "").strip()
    header = f"\U0001F4CE Nuovo reperto in *{case}*"
    if matched_now:
        header += " (stesso soggetto di un caso gia\' aperto)"
    lines = [header + f": {doc_type}"]
    if summary:
        lines.append(summary[:300])

    if doc_type in ("passport", "id_card"):
        try:
            from thanatos_intel.thanatos_documents.passport import analyzer
            pr = analyzer.analyze_file(file_url=file_url, investigation_case=case)
            if pr and pr.get("name"):
                paa = frappe.get_doc("Passport Analysis", pr["name"])
                if paa.surname or paa.given_names:
                    lines.append("")
                    lines.append("\U0001F6C2 Documento identita\' letto:")
                    lines.append(f"{paa.surname or ''} {paa.given_names or ''}".strip())
                    if paa.date_of_birth:
                        lines.append(f"Nato: {paa.date_of_birth}")
                    if paa.document_number:
                        lines.append(f"Doc: {paa.document_number}")
                    lines.append(f"Verdetto: {paa.verdict or 'n/d'}")
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"auto_ingest passport {case}")

    if wa_phone and sender:
        try:
            _reply(wa_phone, sender, lead_name, "\n".join(lines))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "auto_ingest_case_media reply")
    return {"ok": True, "case": case, "document_type": doc_type}
