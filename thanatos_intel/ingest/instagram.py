"""Ingest messaggi diretti Instagram -> Intel Lead.

Gemello di ``whatsapp.py`` per il canale Instagram (webhook Meta, oggetto
``instagram``). Multi-account tramite DocType ``Instagram Account``.

Webhook URL da impostare su developers.facebook.com:
  https://thanatos.agency/api/method/thanatos_intel.ingest.instagram.webhook
  ?token=IL-TUO-TOKEN

Il token e' il campo ``webhook_token`` di un Instagram Account attivo, con
fallback ``instagram_ingest_token`` in site_config. Vale sia per la challenge
GET ``hub.verify_token`` sia per il ``?token=`` nel POST.
"""
import frappe
from frappe.utils.password import get_decrypted_password

GRAPH = "https://graph.facebook.com/v21.0"

_ACCOUNT_FIELDS = [
    "name", "username", "display_name", "ig_user_id", "page_id",
    "auto_assign_to", "default_priority", "default_tags",
    "ai_bot_enabled", "ai_bot_system_prompt", "auto_reply_message", "is_active",
]


def account_token(account: str) -> str:
    try:
        return get_decrypted_password("Instagram Account", account, "access_token") or ""
    except Exception:
        return ""


def _load_account(ig_user_id: str) -> dict | None:
    if not ig_user_id:
        return None
    return frappe.db.get_value(
        "Instagram Account", {"ig_user_id": ig_user_id, "is_active": 1},
        _ACCOUNT_FIELDS, as_dict=True) or None


def _check_token(token: str) -> bool:
    """Valida contro il token globale o il webhook_token di un account attivo."""
    if not token:
        return False
    g = frappe.conf.get("instagram_ingest_token")
    if g and token == g:
        return True
    try:
        names = frappe.get_all("Instagram Account", filters={"is_active": 1}, pluck="name")
    except Exception:
        return False
    for n in names:
        try:
            if get_decrypted_password("Instagram Account", n, "webhook_token") == token:
                return True
        except Exception:
            continue
    return False


def _extract_content(msg: dict) -> str:
    """Testo leggibile da un messaggio IG. Mai vuoto se c'e' un allegato."""
    txt = (msg.get("text") or "").strip()
    if txt:
        return txt
    atts = msg.get("attachments") or []
    if atts:
        kinds = []
        for a in atts:
            t = a.get("type") or "media"
            kinds.append({
                "image": "immagine", "video": "video", "audio": "audio",
                "file": "documento", "share": "post condiviso",
                "story_mention": "menzione nella storia",
                "ig_reel": "reel",
            }.get(t, t))
        return "[" + ", ".join(kinds) + "]"
    return "[messaggio]"


def _parse(data: dict) -> list[dict]:
    """Normalizza il payload webhook IG in una lista di eventi piatti."""
    out = []
    for entry in data.get("entry", []):
        ig_user_id = str(entry.get("id") or "")
        for ev in (entry.get("messaging") or []):
            sender = str((ev.get("sender") or {}).get("id") or "")
            recipient = str((ev.get("recipient") or {}).get("id") or "")
            if not sender:
                continue
            msg = ev.get("message") or {}
            # echo = messaggio inviato da NOI e rimbalzato dal webhook: gia' loggato
            if msg.get("is_echo"):
                continue
            # il mittente non puo' essere l'account stesso
            if sender == ig_user_id:
                continue

            pb = ev.get("postback") or {}
            reac = ev.get("reaction") or {}
            if msg:
                content = _extract_content(msg)
                mid = msg.get("mid", "")
                atts = msg.get("attachments") or []
            elif pb:
                content = pb.get("title") or pb.get("payload") or "[pulsante]"
                mid = pb.get("mid", "")
                atts = []
            elif reac:
                if reac.get("action") == "unreact":
                    continue
                content = f"[reazione {reac.get('emoji', '')}]".strip()
                mid = reac.get("mid", "")
                atts = []
            else:
                # read receipts, delivery, ecc: non generano lead
                continue

            out.append({
                "ig_user_id": ig_user_id or recipient,
                "source_id": sender,
                "content": content,
                "attachments": atts,
                "mid": mid,
            })
    return out


def _profile_name(igsid: str, token: str) -> str:
    """Username del mittente. Best-effort: l'API puo' negarlo senza consenso."""
    if not (igsid and token):
        return ""
    try:
        import requests
        r = requests.get(f"{GRAPH}/{igsid}",
                         params={"fields": "username,name", "access_token": token},
                         timeout=10)
        if r.status_code == 200:
            d = r.json()
            u = d.get("username")
            return f"@{u}" if u else (d.get("name") or "")
    except Exception:
        pass
    return ""



