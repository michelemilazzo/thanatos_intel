"""Ponte Frappe ↔ media server WhatsApp Calling (aiortc su ai-core).

- register_recording: il media server, a fine chiamata, carica la registrazione →
  crea/aggiorna Call Log + avvia trascrizione con diarizzazione.
- operator_join: il Centralino inoltra l'SDP offer dell'operatore al media server
  per unirsi alla chiamata (bridge audio live).
- forward_incoming_call: chiamato dal webhook (evento connect) per accettare la
  chiamata sul media server.
"""
import json
import frappe
from frappe import _
from frappe.utils.password import get_decrypted_password


def _media_url():
    return frappe.conf.get("wa_calling_url", "http://10.10.0.4:18093")


def forward_incoming_call(call_id, pnid, frm, sdp, wa_number=None):
    """Inoltra l'evento connect al media server che accetta la chiamata."""
    import requests
    name = wa_number.phone_number if wa_number else frappe.db.get_value(
        "WhatsApp Number", {"meta_phone_number_id": pnid, "is_active": 1}, "name")
    if not name:
        return {"ok": False, "error": "numero non trovato"}
    token = get_decrypted_password("WhatsApp Number", name, "meta_access_token")
    base = frappe.utils.get_url()
    op_nums = _operator_chain(name)
    op_num = op_nums[0] if op_nums else ""
    ring_timeout = int(frappe.db.get_value("WhatsApp Number", name, "ring_timeout") or 25)
    announce_text = _announce_text(op_num)
    r = requests.post(
        f"{_media_url()}/incoming",
        json={"call_id": call_id, "pnid": pnid, "from": frm, "sdp": sdp,
              "token": token, "frappe_url": base, "operator_number": op_num,
              "operator_numbers": op_nums, "ring_timeout": ring_timeout,
              "announce_text": announce_text},
        timeout=20,
    )
    return r.json()


def _sos_operators(wa_name):
    """Numeri da far squillare su SOS: site_config sos_call_operators (csv),
    altrimenti la catena operatori standard del numero."""
    raw = (frappe.conf.get("sos_call_operators") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return _operator_chain(wa_name)


@frappe.whitelist(allow_guest=True)
def sos_incoming():
    """Webhook dall'app di protezione (Angelo Custode) su pressione SOS: fa
    squillare gli operatori con annuncio vocale. Protetto da secret ?k=.
    Payload atteso (dal worker protect): {type,subject,loc,lat,lon}."""
    import requests
    secret = frappe.conf.get("sos_webhook_secret")
    k = frappe.request.args.get("k") or frappe.form_dict.get("k")
    if not secret or k != secret:
        frappe.local.response["http_status_code"] = 403
        return {"ok": False, "error": "auth"}
    try:
        body = json.loads(frappe.request.get_data() or b"{}")
    except Exception:
        body = {}
    subject = (body.get("subject") or "").strip() or "persona protetta"
    name = frappe.db.get_value("WhatsApp Number", {"provider": "Meta Cloud API", "is_active": 1}, "name") \
        or frappe.db.get_value("WhatsApp Number", {"is_active": 1}, "name")
    if not name:
        return {"ok": False, "error": "numero non configurato"}
    ops = _sos_operators(name)
    if not ops:
        return {"ok": False, "error": "nessun operatore SOS configurato"}
    pnid = frappe.db.get_value("WhatsApp Number", name, "meta_phone_number_id")
    token = get_decrypted_password("WhatsApp Number", name, "meta_access_token")
    announce = ("Allarme S O S dal protetto %s. La posizione e' stata inviata su WhatsApp. "
                "Intervenire con urgenza." % subject)
    try:
        r = requests.post("%s/sos-call" % _media_url(),
                          json={"operators": ops, "pnid": pnid, "token": token,
                                "frappe_url": frappe.utils.get_url(), "announce_text": announce},
                          timeout=20)
        out = r.json()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "sos_incoming media")
        return {"ok": False, "error": str(e)[:200]}
    frappe.logger("sos").info("SOS call subject=%s ops=%s -> %s" % (subject, ops, out))
    return {"ok": True, "dialed": out.get("dialed")}


def _operator_chain(wa_name):
    """Lista ordinata di numeri operatore dal pannello (WhatsApp Operator Route).
    Fallback: call_forward_number + investigatori 'Available' (compat)."""
    chain = []
    routes = frappe.get_all(
        "WhatsApp Operator Route",
        filters={"parent": wa_name, "parenttype": "WhatsApp Number", "enabled": 1},
        fields=["phone", "investigator"], order_by="idx asc")
    for r in routes:
        ph = (r.get("phone") or "").strip()
        if not ph and r.get("investigator"):
            ph = (frappe.db.get_value("Investigator", r["investigator"], "phone") or "").strip()
        if ph and ph not in chain:
            chain.append(ph)
    if chain:
        return chain
    primary = (frappe.db.get_value("WhatsApp Number", wa_name, "call_forward_number") or "").strip()
    if primary:
        chain.append(primary)
    for inv in frappe.get_all("Investigator", filters={"availability": "Available"},
                              fields=["phone"]):
        ph = (inv.get("phone") or "").strip()
        if ph and ph not in chain:
            chain.append(ph)
    return chain


