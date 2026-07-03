import frappe
from frappe import _
from frappe.utils import now_datetime


# ─── Conversations ────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_conversations(filter_type="all", search=""):
    user = frappe.session.user
    conditions = ["l.docstatus < 2", "l.status != 'Archiviato'"]
    values = {}

    if filter_type == "mine":
        conditions.append("l.assigned_to = %(user)s")
        values["user"] = user
    elif filter_type == "unassigned":
        conditions.append("(l.assigned_to IS NULL OR l.assigned_to = '')")

    if search:
        conditions.append(
            "(l.source_name LIKE %(search)s OR l.source_identifier LIKE %(search)s)"
        )
        values["search"] = f"%{search}%"

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            l.name, l.source_name, l.source_identifier, l.source_type,
            l.status, l.priority, l.assigned_to, l.last_message_at, l.creation,
            l.linked_case, l.linked_contact, l.whatsapp_number,
            (SELECT COUNT(*) FROM `tabIntel Lead Message` m
             WHERE m.parent = l.name AND m.direction = 'Inbound') AS msg_count,
            (SELECT COUNT(*) FROM `tabIntel Lead Message` m
             WHERE m.parent = l.name AND m.direction = 'Inbound'
               AND (l.operator_last_read IS NULL
                    OR m.sent_at > l.operator_last_read)) AS unread_count
        FROM `tabIntel Lead` l
        WHERE {where}
        ORDER BY COALESCE(l.last_message_at, l.creation) DESC
        LIMIT 150
        """,
        values,
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def mark_read(lead_name):
    """Segna la conversazione come letta dall'operatore (aggiorna operator_last_read).
    Emette centralino_update per aggiornare il badge negli altri client aperti."""
    frappe.db.set_value("Intel Lead", lead_name, "operator_last_read",
                        now_datetime(), update_modified=False)
    frappe.db.commit()
    try:
        frappe.publish_realtime("centralino_update",
                                {"lead": lead_name, "type": "read"}, after_commit=True)
    except Exception:
        pass
    return {"ok": True}


@frappe.whitelist()
def set_typing(lead_name, is_typing=1):
    """Broadcast 'sta scrivendo' per un thread. Usato sia dagli operatori (PWA)
    sia dai clienti (portale). L'evento centralino_typing porta chi scrive."""
    who = "operator"
    if frappe.session.user != "Guest":
        roles = set(frappe.get_roles(frappe.session.user) or [])
        if not (roles & {"System Manager", "Investigation Manager", "Investigator"}):
            who = "client"
    try:
        frappe.publish_realtime(
            "centralino_typing",
            {"lead": lead_name, "typing": int(is_typing), "who": who,
             "name": frappe.db.get_value("User", frappe.session.user, "full_name") or ""},
        )
    except Exception:
        pass
    return {"ok": True}


@frappe.whitelist()
def get_thread(lead_name):
    doc = frappe.get_doc("Intel Lead", lead_name)
    messages = []
    for m in sorted(doc.messages or [], key=lambda x: x.sent_at or ""):
        messages.append({
            "name": m.name,
            "direction": m.direction,
            "content": m.content,
            "sent_at": str(m.sent_at or ""),
            "status": m.status,
            "sent_by": m.sent_by,
            "media_url": m.media_url,
            "wa_message_id": getattr(m, "wa_message_id", ""),
        })
    return {
        "name": doc.name,
        "source_name": doc.source_name,
        "source_identifier": doc.source_identifier,
        "source_type": doc.source_type,
        "status": doc.status,
        "priority": doc.priority,
        "assigned_to": doc.assigned_to,
        "linked_case": doc.linked_case,
        "linked_contact": doc.linked_contact,
        "whatsapp_number": doc.whatsapp_number,
        "messages": messages,
    }


@frappe.whitelist()
def send_reply(lead_name, message_text):
    from thanatos_intel.ingest.whatsapp_send import send_reply as _send
    return _send(lead_name, message_text)


@frappe.whitelist()
def close_lead(lead_name):
    frappe.db.set_value("Intel Lead", lead_name, "status", "Chiuso")
    frappe.db.commit()
    _emit(lead_name, "closed")
    return {"ok": True}


@frappe.whitelist()
def reopen_lead(lead_name):
    frappe.db.set_value("Intel Lead", lead_name, "status", "Aperto")
    frappe.db.commit()
    _emit(lead_name, "reopened")
    return {"ok": True}


