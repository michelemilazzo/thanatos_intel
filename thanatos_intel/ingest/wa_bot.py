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
    "mai password, credenziali, OTP o dati di pagamento; non rivelare nomi di "
    "investigatori ne' dettagli operativi interni. "
    "Se il cliente chiede di parlare con una persona/operatore/umano o di essere "
    "richiamato, oppure se la richiesta e' concreta/urgente o riguarda un preventivo o "
    "un caso aperto: rispondi con UNA frase breve di presa in carico e aggiungi su una "
    "riga a parte il marcatore [[HANDOFF]] (l'utente non lo vedra'). "
    "Risposte brevi: massimo 60-70 parole."
)

_HANDOFF_MARK = "[[HANDOFF]]"
_HISTORY = 12

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
    try:
        lead = frappe.get_doc("Intel Lead", lead_name)
        lead.append("messages", {
            "direction": "Outbound", "sent_at": now_datetime(),
            "content": body, "status": "Inviato" if ok else "Fallito",
            "sent_by": sent_by, "wa_message_id": mid,
        })
        lead.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa_bot log msg")
    return ok


def _handoff(lead_name, wa_doc):
    """Passa la conversazione a un operatore umano: assegna + notifica."""
    assignee = (wa_doc.auto_assign_to or "").strip() or "Administrator"
    try:
        lead = frappe.get_doc("Intel Lead", lead_name)
        if not lead.assigned_to:
            lead.db_set("assigned_to", assignee, notify=False)
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


@frappe.whitelist()
def generate_reply(lead_name, wa_number, to_number):
    """Genera e invia la risposta del bot AI per un messaggio entrante.
    Pensato per girare in background (frappe.enqueue)."""
    wa_doc = _wa_doc(wa_number)
    if not wa_doc or not int(wa_doc.get("ai_bot_enabled") or 0):
        return {"ok": False, "reason": "bot disabled"}
    from thanatos_intel.ai.doc_ingest import _gateway

    system = (wa_doc.get("ai_bot_system_prompt") or "").strip() or _SYS
    convo = _history(lead_name)
    last = _last_inbound(lead_name)
    want_human = _wants_human(last)

    if want_human:
        clean = ("Certo, la metto subito in contatto con un nostro operatore. "
                 "Resti pure su WhatsApp, la ricontattiamo a breve.")
        send_text(wa_doc, to_number, clean, lead_name)
        _handoff(lead_name, wa_doc)
        return {"ok": True, "handoff": True, "reason": "human requested"}

    prompt = (f"Storico conversazione:\n{convo}\n\n"
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

    if handoff:
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