def _resolve_caller(number):
    """Identifica il chiamante da rubrica (Intelligence Contact) e Intel Lead:
    nome/azienda + a quale operatore e' assegnato."""
    res = {"name": "", "org": "", "contact": "", "lead": "", "assigned_to": "", "assigned_name": ""}
    if not number:
        return res
    n = number if number.startswith("+") else "+" + number
    bare = number.lstrip("+")
    c = frappe.db.get_value("Intelligence Contact", {"whatsapp": ["in", [n, bare]]},
                            ["name", "full_name", "linked_entity"], as_dict=True)         or frappe.db.get_value("Intelligence Contact", {"phone": ["in", [n, bare]]},
                               ["name", "full_name", "linked_entity"], as_dict=True)
    if c:
        res["contact"] = c.name
        if c.full_name and not c.full_name.startswith("Contatto WhatsApp"):
            res["name"] = c.full_name
        if c.linked_entity:
            res["org"] = c.linked_entity
    lead = frappe.db.get_value("Intel Lead", {"source_identifier": ["in", [n, bare]]},
                               ["name", "source_name", "assigned_to"], as_dict=True,
                               order_by="last_message_at desc")
    if lead:
        res["lead"] = lead.name
        if not res["name"] and lead.source_name:
            res["name"] = lead.source_name
        if lead.assigned_to:
            res["assigned_to"] = lead.assigned_to
            res["assigned_name"] = frappe.db.get_value("User", lead.assigned_to, "full_name") or lead.assigned_to
    return res


def _announce_text(op_num):
    """Annuncio di registrazione + lingua dell'operatore (dalla scheda Investigator).
    Conforme a Legea 329/2003 + GDPR (avviso di registrazione)."""
    langs = ""
    digits = "".join(c for c in (op_num or "") if c.isdigit())
    if digits:
        tail = digits[-9:]
        inv = frappe.db.sql(
            """SELECT languages FROM `tabInvestigator`
               WHERE languages IS NOT NULL AND languages != ''
                 AND REPLACE(REPLACE(REPLACE(phone,' ',''),'+',''),'-','') LIKE %s
               LIMIT 1""",
            ("%" + tail,), as_dict=True)
        if inv:
            langs = (inv[0].languages or "").strip()
    lingua = f"L'operatore le rispondera in {langs}. " if langs else ""
    return ("Benvenuto a Thanatos Investigazioni. La informiamo che, ai sensi della "
            "normativa vigente, questa chiamata potrebbe essere registrata. "
            f"{lingua}Resti in linea, la mettiamo in contatto con un operatore.")


def operator_answer(call_id, sdp):
    """Inoltra al media server la SDP answer dell'operatore (gamba in uscita).
    Ritorna True se quel call_id era una gamba operatore nota (gestita)."""
    import requests
    try:
        r = requests.post(f"{_media_url()}/operator/answer",
                          json={"operator_call_id": call_id, "sdp": sdp}, timeout=15)
        return r.status_code == 200 and bool(r.json().get("ok"))
    except Exception:
        return False


@frappe.whitelist()
def operator_join(call_id, sdp):
    """Il Centralino: l'operatore si unisce alla chiamata. Ritorna l'SDP answer."""
    import requests
    r = requests.post(f"{_media_url()}/operator/offer",
                      json={"call_id": call_id, "sdp": sdp}, timeout=20)
    return r.json()


