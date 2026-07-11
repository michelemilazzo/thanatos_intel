"""Bot AI conversazionale su WhatsApp (triage + handoff).

L'output del modello viene inviato TESTUALMENTE al cliente come messaggio WhatsApp.
Triage servizi + handoff operatore. Riusa il gateway MMOS AI.
"""
import frappe
from frappe.utils import now_datetime

_SYS = (
    "Sei l'assistente virtuale di Thanatos Investigazioni, agenzia di "
    "investigazioni e intelligence (sede in Romania, Legea 329/2003, conforme GDPR). "
    "Parli italiano, tono professionale, riservato, empatico ma sobrio. "
    "IMPORTANTISSIMO: il tuo output viene inviato TESTUALMENTE al cliente come "
    "messaggio WhatsApp. Scrivi SEMPRE e SOLO il messaggio rivolto direttamente al "
    "cliente (dandogli del Lei). NON descrivere la conversazione, NON dire che stai "
    "aspettando o che il cliente non ha risposto, NON parlare del 'cliente' in terza "
    "persona, NON spiegare cosa farai: scrivi solo cio' che diresti al cliente adesso. "
    "Compiti: accogliere, spiegare a grandi linee i servizi (investigazioni private, "
    "due diligence, OSINT, rintracci, tutela aziendale, infedelta', recupero "
    "informazioni), capire il bisogno con UNA domanda mirata per volta. "
    "Se il cliente ripete la stessa cosa o sembra bloccato, NON ripetere la stessa "
    "domanda: riassumi e proponi il passo successivo o passa a un operatore. "
    "REGOLE FERREE: non promettere risultati ne' dare consulenza legale; non chiedere "
    "mai password, credenziali, OTP o dati di pagamento; non fornire MAI numeri di telefono, recapiti o contatti diretti in chat (sara un operatore a ricontattare il cliente); non rivelare nomi di "
    "investigatori ne' dettagli operativi interni. "
    "Se il cliente chiede di parlare con una persona/operatore/umano o di essere "
    "richiamato, oppure se la richiesta e' concreta/urgente o riguarda un preventivo o "
    "un caso aperto: rispondi con UNA frase breve di presa in carico e aggiungi su una "
    "riga a parte il marcatore [[HANDOFF]] (l'utente non lo vedra'). "
    "Risposte brevi: massimo 60-70 parole."
)

_HANDOFF_MARK = "[[HANDOFF]]"
_HISTORY = 12

_STATUS_IT = {"Draft": "in preparazione", "Open": "aperta", "In Progress": "in lavorazione",
              "Review": "in revisione", "Closed": "conclusa", "Cancelled": "annullata"}


def _client_case_context(lead_name):
    """Contesto CONFINATO al cliente di questa chat: solo le SUE pratiche,
    identificate dal numero WhatsApp del lead. Nessun dato di altri clienti,
    nessun dettaglio operativo/reperti. Ritorna '' se il numero non corrisponde
    a un cliente censito."""
    try:
        lead = frappe.db.get_value("Intel Lead", lead_name,
                                   ["whatsapp_number", "source_identifier"], as_dict=True)
        if not lead:
            return ""
        # source_identifier = numero del CLIENTE (whatsapp_number è il nostro business number)
        phone = (lead.source_identifier or "").strip()
        digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
        if not digits:
            return ""
        client = frappe.db.sql("""
            SELECT name, client_name FROM `tabInvestigation Client`
            WHERE REPLACE(REPLACE(REPLACE(phone,' ',''),'+',''),'-','') LIKE %s
            LIMIT 1
        """, (f"%{digits}",), as_dict=True)
        if not client:
            return ""
        client = client[0]
        cases = frappe.get_all("Investigation Case",
                               filters={"client": client.name},
                               fields=["name", "case_title", "status", "payment_status"],
                               order_by="modified desc", limit_page_length=5)
        if not cases:
            return ""
        lines = [f"CLIENTE IDENTIFICATO: {client.client_name}. Le sue pratiche:"]
        for c in cases:
            st = _STATUS_IT.get(c.status, c.status or "?")
            pay = {"Pending": "pagamento in attesa", "Paid": "pagata",
                   "Partial": "pagamento parziale"}.get(c.payment_status, "")
            lines.append(f"- {c.name} «{c.case_title or ''}»: {st}"
                         + (f", {pay}" if pay else ""))
        lines.append(
            "Se il cliente chiede lo stato della sua pratica riferisci SOLO queste "
            "informazioni (stato e pagamento), in modo rassicurante, senza dettagli "
            "operativi, reperti o nomi interni. Per domande di merito sulla pratica, "
            "presa in carico + [[HANDOFF]].")
        return "\n".join(lines)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa_bot _client_case_context")
        return ""