def _debug_dump(tag: str, content: str) -> None:
    """Dump diagnostico su file: il webhook puo' fallire PRIMA di poter scrivere
    su DocType, quindi il file e' l'unico posto sempre raggiungibile.
    Attivo solo con ``instagram_debug_payload`` in site_config."""
    if not frappe.conf.get("instagram_debug_payload"):
        return
    try:
        from frappe.utils import now
        with open("/tmp/ig_webhook_debug.log", "a") as f:
            f.write(f"\n===== {tag} {now()} =====\n{content}\n")
    except Exception:
        pass


def _log_raw(data: dict) -> None:
    """Payload grezzo in WABA Webhook Log (riusa lo stesso registro di WA)."""
    if not frappe.conf.get("instagram_webhook_log", 1):
        return
    try:
        if not frappe.db.exists("DocType", "WABA Webhook Log"):
            return
        frappe.get_doc({
            "doctype": "WABA Webhook Log",
            "payload": "[instagram] " + frappe.as_json(data)[:100000],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass


def _create_lead(acc: dict, ev: dict, source_name: str) -> str:
    from thanatos_intel.thanatos_core.doctype.intel_lead.intel_lead import find_or_create_lead
    atts = ev.get("attachments") or []
    media_url = ((atts[0].get("payload") or {}).get("url", "") if atts else "")
    # find_or_create_lead accetta un dict di default di canale (nato per WhatsApp):
    # senza "phone_number" il campo whatsapp_number resta vuoto, come deve essere.
    cfg = {
        "default_priority": acc.get("default_priority"),
        "default_tags": acc.get("default_tags"),
        "auto_assign_to": acc.get("auto_assign_to"),
    }
    return find_or_create_lead(
        source_identifier=ev["source_id"],
        source_name=source_name,
        content=ev["content"],
        source_type="Instagram",
        media_url=media_url,
        wa_number=cfg,
        wa_message_id=ev.get("mid", ""),
    )


@frappe.whitelist(allow_guest=True)
def webhook():
    """Endpoint webhook Instagram multi-account."""
    req = frappe.request
    args = req.args

    if req.method == "GET":
        from werkzeug.wrappers import Response
        challenge = args.get("hub.challenge")
        verify = args.get("hub.verify_token", "")
        if _check_token(verify) and challenge:
            return Response(challenge, status=200, content_type="text/plain")
        return Response("invalid verify_token", status=403, content_type="text/plain")

    if not _check_token((args.get("token") or "").strip()):
        frappe.response["http_status_code"] = 403
        return {"error": "unauthorized"}

    _debug_dump("RAW BODY", (req.get_data(as_text=True) or "")[:8000])

    data = req.json or {}
    _log_raw(data)

    try:
        return _process(data)
    except Exception:
        # senza questo il traceback si perde: Frappe rispondeva 417 muto
        _debug_dump("TRACEBACK", frappe.get_traceback())
        frappe.log_error(frappe.get_traceback(), "IG webhook")
        raise


def _process(data: dict) -> dict:
    created = []
    for ev in _parse(data):
        acc = _load_account(ev["ig_user_id"])
        if not acc:
            continue

        # dedup: Meta consegna at-least-once e ritenta lo stesso mid
        mid = (ev.get("mid") or "").strip()
        seen = f"ig_seen:{mid}" if mid else None
        if seen:
            if frappe.cache().get_value(seen):
                continue
            frappe.cache().set_value(seen, "1", expires_in_sec=900)

        token = account_token(acc.name)
        source_name = _profile_name(ev["source_id"], token)

        try:
            name = _create_lead(acc, ev, source_name)
        except Exception:
            # lead non salvato: NON marcare il mid come visto, cosi' il retry lo riprocessa
            if seen:
                frappe.cache().delete_value(seen)
            raise
        created.append(name)

        if not frappe.db.get_value("Intel Lead", name, "instagram_account"):
            frappe.db.set_value("Intel Lead", name, "instagram_account", acc.name,
                                update_modified=False)
            frappe.db.commit()

        # Notifica push agli operatori (PWA Switchboard): best-effort
        try:
            from thanatos_intel.api.push import on_new_inbound_message
            on_new_inbound_message(name, source_name or ev["source_id"], ev["content"])
        except Exception:
            frappe.log_error(frappe.get_traceback(), "IG push notify")

        # Allegati -> scarica e allega al lead
        for a in (ev.get("attachments") or []):
            url = (a.get("payload") or {}).get("url", "")
            if url:
                frappe.enqueue(
                    "thanatos_intel.ingest.instagram.process_attachment",
                    queue="long", timeout=600,
                    lead_name=name, url=url, kind=a.get("type") or "file")

        _auto_reply(acc, name, ev["source_id"], ev["content"])

    return {"created": created, "count": len(created)}


def _auto_reply(acc: dict, lead_name: str, to_id: str, content: str) -> None:
    """Bot AI se abilitato, altrimenti messaggio fisso (guardia 4h)."""
    try:
        from frappe.utils import add_to_date, now_datetime
        from thanatos_intel.ingest.instagram_send import send_dm

        txt = (content or "").strip()
        if acc.get("ai_bot_enabled") and txt and not txt.startswith("["):
            frappe.enqueue("thanatos_intel.ingest.instagram.generate_bot_reply",
                           queue="short", timeout=200,
                           lead_name=lead_name, account=acc.name, to_id=to_id)
            return

        msg = (acc.get("auto_reply_message") or "").strip()
        if not msg:
            return
        cutoff = add_to_date(now_datetime(), hours=-4)
        recent = frappe.db.count("Intel Lead Message", {
            "parent": lead_name, "direction": "Outbound", "sent_at": [">=", cutoff]})
        if not recent:
            send_dm(acc.name, to_id, msg, lead_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "IG auto-reply")


_SYS = (
    "Sei l'assistente di Thanatos Investigazioni, agenzia investigativa. "
    "Rispondi su Instagram in italiano, tono professionale e cordiale, messaggi BREVI. "
    "Fai triage: capisci di che problema si tratta e quale servizio serve, "
    "raccogli i dati essenziali. Non promettere risultati né dare consulenza legale. "
    "Se l'utente chiede di parlare con una persona, o il caso è delicato, "
    "rispondi che avvisi subito un operatore. "
    "Scrivi SOLO il messaggio da inviare, senza meta-commenti."
)


def generate_bot_reply(lead_name: str, account: str, to_id: str) -> dict:
    """Bot di triage su Instagram (gateway MMOS AI, non-privilegiato)."""
    from thanatos_intel.ingest.instagram_send import send_dm

    last = frappe.db.get_value(
        "Intel Lead Message", {"parent": lead_name, "direction": "Inbound"},
        "content", order_by="sent_at desc") or ""
    if not last.strip() or last.strip().startswith("["):
        return {"ok": False, "reason": "nessun testo"}

    acc = frappe.db.get_value("Instagram Account", account,
                              ["ai_bot_system_prompt"], as_dict=True) or {}

    rows = frappe.get_all(
        "Intel Lead Message", filters={"parent": lead_name},
        fields=["direction", "content"], order_by="sent_at desc", limit=8)
    convo = "\n".join(
        f"{'Cliente' if r.direction == 'Inbound' else 'Noi'}: {r.content}"
        for r in reversed(rows))

    try:
        from thanatos_intel.ai.doc_ingest import _gateway
        from thanatos_intel.workflow.ai_concierge import _resp_text
    except Exception:
        return {"ok": False, "reason": "gateway non disponibile"}

    prompt = (f"Storico conversazione:\n{convo}\n\n"
              f"Ultimo messaggio del cliente: «{last}»\n\n"
              "Scrivi ORA, in prima persona, il messaggio Instagram da inviare "
              "in risposta. Solo il messaggio, nient'altro.")
    resp = _gateway(prompt, system=(acc.get("ai_bot_system_prompt") or "").strip() or _SYS,
                    task_type="chat", session_id=f"ig-{lead_name}")
    text = (_resp_text(resp) or "").strip()
    if not text:
        return {"ok": False, "reason": "gateway muto"}

    send_dm(account, to_id, text, lead_name)
    return {"ok": True}


def process_attachment(lead_name: str, url: str, kind: str = "file") -> None:
    """Scarica l'allegato IG (URL CDN a scadenza) e lo allega al lead."""
    import os
    from urllib.parse import urlparse
    try:
        import requests
        r = requests.get(url, timeout=90)
        if r.status_code != 200 or not r.content:
            return
        base = os.path.basename(urlparse(url).path) or f"ig_{kind}"
        if "." not in base:
            base += {"image": ".jpg", "video": ".mp4",
                     "audio": ".m4a"}.get(kind, ".bin")
        frappe.get_doc({
            "doctype": "File",
            "file_name": f"{frappe.generate_hash(length=6)}_{base}",
            "attached_to_doctype": "Intel Lead",
            "attached_to_name": lead_name,
            "content": r.content,
            "is_private": 1,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "IG attachment")
