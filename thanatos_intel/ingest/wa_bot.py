"""Bot AI conversazionale su WhatsApp (triage + handoff).

Quando un WhatsApp Number ha ai_bot_enabled=1, le risposte automatiche sono
generate dal gateway MMOS AI invece del messaggio fisso. Il bot fa accoglienza
e triage (info servizi, qualifica della richiesta) e quando serve un umano
passa la mano notificando l'operatore assegnato.
"""
import frappe
from frappe.utils import now_datetime

_SYS = (
    "Sei l'assistente virtuale di Thanatos Investigazioni, agenzia di "
    "investigazioni e intelligence (sede in Romania, Legea 329/2003, conforme GDPR). "
    "Parli italiano, tono professionale, riservato, empatico ma sobrio. "
    "Compiti: 1) accogliere il cliente; 2) spiegare a grandi linee i servizi "
    "(investigazioni private, due diligence, OSINT, rintracci, tutela aziendale, "
    "infedelta', recupero informazioni); 3) capire di cosa ha bisogno e con quale "
    "urgenza facendo UNA domanda mirata per volta. "
    "REGOLE FERREE: non promettere risultati ne' dare consulenza legale; non "
    "chiedere mai password, credenziali, OTP o dati di pagamento; non rivelare "
    "nomi di investigatori ne' dettagli operativi interni; massima riservatezza. "
    "Se la richiesta e' concreta o urgente, delicata, riguarda un preventivo, un "
    "incarico o un caso gia' aperto, oppure se il cliente chiede di parlare con "
    "una persona, passa la mano a un operatore umano: in quel caso termina il "
    "messaggio con il marcatore [[HANDOFF]] su una riga a parte (l'utente non lo "
    "vedra'). Risposte brevi: massimo 60-70 parole."
)

_HANDOFF_MARK = "[[HANDOFF]]"
_HISTORY = 12


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
    prompt = (f"Conversazione finora:\n{convo}\n\n"
              "Rispondi come Thanatos al cliente, seguendo le tue regole.")
    resp = _gateway(prompt, system=system, task_type="chat", session_id=f"wa-{lead_name}")

    from thanatos_intel.workflow.ai_concierge import _resp_text
    text = _resp_text(resp)
    if not text:
        from thanatos_intel.ingest.whatsapp import _send_auto_reply
        _send_auto_reply({"phone_number": wa_doc.name}, to_number, lead_name, is_new=True)
        return {"ok": False, "reason": "gateway down, fallback sent"}

    handoff = _HANDOFF_MARK in text
    clean = text.replace(_HANDOFF_MARK, "").strip()
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
