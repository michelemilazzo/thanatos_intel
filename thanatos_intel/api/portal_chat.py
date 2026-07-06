"""API per la chat web cliente (/portal/chat). Scope: solo casi del cliente
loggato. Riusa Intel Lead esistente del cliente, ne crea uno nuovo se non c'è."""
import frappe
from frappe import _
from frappe.utils import now_datetime


def _guard(case_name):
    if frappe.session.user == "Guest":
        frappe.throw(_("Login richiesto."), frappe.PermissionError)
    from thanatos_intel.permissions import visible_case_names, is_full_access
    if not is_full_access(frappe.session.user):
        visible = visible_case_names(frappe.session.user) or []
        if case_name not in visible:
            frappe.throw(_("Accesso negato al caso {0}").format(case_name),
                         frappe.PermissionError)


def _get_or_create_lead(case_name, user):
    """Trova (o crea) un Intel Lead di tipo Portal per questo caso+utente."""
    lead = frappe.db.get_value(
        "Intel Lead",
        {"linked_case": case_name, "source_type": "Portal"},
        "name",
    )
    if lead:
        return lead
    # se c'è già un lead WhatsApp collegato lo riuso (thread unificato)
    lead = frappe.db.get_value(
        "Intel Lead",
        {"linked_case": case_name, "source_type": "WhatsApp"},
        "name",
    )
    if lead:
        return lead
    # crea nuovo
    doc = frappe.get_doc({
        "doctype": "Intel Lead",
        "source_type": "Portal",
        "source_identifier": user,
        "source_name": frappe.db.get_value("User", user, "full_name") or user,
        "linked_case": case_name,
        "status": "Aperto",
    })
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


@frappe.whitelist()
def get_case_thread(case_name):
    """Ritorna i messaggi del thread cliente per il caso. Scope: solo casi
    visibili all'utente loggato."""
    _guard(case_name)
    lead = _get_or_create_lead(case_name, frappe.session.user)
    doc = frappe.get_doc("Intel Lead", lead)
    messages = []
    for m in sorted(doc.messages or [], key=lambda x: x.sent_at or ""):
        content = (m.content or "").strip()
        if content.startswith("[") or content.startswith("—"):
            continue
        messages.append({
            "direction": m.direction,
            "content": content,
            "sent_at": str(m.sent_at or ""),
            "media_url": m.media_url,
        })
    return {"lead": lead, "case": case_name, "messages": messages}


@frappe.whitelist()
def send_message(case_name, message_text):
    """Cliente scrive dal portale. Registriamo come Inbound e notifichiamo gli
    operatori (realtime + push)."""
    _guard(case_name)
    text = (message_text or "").strip()
    if not text:
        return {"ok": False}
    lead = _get_or_create_lead(case_name, frappe.session.user)
    doc = frappe.get_doc("Intel Lead", lead)
    doc.append("messages", {
        "direction": "Inbound",
        "sent_at": now_datetime(),
        "content": text,
        "status": "Ricevuto",
        "sent_by": frappe.session.user,
    })
    doc.db_set("last_message_at", now_datetime(), notify=False)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    try:
        frappe.publish_realtime(
            "centralino_update",
            {"lead": lead, "type": "new_message", "source": "portal"},
            after_commit=True,
        )
    except Exception:
        pass
    try:
        from thanatos_intel.api.push import on_new_inbound_message
        on_new_inbound_message(lead, doc.source_name, text)
    except Exception:
        pass
    return {"ok": True, "lead": lead}


@frappe.whitelist()
def send_media(case_name, file_url, caption=""):
    """Cliente carica un file (allegato o nota vocale) via portale. Lo salva
    come messaggio Inbound sul lead e notifica gli operatori."""
    _guard(case_name)
    import os
    lead = _get_or_create_lead(case_name, frappe.session.user)
    doc = frappe.get_doc("Intel Lead", lead)
    rel = (file_url or "").split("/files/", 1)[-1]
    fname = os.path.basename(rel) or "allegato"
    doc.append("messages", {
        "direction": "Inbound",
        "sent_at": now_datetime(),
        "content": (caption or "").strip() or f"📎 {fname}",
        "media_url": file_url,
        "status": "Ricevuto",
        "sent_by": frappe.session.user,
    })
    doc.db_set("last_message_at", now_datetime(), notify=False)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    try:
        frappe.publish_realtime(
            "centralino_update",
            {"lead": lead, "type": "new_message", "source": "portal", "has_media": True},
            after_commit=True,
        )
    except Exception:
        pass
    try:
        from thanatos_intel.api.push import on_new_inbound_message
        on_new_inbound_message(lead, doc.source_name, f"📎 {fname}")
    except Exception:
        pass
    return {"ok": True, "lead": lead, "filename": fname}