@frappe.whitelist()
def assign_lead(lead_name, to_user):
    frappe.db.set_value("Intel Lead", lead_name, "assigned_to", to_user)
    frappe.db.commit()
    _emit(lead_name, "assigned")
    return {"ok": True}


# ─── Operator status ──────────────────────────────────────────────────────────

@frappe.whitelist()
def set_operator_status(status):
    if status not in ("online", "busy", "offline"):
        frappe.throw(_("Stato non valido"))
    frappe.cache.hset("centralino_op_status", frappe.session.user, status)
    frappe.publish_realtime(
        "centralino_op_status",
        {"user": frappe.session.user, "status": status},
    )
    return {"ok": True}


@frappe.whitelist()
def get_operator_statuses():
    raw = frappe.cache.hgetall("centralino_op_status") or {}
    # hgetall returns bytes keys/values in some redis versions
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }


# ─── Users list for assign dialog ────────────────────────────────────────────

@frappe.whitelist()
def get_operators():
    roles = ("Investigator", "Investigation Manager", "System Manager")
    users = frappe.db.sql(
        """
        SELECT DISTINCT u.name, u.full_name, u.user_image
        FROM `tabUser` u
        JOIN `tabHas Role` r ON r.parent = u.name
        WHERE r.role IN %(roles)s AND u.enabled = 1 AND u.name != 'Guest'
        ORDER BY u.full_name
        """,
        {"roles": roles},
        as_dict=True,
    )
    return users


# ─── Helper ───────────────────────────────────────────────────────────────────

def _emit(lead_name, event_type, extra=None):
    payload = {"lead": lead_name, "type": event_type}
    if extra:
        payload.update(extra)
    frappe.publish_realtime("centralino_update", payload, after_commit=True)


@frappe.whitelist()
def get_call_logs(search=""):
    """Storico chiamate WhatsApp registrate (per la scheda Chiamate del Centralino)."""
    rows = frappe.get_all(
        "Call Log",
        fields=["name", "called_at", "caller_name", "caller_number", "outcome",
                "duration_seconds", "duration_minutes", "audio_file",
                "transcription_status", "linked_case", "handled_by"],
        order_by="called_at desc", limit=80)
    s = (search or "").strip().lower()
    if s:
        rows = [r for r in rows if s in (r.get("caller_name") or "").lower()
                or s in (r.get("caller_number") or "")]
    return rows


@frappe.whitelist()
def stream_call_audio(call_log):
    """Serve la registrazione audio (file fisico) in streaming, con check permessi
    sul Call Log. Evita il mismatch File-doc/audio_file."""
    import os
    from werkzeug.wrappers import Response
    cl = frappe.get_doc("Call Log", call_log)  # solleva PermissionError se non autorizzato
    url = (cl.audio_file or "").strip()
    if not url:
        frappe.throw("Nessuna registrazione audio per questa chiamata.")
    fname = url.split("/")[-1]
    path = frappe.get_site_path("private", "files", fname)
    if not os.path.exists(path):
        frappe.throw("File audio non trovato.")
    with open(path, "rb") as f:
        content = f.read()
    return Response(content, mimetype="audio/ogg",
                    headers={"Content-Disposition": 'inline; filename="%s.ogg"' % call_log,
                             "Accept-Ranges": "bytes"})