_META_SIGNS = (
    "non c'è ancora", "non c'e ancora", "sto aspettando", "risponderò quando",
    "rispondero quando", "il cliente non ha", "in attesa che il cliente",
    "attendo che il cliente", "aspettando che il cliente", "quando il cliente",
    "non c'è una nuova risposta", "non c'e una nuova risposta",
)


def _is_meta(t):
    tl = (t or "").lower()
    return any(s in tl for s in _META_SIGNS)


def _wants_human(t):
    import re
    tl = (t or "").lower()
    if "parlare con un" in tl or "con un operatore" in tl or "con una persona" in tl:
        return True
    return bool(
        re.search(r"\b(operatore|umano|umana|persona|consulente|agente)\b", tl)
        and re.search(r"(parlar|parla|sentir|contatt|vorrei|voglio|posso|chiama)", tl)
    )


def _last_inbound(lead_name):
    rows = frappe.get_all(
        "Intel Lead Message",
        filters={"parent": lead_name, "direction": "Inbound"},
        fields=["content"], order_by="sent_at desc", limit=1,
    )
    return ((rows[0].content if rows else "") or "").strip()


def _history(lead_name):
    rows = frappe.get_all(
        "Intel Lead Message",
        filters={"parent": lead_name},
        fields=["direction", "content"],
        order_by="sent_at asc, idx asc",
        limit=_HISTORY,
    )
    lines = []
    for r in rows:
        who = "Cliente" if r.direction == "Inbound" else "Thanatos"
        c = (r.content or "").strip()
        if c and not c.startswith("["):
            lines.append(f"{who}: {c}")
    return "\n".join(lines)


def _wa_doc(wa_number):
    name = wa_number.get("phone_number") if isinstance(wa_number, dict) else wa_number
    if not name:
        return None
    try:
        return frappe.get_doc("WhatsApp Number", name)
    except Exception:
        return None