_EXPLAIN_SYS = (
    "Sei l'assistente Thanatos Intel per un CLIENTE. Ricevi il testo di un "
    "documento che il cliente ti ha appena caricato. Rispondi SOLO con JSON "
    "valido, nessun testo fuori: "
    '{"spiegazione":"spiegazione chiara e sintetica al cliente (del Lei, '
    'max 120 parole, cosa e il documento e cosa comporta)",'
    '"riassunto":"riassunto tecnico 2-3 frasi per l operatore",'
    '"tipo_documento":"tipo (contratto/visura/fattura/sentenza/...)",'
    '"leggi_citate":["eventuali riferimenti normativi/articoli citati nel testo"],'
    '"dati_chiave":{"campo":"valore per i dati salienti (importi, date, parti, '
    'P.IVA, numeri)"},'
    '"da_approfondire":["eventuali punti che l operatore dovrebbe verificare"]}'
)


@frappe.whitelist()
def ai_explain_document(case_name, file_url, question=""):
    """Il cliente carica un documento in modalità AI: lo leggiamo (OCR),
    l'AI lo spiega al cliente e SALVA l'estratto strutturato (riassunto, leggi
    citate, dati chiave) in una cartella Drive del caso per consultazione rapida
    dell'operatore + Case Activity. Scope: solo casi del cliente."""
    _guard(case_name)
    import json
    import os
    # 1) OCR / lettura testo del documento
    from thanatos_intel.ai.ops_brain import _t_read_document
    r = _t_read_document(file_url=file_url)
    if r.get("error"):
        return {"ok": False, "error": r["error"]}
    text = (r.get("text") or "").strip()
    if not text or "illeggibile" in text:
        return {"ok": False, "error": "Documento vuoto o illeggibile."}

    # 2) estrazione strutturata via motore economico
    from thanatos_intel.ai.ops_brain import _cheap_chat
    from thanatos_intel.ai.doc_ingest import _extract_json
    q = f"\n\nDomanda del cliente: «{question}»" if question else ""
    out, _u = _cheap_chat(f"Testo del documento:\n\n{text[:9000]}{q}", _EXPLAIN_SYS)
    parsed = _extract_json(out) or {}
    spiegazione = (parsed.get("spiegazione")
                   or out[:600] if out else "Non sono riuscito ad analizzare il documento.")

    fname = os.path.basename((file_url or "").split("/files/")[-1]) or "documento"

    # 3) salva l'estratto in una cartella del caso per l'operatore
    md = _estratto_md(fname, parsed, question)
    _save_estratto(case_name, fname, md, parsed, file_url)

    return {"ok": True, "spiegazione": spiegazione,
            "tipo": parsed.get("tipo_documento", ""),
            "leggi": parsed.get("leggi_citate") or [],
            "filename": fname}


def _estratto_md(fname, parsed, question):
    lines = [f"# Estratto AI — {fname}",
             f"**Tipo:** {parsed.get('tipo_documento', 'n/d')}",
             ""]
    if question:
        lines += [f"**Domanda del cliente:** {question}", ""]
    if parsed.get("riassunto"):
        lines += ["## Riassunto (operatore)", parsed["riassunto"], ""]
    if parsed.get("spiegazione"):
        lines += ["## Spiegazione data al cliente", parsed["spiegazione"], ""]
    dk = parsed.get("dati_chiave") or {}
    if dk:
        lines += ["## Dati chiave"] + [f"- **{k}:** {v}" for k, v in dk.items()] + [""]
    leggi = parsed.get("leggi_citate") or []
    if leggi:
        lines += ["## Riferimenti normativi citati"] + [f"- {x}" for x in leggi] + [""]
    da = parsed.get("da_approfondire") or []
    if da:
        lines += ["## Da approfondire"] + [f"- [ ] {x}" for x in da] + [""]
    return "\n".join(lines)