@frappe.whitelist()
def call_transcript_md(call_log):
    """Esporta la trascrizione della chiamata come file Markdown (.md)."""
    import json
    from werkzeug.wrappers import Response
    cl = frappe.get_doc("Call Log", call_log)  # check permessi
    try:
        segs = json.loads(cl.transcript_raw or "[]")
    except Exception:
        segs = []
    L = ["# Chiamata %s" % cl.name, ""]
    L.append("- **Da:** %s (%s)" % (cl.caller_name or "", cl.caller_number or ""))
    L.append("- **Data:** %s" % (cl.called_at or ""))
    L.append("- **Durata:** %sm %ss" % (cl.duration_minutes or 0, cl.duration_seconds or 0))
    L.append("- **Esito:** %s" % (cl.outcome or ""))
    if cl.get("linked_case"):
        L.append("- **Caso:** %s" % cl.linked_case)
    L += ["", "## Trascrizione", ""]
    if segs:
        for s in segs:
            t = int((s.get("start_ms") or 0) / 1000)
            ts = "%02d:%02d" % (t // 60, t % 60)
            spk = s.get("speaker_label") or s.get("speaker") or "?"
            L.append("**%s** [%s] %s" % (spk, ts, s.get("text", "")))
    elif (cl.transcript_text or "").strip():
        L.append(cl.transcript_text)
    else:
        L.append("_(trascrizione non disponibile)_")
    md = "\n".join(L)
    return Response(md, mimetype="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="%s.md"' % call_log})



@frappe.whitelist()
def promote_to_case(lead_name):
    """Promuovi un Intel Lead a Investigation Case usando il flusso operatore
    (analizza allegati, crea case, collega). Enqueue: risponde subito, il job
    parte in background e emette centralino_update quando finisce."""
    user = frappe.session.user
    inv = frappe.db.get_value("Investigator", {"platform_user": user}, "name")
    lead = frappe.get_doc("Intel Lead", lead_name)
    if lead.linked_case:
        return {"ok": True, "already": lead.linked_case}
    frappe.enqueue(
        "thanatos_intel.ingest.operator_console.run_open_case",
        queue="long", timeout=1200,
        lead_name=lead_name,
        wa_phone=lead.whatsapp_number,
        sender=lead.source_identifier,
        operator=inv,
    )
    return {"ok": True, "enqueued": True}


@frappe.whitelist()
def get_cases(filter_type="mine", search=""):
    """Lista casi visibili all'operatore corrente. filter_type: mine|all|open|closed."""
    user = frappe.session.user
    conditions = []
    values = {}
    if filter_type == "mine":
        # casi in cui l'utente è nel team (via Case Assignment: assignee_email
        # o assignee=Investigator collegato al platform_user)
        conditions.append(
            "EXISTS (SELECT 1 FROM `tabCase Assignment` a "
            "WHERE a.parent = c.name AND ("
            "  a.assignee_email = %(user)s "
            "  OR a.assignee IN (SELECT name FROM `tabInvestigator` "
            "                    WHERE platform_user = %(user)s)))"
        )
        values["user"] = user
    elif filter_type == "open":
        conditions.append("c.status = 'Open'")
    elif filter_type == "closed":
        conditions.append("c.status IN ('Closed','Archived')")
    if search:
        conditions.append("(c.name LIKE %(s)s OR c.case_title LIKE %(s)s)")
        values["s"] = f"%{search}%"
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = frappe.db.sql(
        f"""
        SELECT c.name, c.case_title, c.case_type, c.status, c.priority,
               c.client, c.modified, c.opening_date, c.risk_score_final,
               (SELECT COUNT(*) FROM `tabInvestigation Evidence` e
                WHERE e.investigation_case = c.name) as n_evidence,
               (SELECT client_name FROM `tabInvestigation Client`
                WHERE name = c.client) as client_name
        FROM `tabInvestigation Case` c
        {where}
        ORDER BY c.modified DESC LIMIT 100
        """,
        values, as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_case_detail(case_name):
    """Dettaglio caso per la Switchboard: header + reperti + attività + team."""
    c = frappe.get_doc("Investigation Case", case_name)
    client_name = None
    if c.client:
        client_name = frappe.db.get_value("Investigation Client", c.client, "client_name")
    evidences = frappe.get_all(
        "Investigation Evidence",
        filters={"investigation_case": case_name},
        fields=["name", "evidence_name", "attached_file", "notes",
                "authenticity", "creation"],
        order_by="creation desc", limit=50,
    )
    activities = frappe.get_all(
        "Case Activity",
        filters={"parent": case_name},
        fields=["activity_date", "activity_type", "description"],
        order_by="activity_date desc", limit=30,
    )
    team = []
    for a in (c.get("case_assignments") or []):
        team.append({"user": a.assigned_to,
                     "role": a.role_in_case if hasattr(a, "role_in_case") else None})
    linked_leads = frappe.get_all(
        "Intel Lead", filters={"linked_case": case_name},
        fields=["name", "source_name", "source_identifier",
                "source_type", "last_message_at"], limit=10,
    )
    return {
        "name": c.name,
        "case_title": c.case_title,
        "case_type": c.case_type,
        "status": c.status,
        "priority": c.priority,
        "client": c.client,
        "client_name": client_name,
        "summary": c.summary,
        "opening_date": str(c.opening_date or ""),
        "closing_date": str(c.closing_date or ""),
        "risk_score_final": c.risk_score_final,
        "final_verdict": c.final_verdict,
        "team": team,
        "evidences": evidences,
        "activities": activities,
        "linked_leads": linked_leads,
    }


def _operator_lead(user):
    """Trova il Intel Lead con source_identifier = numero WhatsApp dell'operatore
    (Investigator.phone). Se non esiste, ritorna None (non lo creiamo qui: viene
    creato automaticamente dal webhook quando l'operatore scrive al numero
    Thanatos)."""
    import re
    phone = frappe.db.get_value("Investigator", {"platform_user": user}, "phone")
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return None
    tail = digits[-9:]
    lead = frappe.db.sql(
        """
        SELECT name FROM `tabIntel Lead`
        WHERE source_type = 'WhatsApp' AND source_identifier LIKE %s
        ORDER BY last_message_at DESC LIMIT 1
        """,
        f"%{tail}",
    )
    return lead[0][0] if lead else None


@frappe.whitelist()
def get_ingest_thread():
    """Ritorna il thread ingest dell'operatore corrente (i suoi messaggi WA con
    documenti/note): fungerà da cassetta di smistamento nella PWA."""
    user = frappe.session.user
    lead_name = _operator_lead(user)
    if not lead_name:
        return {"empty": True,
                "hint": "Non ho trovato la tua cassetta ingest. "
                        "Manda un messaggio o un documento al numero WhatsApp "
                        "Thanatos dal tuo cellulare per crearla."}
    return get_thread(lead_name)


@frappe.whitelist()
def attach_lead_message_to_case(message_name, case_name):
    """Sposta un allegato di un Intel Lead Message dentro un Investigation Case
    (come Investigation Evidence). Se il messaggio non ha allegato ma solo testo,
    salva il testo come Case Activity note."""
    msg = frappe.get_doc("Intel Lead Message",
                         {"name": message_name}) if not isinstance(
        message_name, dict) else None
    if not msg:
        # child docs vengono cercati globalmente per name
        parents = frappe.db.sql(
            "SELECT parent FROM `tabIntel Lead Message` WHERE name=%s",
            message_name, as_dict=True)
        if not parents:
            frappe.throw("Messaggio non trovato")
        lead = frappe.get_doc("Intel Lead", parents[0].parent)
        msg = next((m for m in lead.messages if m.name == message_name), None)
        if not msg:
            frappe.throw("Messaggio non trovato nel lead")
    frappe.get_doc("Investigation Case", case_name)  # existence + perm
    from thanatos_intel.ai.doc_ingest import ingest_document
    # Se c'è un file allegato, ingest come evidence
    if msg.media_url:
        r = ingest_document(file_url=msg.media_url,
                            investigation_case=case_name,
                            document_type="generic") or {}
        return {"ok": True, "as": "evidence", "result": r}
    # Altrimenti, aggiungi come Case Activity
    c = frappe.get_doc("Investigation Case", case_name)
    c.append("case_activities", {
        "activity_date": now_datetime(),
        "activity_type": "Note",
        "description": f"Da ingest ({msg.sent_at}):\n{msg.content or ''}",
    })
    c.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "as": "activity"}


@frappe.whitelist()
def send_media(lead_name, file_url, caption=""):
    """Invia un file al cliente WhatsApp via Meta Cloud API.
    Determina automaticamente il tipo (image/audio/video/document) dal MIME."""
    import os
    import mimetypes
    import requests
    from frappe.utils.password import get_decrypted_password

    lead = frappe.get_doc("Intel Lead", lead_name)
    if lead.source_type != "WhatsApp":
        frappe.throw(_("Il lead non è di tipo WhatsApp."))
    wa_name = lead.whatsapp_number
    if not wa_name:
        frappe.throw(_("Numero WhatsApp non configurato per questo lead."))
    wa = frappe.get_doc("WhatsApp Number", wa_name)
    pnid = wa.meta_phone_number_id
    token = get_decrypted_password("WhatsApp Number", wa.name, "meta_access_token")
    if not (pnid and token):
        frappe.throw(_("Meta phone_number_id o access_token mancanti."))
    to_number = (lead.source_identifier or "").lstrip("+").replace(" ", "").replace("-", "")

    rel = (file_url or "").split("/files/", 1)[-1]
    fpath = frappe.get_site_path(
        "private" if "/private/" in file_url else "public", "files", rel)
    if not os.path.exists(fpath):
        frappe.throw(_("File non trovato sul server: {0}").format(file_url))

    filename = os.path.basename(fpath)
    mime, _enc = mimetypes.guess_type(filename)
    mime = mime or "application/octet-stream"
    if mime.startswith("image/"):
        wa_type = "image"
    elif mime.startswith("audio/"):
        wa_type = "audio"
    elif mime.startswith("video/"):
        wa_type = "video"
    else:
        wa_type = "document"

    # upload media a Meta
    with open(fpath, "rb") as fh:
        up = requests.post(
            f"https://graph.facebook.com/v21.0/{pnid}/media",
            data={"messaging_product": "whatsapp"},
            files={"file": (filename, fh, mime)},
            headers={"Authorization": f"Bearer {token}"},
            timeout=180,
        )
    up_json = up.json() if up.text else {}
    mid = up_json.get("id")
    if not mid:
        return {"ok": False,
                "error": up_json.get("error", {}).get("message") or up.text[:300]}

    # invio messaggio
    cap = (caption or "")[:900]
    media_payload = {"id": mid}
    if wa_type == "document":
        media_payload["filename"] = filename
    if cap and wa_type != "audio":
        media_payload["caption"] = cap
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": wa_type,
        wa_type: media_payload,
    }
    r = requests.post(
        f"https://graph.facebook.com/v21.0/{pnid}/messages",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp = r.json() if r.text else {}
    ok = r.status_code == 200 and bool(resp.get("messages"))
    wa_mid = resp["messages"][0].get("id", "") if ok else ""

    # log outbound
    lead.append("messages", {
        "direction": "Outbound",
        "sent_at": now_datetime(),
        "content": cap or f"📎 {filename}",
        "media_url": file_url,
        "status": "Inviato" if ok else "Fallito",
        "sent_by": frappe.session.user,
        "wa_message_id": wa_mid,
    })
    lead.db_set("last_message_at", now_datetime(), notify=False)
    lead.save(ignore_permissions=True)
    frappe.db.commit()

    if not ok:
        return {"ok": False,
                "error": resp.get("error", {}).get("message") or str(resp)[:300]}
    return {"ok": True, "message_id": wa_mid,
            "file_url": file_url, "filename": filename, "wa_type": wa_type}


@frappe.whitelist()
def global_search(q, limit=20):
    """Ricerca globale cross-doctype per la Switchboard: chat, casi, reperti,
    clienti. Ritorna un dict per tipo, ognuno con lista di risultati."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"chats": [], "cases": [], "evidences": [], "clients": []}
    like = f"%{q}%"
    limit = min(int(limit), 50)
    out = {}
    out["chats"] = frappe.db.sql(
        """
        SELECT l.name, l.source_name, l.source_identifier, l.source_type,
               l.status, l.linked_case
        FROM `tabIntel Lead` l
        WHERE l.source_name LIKE %s OR l.source_identifier LIKE %s
           OR l.name LIKE %s
        ORDER BY l.last_message_at DESC LIMIT %s
        """,
        (like, like, like, limit), as_dict=True,
    )
    out["cases"] = frappe.db.sql(
        """
        SELECT c.name, c.case_title, c.status, c.case_type,
               (SELECT client_name FROM `tabInvestigation Client`
                WHERE name = c.client) as client_name
        FROM `tabInvestigation Case` c
        WHERE c.name LIKE %s OR c.case_title LIKE %s OR c.summary LIKE %s
        ORDER BY c.modified DESC LIMIT %s
        """,
        (like, like, like, limit), as_dict=True,
    )
    out["evidences"] = frappe.db.sql(
        """
        SELECT e.name, e.evidence_name, e.investigation_case, e.authenticity,
               LEFT(e.notes, 140) as notes_preview
        FROM `tabInvestigation Evidence` e
        WHERE e.evidence_name LIKE %s OR e.notes LIKE %s
        ORDER BY e.creation DESC LIMIT %s
        """,
        (like, like, limit), as_dict=True,
    )
    out["clients"] = frappe.db.sql(
        """
        SELECT name, client_name, client_type, phone, email
        FROM `tabInvestigation Client`
        WHERE client_name LIKE %s OR name LIKE %s OR phone LIKE %s
           OR email LIKE %s
        ORDER BY modified DESC LIMIT %s
        """,
        (like, like, like, like, limit), as_dict=True,
    )
    # ricerca anche nei messaggi (contenuti, ultimi N giorni)
    out["messages"] = frappe.db.sql(
        """
        SELECT m.parent as lead, m.direction, m.sent_at,
               LEFT(m.content, 160) as preview,
               l.source_name, l.source_identifier
        FROM `tabIntel Lead Message` m
        JOIN `tabIntel Lead` l ON l.name = m.parent
        WHERE m.content LIKE %s AND m.creation > NOW() - INTERVAL 60 DAY
        ORDER BY m.sent_at DESC LIMIT %s
        """,
        (like, limit), as_dict=True,
    )
    return out