def send_text(wa_doc, to_number, body, lead_name, sent_by="Administrator"):
    """Invia un testo via Meta e registra il messaggio outbound sul lead."""
    from frappe.utils.password import get_decrypted_password
    pnid = wa_doc.meta_phone_number_id
    token = get_decrypted_password("WhatsApp Number", wa_doc.name, "meta_access_token")
    if not pnid or not token:
        return False
    to_clean = (to_number or "").lstrip("+").replace(" ", "").replace("-", "")
    ok, mid = False, ""
    try:
        import requests
        resp = requests.post(
            f"https://graph.facebook.com/v21.0/{pnid}/messages",
            json={"messaging_product": "whatsapp", "recipient_type": "individual",
                  "to": to_clean, "type": "text",
                  "text": {"preview_url": False, "body": body}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        data = resp.json()
        ok = resp.status_code == 200 and bool(data.get("messages"))
        mid = data["messages"][0].get("id", "") if ok else ""
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa_bot send_text")
    import time as _time
    from thanatos_intel.thanatos_core.doctype.intel_lead.intel_lead import _is_write_conflict
    for _i in range(5):
        try:
            lead = frappe.get_doc("Intel Lead", lead_name)
            lead.append("messages", {
                "direction": "Outbound", "sent_at": now_datetime(),
                "content": body, "status": "Inviato" if ok else "Fallito",
                "sent_by": sent_by, "wa_message_id": mid,
            })
            lead.save(ignore_permissions=True)
            frappe.db.commit()
            break
        except Exception as e:
            frappe.db.rollback()
            if not _is_write_conflict(e) or _i == 4:
                frappe.log_error(frappe.get_traceback(), "wa_bot log msg")
                break
            _time.sleep(0.2 * (_i + 1))
    return ok


def send_image(wa_doc, to_number, image_bytes, caption, lead_name, filename="captcha.png"):
    """Carica un'immagine su Meta (media API) e la invia come messaggio image.
    Usato per mandare all'operatore il captcha OCF da risolvere."""
    from frappe.utils.password import get_decrypted_password
    pnid = wa_doc.meta_phone_number_id
    token = get_decrypted_password("WhatsApp Number", wa_doc.name, "meta_access_token")
    if not pnid or not token:
        return False
    to_clean = (to_number or "").lstrip("+").replace(" ", "").replace("-", "")
    try:
        import requests
        # 1) upload media
        up = requests.post(
            f"https://graph.facebook.com/v21.0/{pnid}/media",
            data={"messaging_product": "whatsapp", "type": "image/png"},
            files={"file": (filename, image_bytes, "image/png")},
            headers={"Authorization": f"Bearer {token}"}, timeout=30)
        media_id = (up.json() or {}).get("id")
        if not media_id:
            frappe.log_error(str(up.text)[:500], "wa send_image upload")
            return False
        # 2) invia messaggio image
        resp = requests.post(
            f"https://graph.facebook.com/v21.0/{pnid}/messages",
            json={"messaging_product": "whatsapp", "recipient_type": "individual",
                  "to": to_clean, "type": "image",
                  "image": {"id": media_id, "caption": caption[:1000]}},
            headers={"Authorization": f"Bearer {token}"}, timeout=20)
        ok = resp.status_code == 200 and bool((resp.json() or {}).get("messages"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa_bot send_image")
        ok = False
    import time as _time
    from thanatos_intel.thanatos_core.doctype.intel_lead.intel_lead import _is_write_conflict
    for _i in range(5):
        try:
            lead = frappe.get_doc("Intel Lead", lead_name)
            lead.append("messages", {"direction": "Outbound", "sent_at": now_datetime(),
                                     "content": f"[immagine] {caption}"[:200],
                                     "status": "Inviato" if ok else "Fallito",
                                     "sent_by": "Administrator"})
            lead.save(ignore_permissions=True)
            frappe.db.commit()
            break
        except Exception as e:
            frappe.db.rollback()
            if not _is_write_conflict(e) or _i == 4:
                break
            _time.sleep(0.2 * (_i + 1))
    return ok


def _handoff(lead_name, wa_doc):
    """Passa la conversazione a un operatore umano: assegna + notifica."""
    assignee = (wa_doc.auto_assign_to or "").strip() or "Administrator"
    try:
        lead = frappe.get_doc("Intel Lead", lead_name)
        if not lead.assigned_to:
            lead.db_set("assigned_to", assignee, notify=False)
        lead.db_set("bot_handed_off", 1, notify=False)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa_bot handoff assign")
    try:
        from thanatos_intel.ingest.intel_notifications import _notify
        _notify(assignee, "Handoff dal Bot AI",
                f"Il bot ha passato la conversazione WhatsApp {lead_name}. Rispondi dal Centralino.",
                lead_name, "orange")
    except Exception:
        pass
    try:
        frappe.publish_realtime("centralino_update",
                                {"lead": lead_name, "type": "handoff"}, after_commit=True)
    except Exception:
        pass


def _resolve_client_user(sender):
    """Se il mittente WA e' un CLIENTE riconosciuto (Investigation Client.phone),
    ritorna il suo platform_user. Match sugli ultimi 9 digit come per operatori."""
    import re
    d = re.sub(r"\D", "", sender or "")
    if len(d) < 8:
        return None
    tail = d[-9:]
    rows = frappe.db.sql(
        """SELECT platform_user, phone FROM `tabInvestigation Client`
           WHERE phone IS NOT NULL AND phone != '' AND platform_user IS NOT NULL""",
        as_dict=True)
    for r in rows:
        if re.sub(r"\D", "", r["phone"] or "").endswith(tail):
            return r["platform_user"]
    return None


def _client_case_for_media(user, lead_name):
    """Ritorna il caso del cliente su cui salvare l'estratto: il linked_case del
    lead, oppure l'UNICO caso visibile del cliente."""
    lc = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
    if lc:
        return lc
    try:
        from thanatos_intel.permissions import visible_case_names
        vc = visible_case_names(user) or []
        if len(vc) == 1:
            return vc[0]
    except Exception:
        pass
    return None


def _try_client_media_explain(lead_name, wa_doc, to_number, user):
    """Se l'ULTIMO messaggio inbound e' un allegato (immagine/doc/video), il
    cliente lo ha appena mandato: chiama ai_explain_document (stessa logica del
    portale). L'estratto va nella cartella Drive '08 Estratti AI' e Case
    Activity per l'operatore. Il cliente riceve la spiegazione via WA."""
    rows = frappe.db.sql(
        """SELECT content, media_url FROM `tabIntel Lead Message`
           WHERE parent=%s AND direction='Inbound'
           ORDER BY sent_at DESC LIMIT 1""",
        lead_name, as_dict=True)
    if not rows:
        return False
    msg = rows[0]
    media_url = msg.get("media_url") or ""
    if not media_url:
        return False
    case = _client_case_for_media(user, lead_name)
    if not case:
        send_text(wa_doc, to_number,
                  "Grazie per il documento. Ho piu' pratiche a Suo nome: "
                  "mi indichi il codice caso (es. CASE-AAAA-N) e Le fornisco la spiegazione.",
                  lead_name)
        return True
    # didascalia = eventuale domanda del cliente
    caption = (msg.get("content") or "").strip()
    if "\n" in caption:
        caption = caption.split("\n", 1)[1].strip()  # rimuove label icona
    question = caption if caption and not caption.startswith("[") else ""
    try:
        from thanatos_intel.api.portal_chat import ai_explain_document
        # esegui come il cliente (scope corretto)
        prev_user = frappe.session.user
        frappe.set_user(user)
        try:
            r = ai_explain_document(case, media_url, question=question)
        finally:
            frappe.set_user(prev_user)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa client media explain")
        return False
    if not r or not r.get("ok"):
        return False
    parts = [r.get("spiegazione", "")]
    if r.get("tipo"):
        parts.append(f"\n_Tipo documento:_ {r['tipo']}")
    if r.get("leggi"):
        parts.append(f"_Riferimenti:_ {', '.join(r['leggi'][:3])}")
    parts.append("\n_Il documento e' stato archiviato nel Suo fascicolo._")
    send_text(wa_doc, to_number, "\n".join(p for p in parts if p), lead_name)
    return True


def _try_operator_ai_reply(lead_name, wa_doc, to_number):
    """Se il sender WA e' un Investigator (operatore MMOS/Thanatos), il brain
    risponde in modalita' operatore: FULL access se super_admin/admin, casi
    assegnati se Investigator. Nessuno scope su un singolo caso, TUTTI i tool.
    Ha PRIORITA' sul branch cliente (un operatore ha sempre pieno controllo)."""
    try:
        from thanatos_intel.ingest.operator_console import find_operator, _operator_user
        from thanatos_intel.ai import ops_brain as ob
    except Exception:
        return False
    op = find_operator(to_number)
    if not op:
        return False
    user = _operator_user(op)  # platform_user dell'Investigator (fallback Administrator)
    if not user:
        return False
    # allegato inviato dall'operatore -> ingest generale (non client-explain scoped)
    last_msg = _last_inbound(lead_name) or ""
    if last_msg.strip().startswith("[") and "media_url" not in last_msg:
        return False
    # Testo: il brain risponde con TUTTI i tool, scope determinato dai ruoli dell'user
    if not last_msg.strip() or last_msg.strip().startswith("["):
        return False
    try:
        reply = ob.answer(last_msg, user=user, operator=op, lead_name=lead_name,
                          session_id=f"wa-op-{op}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa operator ai reply")
        return False
    if not reply or "non disponibile" in reply.lower():
        return False
    send_text(wa_doc, to_number, reply, lead_name)
    return True


def _try_client_ai_reply(lead_name, wa_doc, to_number):
    """Se il mittente e' un cliente riconosciuto: passa al cervello scoped
    (vede solo i suoi casi). Se l'ultimo msg e' un allegato -> ai_explain_document
    (spiega + salva estratto). Altrimenti risposta testuale scoped."""
    user = _resolve_client_user(to_number)
    if not user:
        return False
    # 1) allegato appena mandato -> spiegazione + estratto per operatore
    if _try_client_media_explain(lead_name, wa_doc, to_number, user):
        return True
    # 2) risposta testuale scoped
    try:
        from thanatos_intel.ai import ops_brain as ob
    except Exception:
        return False
    last = _last_inbound(lead_name) or ""
    if not last.strip() or last.strip().startswith("["):
        return False
    try:
        reply = ob.answer(last, user=user, lead_name=lead_name,
                          session_id=f"wa-client-{user}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa client ai reply")
        return False
    if not reply or "non disponibile" in reply.lower():
        return False
    send_text(wa_doc, to_number, reply, lead_name)
    return True


@frappe.whitelist()
def generate_reply(lead_name, wa_number, to_number):
    """Genera e invia la risposta AI per un messaggio entrante (background job).

    - Se il mittente e' un CLIENTE riconosciuto (Investigation Client.phone),
      passa al cervello scoped (vede solo i suoi casi).
    - Altrimenti bot commerciale generico (nuovi lead, accoglienza)."""
    wa_doc = _wa_doc(wa_number)
    if not wa_doc or not int(wa_doc.get("ai_bot_enabled") or 0):
        return {"ok": False, "reason": "bot disabled"}
    # Operatore riconosciuto -> brain in modalita' operatore (priorita' massima)
    if _try_operator_ai_reply(lead_name, wa_doc, to_number):
        return {"ok": True, "mode": "operator_ai"}
    # Cliente riconosciuto -> assistente AI scoped ai suoi casi
    if _try_client_ai_reply(lead_name, wa_doc, to_number):
        return {"ok": True, "mode": "client_scoped_ai"}
    # il bot risponde SEMPRE; bot_handed_off serve solo a NON ri-avvisare l'operatore
    already_ho = int(frappe.db.get_value("Intel Lead", lead_name, "bot_handed_off") or 0)
    from thanatos_intel.ai.doc_ingest import _gateway

    system = (wa_doc.get("ai_bot_system_prompt") or "").strip() or _SYS
    convo = _history(lead_name)
    last = _last_inbound(lead_name)
    want_human = _wants_human(last)

    if want_human and not already_ho:
        clean = ("Certo, avviso subito un nostro operatore che la ricontattera'. "
                 "Intanto sono qui: mi dica pure di cosa ha bisogno e cerco di aiutarla.")
        send_text(wa_doc, to_number, clean, lead_name)
        _handoff(lead_name, wa_doc)
        return {"ok": True, "handoff": True, "reason": "human requested"}

    client_ctx = _client_case_context(lead_name)
    prompt = ((f"{client_ctx}\n\n" if client_ctx else "")
              + f"Storico conversazione:\n{convo}\n\n"
              f"Ultimo messaggio del cliente: «{last}»\n\n"
              "Scrivi ORA, in prima persona, il messaggio WhatsApp da inviare al "
              "cliente in risposta. Solo il messaggio, nient'altro.")
    resp = _gateway(prompt, system=system, task_type="chat", session_id=f"wa2-{lead_name}")

    from thanatos_intel.workflow.ai_concierge import _resp_text
    text = _resp_text(resp) or ""
    if not text:
        from thanatos_intel.ingest.whatsapp import _send_auto_reply
        _send_auto_reply({"phone_number": wa_doc.name}, to_number, lead_name, is_new=True)
        return {"ok": False, "reason": "gateway down, fallback sent"}

    handoff = _HANDOFF_MARK in text
    clean = text.replace(_HANDOFF_MARK, "").strip()

    # guardia: il modello a volte "narra" invece di rispondere → non inviarlo al cliente
    if not clean or _is_meta(clean):
        clean = ("Mi scusi, può darmi qualche dettaglio in più così la indirizzo "
                 "all'operatore giusto? Se preferisce, la metto subito in contatto "
                 "con un nostro operatore.")
        handoff = True

    if clean:
        send_text(wa_doc, to_number, clean, lead_name)

    try:
        usage = (resp or {}).get("usage") or {}
        if usage.get("tokens_in") or usage.get("tokens_out"):
            from thanatos_intel.billing.ai_meter import record_usage
            record_usage(client=None, model=(resp or {}).get("model", "default"),
                         tokens_in=usage.get("tokens_in", 0),
                         tokens_out=usage.get("tokens_out", 0), reference=lead_name)
    except Exception:
        pass

    if handoff and not already_ho:
        _handoff(lead_name, wa_doc)
    return {"ok": True, "handoff": handoff}


def trigger_for_lead(lead_name, wa_phone):
    """Fa rispondere il bot all'ultimo messaggio del lead, se il numero ha il bot
    attivo. Usato dopo trascrizione vocale o ricezione di un media."""
    if not wa_phone:
        return
    if not int(frappe.db.get_value("WhatsApp Number", wa_phone, "ai_bot_enabled") or 0):
        return
    to_number = frappe.db.get_value("Intel Lead", lead_name, "source_identifier")
    if not to_number:
        return
    try:
        generate_reply(lead_name, wa_phone, to_number)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa_bot trigger_for_lead")