_TIPO_LEGALE = ("contratto", "sentenza", "atto", "delega", "procura",
                "mandato", "diffida", "notarile", "notaio", "verbale",
                "citazione", "decreto", "ordinanza", "querela", "denuncia")
_TIPO_REPORT = ("dossier", "perizia", "relazione", "report",
                "investigativ", "screening", "due diligence")


def _subfolder_by_tipo(tipo, fname=""):
    """Cartella Drive per NATURA del documento (allineata alle sub esistenti
    del sistema): 07 Legale / 05 Report / 01 Documenti (default)."""
    t = ((tipo or "") + " " + (fname or "")).lower()
    if any(k in t for k in _TIPO_LEGALE):
        return "07 Legale"
    if any(k in t for k in _TIPO_REPORT):
        return "05 Report"
    return "01 Documenti"


def _load_file_bytes(file_url):
    """Legge i bytes di un file Frappe dal filesystem locale."""
    import os
    if not file_url:
        return None, "application/octet-stream"
    rel = file_url.split("/files/", 1)[-1]
    subdir = "private" if "/private/" in file_url else "public"
    path = frappe.get_site_path(subdir, "files", rel)
    if not os.path.exists(path):
        return None, "application/octet-stream"
    import mimetypes
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        return f.read(), mime


def _save_estratto(case_name, fname, md, parsed, file_url=None):
    """Archivia ORIGINALE + estratto AI nella stessa subfolder Drive scelta
    per NATURA. L'estratto ha suffisso '[ESTRATTO AI]' nel nome per essere
    riconoscibile dall'operatore. Registra Case Activity con destinazione."""
    from thanatos_intel.reporting.case_reports import _put_in_drive, _client_name
    try:
        client = _client_name(frappe.get_doc("Investigation Case", case_name))
    except Exception:
        client = ""
    sub = _subfolder_by_tipo(parsed.get("tipo_documento", ""), fname)
    base = fname.rsplit(".", 1)[0]

    try:
        content, mime = _load_file_bytes(file_url)
        if content:
            _put_in_drive(case_name, fname, content, mime, client, subfolder=sub)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "portal ai originale drive")

    try:
        _put_in_drive(case_name,
                      f"{base} [ESTRATTO AI].md",
                      md.encode("utf-8"), "text/markdown", client,
                      subfolder=sub)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "portal ai estratto drive")

    try:
        c = frappe.get_doc("Investigation Case", case_name)
        riass = (parsed.get("riassunto") or "")[:400]
        leggi = ", ".join(parsed.get("leggi_citate") or [])
        desc = (f"🤖 [Estratto AI] {fname} → archiviato in *{sub}*\n"
                f"Tipo: {parsed.get('tipo_documento', 'n/d')}\n{riass}"
                + (f"\nLeggi citate: {leggi}" if leggi else ""))
        c.append("case_activities", {
            "activity_date": now_datetime(), "activity_type": "Document Analysis",
            "description": desc[:1000], "operator": "Administrator"})
        c.flags.ignore_mandatory = True
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "portal ai estratto activity")

    try:
        leggi = ", ".join(parsed.get("leggi_citate") or [])
        notes = ((parsed.get("riassunto") or "")[:1500]
                 + (f"\n\nLeggi citate: {leggi}" if leggi else "")
                 + f"\n\nCartella Drive: {sub}")
        ev = frappe.get_doc({
            "doctype": "Investigation Evidence",
            "investigation_case": case_name,
            "evidence_name": f"[ESTRATTO AI] {fname}",
            "evidence_type": "Document",
            "source": "portale AI cliente",
            "custody_status": "Received",
            "acquisition_date": now_datetime(),
            "notes": notes[:5000],
        })
        ev.flags.ignore_mandatory = True
        ev.insert(ignore_permissions=True)
        try:
            from frappe.utils.file_manager import save_file
            save_file(f"{base} [ESTRATTO AI].md", md.encode("utf-8"),
                     "Investigation Evidence", ev.name, is_private=1)
            ev.reload()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "portal ai evidence attach")
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "portal ai evidence create")


# ─────────────── AI: spiega documento al cliente + estratto operatore ─────────