@frappe.whitelist(allow_guest=True)
def register_recording():
    """Chiamato dal media server a fine chiamata: salva la registrazione → Call Log + trascrizione.
    Auth: header X-WA-Calling-Secret."""
    secret = frappe.get_request_header("X-WA-Calling-Secret", "")
    if not secret or secret != frappe.conf.get("wa_calling_secret"):
        frappe.throw(_("Non autorizzato"), frappe.PermissionError)

    frm = frappe.form_dict.get("from_number", "")
    call_id = frappe.form_dict.get("call_id", "")
    duration = int(frappe.form_dict.get("duration", 0) or 0)
    answered = int(frappe.form_dict.get("answered", 0) or 0)
    files = frappe.request.files
    audio = files.get("file") if files else None

    # trova/crea la scheda contatto (numero + nominativo) e recupera i dati
    from thanatos_intel.ingest.contacts import ensure_contact_from_wa
    n = frm if frm.startswith("+") else "+" + frm
    contact = ensure_contact_from_wa(frm, "", "Chiamata WhatsApp")
    caller_name = frappe.db.get_value("Intelligence Contact", contact, "full_name") if contact else ""
    contact_client = frappe.db.get_value("Intelligence Contact", contact, "linked_entity") if contact else None

    # Call Log già creato all'arrivo? aggiorna; altrimenti crea
    existing = frappe.db.get_value("Call Log", {"summary": ["like", f"%{call_id}%"]}, "name")
    if existing:
        doc = frappe.get_doc("Call Log", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Call Log", "called_at": frappe.utils.now_datetime(),
            "direction": "Entrante", "caller_number": n,
            "summary": f"Chiamata WhatsApp · id {call_id}",
        })
        doc.insert(ignore_permissions=True)

    # popola più campi possibili
    doc.db_set("caller_number", n)
    if caller_name:
        doc.db_set("caller_name", caller_name)
    if contact:
        doc.db_set("linked_contact", contact)
    doc.db_set("handled_by", frappe.session.user if frappe.session.user != "Guest" else "Administrator")
    doc.db_set("outcome", "Risposta" if answered else "Messaggio vocale")
    doc.db_set("duration_seconds", duration % 60)
    doc.db_set("duration_minutes", duration // 60)

    if audio:
        import os
        content = audio.stream.read()
        fname = f"wa-call-{call_id[:18]}.ogg"
        # 1. audio su StorageBox (box autoritativo, non riempie il disco del bench)
        box_dir = os.path.join(
            frappe.conf.get("call_recordings_box", "/mnt/thanatos-box/call-recordings"),
            doc.get("linked_case") or "_non-assegnate")
        file_url = f"/private/files/{fname}"
        try:
            os.makedirs(box_dir, exist_ok=True)
            box_path = os.path.join(box_dir, fname)
            with open(box_path, "wb") as f:
                f.write(content)
            # 2. symlink nel private/files del sito → StorageBox (Frappe serve seguendo il link)
            link_path = frappe.get_site_path("private", "files", fname)
            if os.path.islink(link_path) or os.path.exists(link_path):
                os.remove(link_path)
            os.symlink(box_path, link_path)
            fdoc = frappe.get_doc({
                "doctype": "File", "file_name": fname, "file_url": file_url,
                "attached_to_doctype": "Call Log", "attached_to_name": doc.name,
                "is_private": 1,
            }).insert(ignore_permissions=True)
        except Exception:
            # fallback: salva nel filesystem del bench se il box non è disponibile
            frappe.log_error(frappe.get_traceback(), "call rec box save")
            fdoc = frappe.get_doc({
                "doctype": "File", "file_name": fname,
                "attached_to_doctype": "Call Log", "attached_to_name": doc.name,
                "is_private": 1, "content": content,
            }).insert(ignore_permissions=True)
            file_url = fdoc.file_url
        doc.db_set("audio_file", file_url)
        doc.db_set("transcription_status", "In elaborazione")
        frappe.db.commit()
        # trascrizione con diarizzazione (Whisper locale)
        frappe.enqueue("thanatos_intel.ingest.transcription.transcribe_call_log",
                       queue="long", timeout=900, call_log_name=doc.name)
    frappe.db.commit()
    return {"ok": True, "call_log": doc.name}


def reorganize_call_files(call_log):
    """Sposta registrazione audio + trascrizione .md nella cartella del caso
    collegato (o _non-assegnate) sul box, aggiornando i symlink. Idempotente."""
    import os
    import shutil
    cl = frappe.get_doc("Call Log", call_log)
    sub = cl.get("linked_case") or "_non-assegnate"
    url = (cl.get("audio_file") or "").strip()
    if url:
        fname = url.split("/")[-1]
        link = frappe.get_site_path("private", "files", fname)
        rec_base = frappe.conf.get("call_recordings_box", "/mnt/thanatos-box/call-recordings")
        dest_dir = os.path.join(rec_base, sub)
        dest = os.path.join(dest_dir, fname)
        cur = os.path.realpath(link) if os.path.islink(link) else (link if os.path.exists(link) else None)
        if cur and os.path.exists(cur) and os.path.abspath(cur) != os.path.abspath(dest):
            try:
                os.makedirs(dest_dir, exist_ok=True)
                if not os.path.exists(dest):
                    shutil.move(cur, dest)
                if os.path.islink(link) or os.path.exists(link):
                    os.remove(link)
                os.symlink(dest, link)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "reorganize call rec")
    try:
        from thanatos_intel.ingest.transcription import _archive_transcript_md
        _archive_transcript_md(call_log)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "reorganize call md")


def call_log_files_on_update(doc, method=None):
    """Quando il caso collegato cambia, riorganizza i file della chiamata per caso."""
    try:
        if doc.has_value_changed("linked_case") and doc.get("audio_file"):
            reorganize_call_files(doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "call_log on_update reorg")
