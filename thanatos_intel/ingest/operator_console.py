"""Canale operatore su WhatsApp.

Quando il mittente di un messaggio WhatsApp e' un investigatore noto (numero che
matcha Investigator.phone), il messaggio NON e' di un cliente: e' un comando
operativo. L'operatore puo' inviare documenti e poi un comando testuale
("elabora gli allegati ed apri un caso") per far creare a MMOS AI un
Investigation Case con i documenti gia' ingeriti (OCR + estrazione + reperti).
"""
import re
import frappe
from frappe.utils import now_datetime, get_url


def _digits(n):
    return re.sub(r"\D", "", n or "")


def _operator_user(operator):
    """Risolve l'Investigator nel suo User (campo platform_user). Fallback Administrator.
    Serve per i campi Link→User (promoted_by, notifiche), che NON accettano il nome
    dell'Investigator."""
    u = frappe.db.get_value("Investigator", operator, "platform_user") if operator else None
    return u or "Administrator"


def find_operator(number):
    """Ritorna il nome dell'Investigator se il numero corrisponde a un operatore."""
    d = _digits(number)
    if len(d) < 8:
        return None
    tail = d[-9:]
    for r in frappe.get_all("Investigator", fields=["name", "phone"], limit=0):
        if r.phone and _digits(r.phone).endswith(tail):
            return r.name
    return None


_OPEN_CASE_RE = re.compile(
    r"(apr[ai].{0,12}\bcas[oi]\b|crea.{0,12}\bcas[oi]\b|elabor.{0,20}allegat|"
    r"\bapri\b.{0,12}\bpratica\b|processa.{0,20}allegat|analizz.{0,20}allegat)",
    re.I,
)
_HELP_RE = re.compile(r"\b(aiuto|help|comandi|cosa puoi fare)\b", re.I)
_REPROCESS_RE = re.compile(
    r"(rilegg|ri-?legg|ri-?process|riprov.{0,12}ocr|ri-?fai.{0,10}ocr|"
    r"\bleggi\b.{0,14}(allegat|document)|ocr.{0,14}divers)", re.I)
_QUESTIONS_RE = re.compile(
    r"(domand.{0,14}(document|allegat|reperti|cas)|fai.{0,8}le domand|"
    r"poni.{0,14}domand|investigatore digitale|domande investigative)", re.I)


def handle_operator_message(lead_name, wa_phone, sender, text, operator):
    """Instrada il messaggio dell'operatore. Solo i comandi riconosciuti agiscono;
    i messaggi normali/allegati vengono solo registrati (no bot, no auto-reply)."""
    t = (text or "").strip()
    if not t or t.startswith("["):
        return  # media/placeholder: gia' allegato, niente da fare
    if _OPEN_CASE_RE.search(t):
        frappe.enqueue(
            "thanatos_intel.ingest.operator_console.run_open_case",
            queue="long", timeout=1200,
            lead_name=lead_name, wa_phone=wa_phone, sender=sender, operator=operator,
        )
        _reply(wa_phone, sender, lead_name,
               "\U0001F6E0️ Ricevuto. Sto elaborando gli allegati e apro la "
               "pratica: le mando l'esito tra poco.")
        return
    if _REPROCESS_RE.search(t):
        case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Non c'e' ancora un caso collegato a questa chat. Prima «apri un caso».")
            return
        frappe.enqueue("thanatos_intel.ingest.operator_console.reprocess_case_docs",
                       queue="long", timeout=1800, case=case, lead_name=lead_name,
                       wa_phone=wa_phone, sender=sender)
        _reply(wa_phone, sender, lead_name,
               "\U0001F501 Rileggo i documenti del caso con l'OCR, le mando l'esito tra poco.")
        return
    if _QUESTIONS_RE.search(t):
        case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Non c'e' ancora un caso collegato a questa chat. Prima «apri un caso».")
            return
        frappe.enqueue("thanatos_intel.ai.doc_questions.generate_questions",
                       queue="long", timeout=1200, case=case, lead_name=lead_name,
                       wa_phone=wa_phone, sender=sender, post=1)
        _reply(wa_phone, sender, lead_name,
               "\U0001F575️ Da investigatore digitale: preparo le domande per ogni "
               "documento, gliele mando tra poco.")
        return
    if _HELP_RE.search(t):
        _reply(wa_phone, sender, lead_name,
               "Sono il tuo assistente operativo. Puoi:\n"
               "• farmi domande su casi, lead e documenti\n"
               "• inviare i documenti e scrivere «*elabora gli allegati ed apri un "
               "caso*» → apro la pratica con i reperti gia' analizzati (OCR + AI)\n"
               "• chiedermi la sintesi di un caso (es. «riassumi CASE-2026-0026»)")
        return
    # messaggio operatore libero → assistente AI operativo (co-pilota), in background
    frappe.enqueue(
        "thanatos_intel.ingest.operator_console.operator_assistant_reply",
        queue="short", timeout=200,
        lead_name=lead_name, wa_phone=wa_phone, sender=sender, text=t, operator=operator,
    )
    return


_OP_SYS = (
    "Sei l'assistente operativo interno di Thanatos Intel (agenzia investigativa, sede "
    "Romania, GDPR/Legea 329-2003). Parli su WhatsApp con un OPERATORE interno "
    "(investigatore/manager), NON con un cliente: dagli del tu, tono diretto e concreto, "
    "niente disclaimer commerciali ne' presentazioni dell'agenzia. Aiutalo nel lavoro: "
    "rispondi su casi/lead, riassumi documenti e pratiche, suggerisci i prossimi passi "
    "investigativi, redigi note/testi. Usa SOLO le informazioni nel contesto fornito; se "
    "un dato non c'e', dillo e indica come ottenerlo. Ricorda all'operatore, quando "
    "pertinente, che inviando documenti e scrivendo «elabora gli allegati ed apri un caso» "
    "apri una pratica con i reperti analizzati. Risposte brevi e operative (max ~120 "
    "parole), in italiano."
)


def _case_brief(case):
    c = frappe.db.get_value("Investigation Case", case,
                            ["case_title", "case_type", "status", "summary"],
                            as_dict=True) or {}
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=["evidence_name", "notes"], limit=20)
    lines = [f"Caso {case}: {c.get('case_title')} [{c.get('status')}] "
             f"tipo {c.get('case_type')}"]
    if c.get("summary"):
        lines.append("Sintesi: " + c["summary"])
    if evs:
        lines.append(f"Reperti ({len(evs)}):")
        for e in evs[:12]:
            note = (e.notes or "").replace("\n", " ").strip()
            lines.append(f"  • {e.evidence_name}: {note[:140]}")
    return "\n".join(lines)


def _operator_context(operator, lead_name, text):
    parts = []
    codename = frappe.db.get_value("Investigator", operator, "codename")
    parts.append("Operatore: " + operator + (f" ({codename})" if codename else ""))
    refs = []
    lc = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
    if lc:
        refs.append(lc)
    for tok in re.findall(r"CASE-\d{4}-\d+", text or "", re.I):
        tok = tok.upper()
        if tok not in refs and frappe.db.exists("Investigation Case", tok):
            refs.append(tok)
    for cn in refs[:3]:
        parts.append(_case_brief(cn))
    rec = frappe.get_all("Investigation Case",
                         fields=["name", "case_title", "status", "case_type"],
                         order_by="modified desc", limit=8)
    if rec:
        parts.append("Casi recenti:\n" + "\n".join(
            f"- {c.name} [{c.status}] {c.case_type or ''}: {c.case_title}" for c in rec))
    return "\n\n".join(parts)


@frappe.whitelist()
def operator_assistant_reply(lead_name, wa_phone, sender, text, operator):
    """Co-pilota AI per l'operatore: risponde su WhatsApp con supporto operativo
    fondato sul contesto reale (casi, lead, reperti)."""
    from thanatos_intel.ai.doc_ingest import _gateway
    from thanatos_intel.ai.case_architect import _resp_text
    ctx = _operator_context(operator, lead_name, text)
    msg = (f"Contesto operativo:\n{ctx}\n\n"
           f"Messaggio dell'operatore: «{text}»\n\nRispondi all'operatore.")
    resp = _gateway(msg, system=_OP_SYS, task_type="chat", session_id=f"op-{operator}")
    out = (_resp_text(resp) or "").strip()
    if not out:
        out = "Ricevuto. (assistente AI momentaneamente non disponibile)"
    _reply(wa_phone, sender, lead_name, out)
    try:
        usage = (resp or {}).get("usage") or {}
        if usage.get("tokens_in") or usage.get("tokens_out"):
            from thanatos_intel.billing.ai_meter import record_usage
            record_usage(client=None, model=(resp or {}).get("model", "default"),
                         tokens_in=usage.get("tokens_in", 0),
                         tokens_out=usage.get("tokens_out", 0), reference=lead_name)
    except Exception:
        pass
    return {"ok": True}


_DOC_EXT = (".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".tiff", ".tif")


def _lead_documents(lead_name):
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Intel Lead", "attached_to_name": lead_name},
        fields=["name", "file_name", "file_url"],
        order_by="creation asc", limit=0,
    )
    out, seen = [], set()
    for f in files:
        if not (f.file_name or "").lower().endswith(_DOC_EXT):
            continue
        key = (f.file_url or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


_CLASSIFY_SYS = (
    "Sei un analista di Thanatos Intel. Ricevi l'elenco dei nomi dei documenti di una "
    "nuova pratica investigativa. Scegli il tipo di caso piu' adatto SOLO tra questi: "
    "{types}. Rispondi SOLO con JSON valido, nessun testo fuori dal JSON: "
    '{{"case_type":"<uno dei tipi elencati>","case_title":"titolo breve in italiano",'
    '"summary":"2 frasi di sintesi"}}'
)


def _classify_case(doc_names, case_types):
    from thanatos_intel.ai.doc_ingest import _gateway, _extract_json
    from thanatos_intel.ai.case_architect import _resp_text
    sys = _CLASSIFY_SYS.format(types=", ".join(case_types))
    msg = ("Documenti della pratica:\n- " + "\n- ".join(doc_names) +
           "\n\nRispondi SOLO con il JSON richiesto.")
    resp = _gateway(msg, system=sys, task_type="chat")
    return _extract_json(_resp_text(resp)) or {}


_BOX_CASES = "/mnt/thanatos-box/Cases"
_MIME = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
         "jpeg": "image/jpeg", "webp": "image/webp", "tiff": "image/tiff",
         "tif": "image/tiff", "txt": "text/plain",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _ensure_case_box(case):
    """Garantisce che la cartella Drive del caso viva nel box dedicato
    (/mnt/thanatos-box/Cases/<CASE>), sostituendo la dir locale con un symlink.
    Idempotente. Ritorna il path box o None."""
    import os
    import shutil
    folder = frappe.db.get_value("Investigation Case", case, "drive_folder")
    rel = frappe.db.get_value("Drive File", folder, "path") if folder else None
    if not rel:
        return None
    local = frappe.get_site_path("private", "files", rel.rstrip("/"))
    box = os.path.join(_BOX_CASES, case)
    try:
        if os.path.islink(local):
            return os.path.realpath(local)
        if not os.path.isdir("/mnt/thanatos-box"):
            return None
        os.makedirs(box, exist_ok=True)
        if os.path.isdir(local):
            for entry in os.listdir(local):
                s, d = os.path.join(local, entry), os.path.join(box, entry)
                if not os.path.exists(d):
                    shutil.move(s, d)
            shutil.rmtree(local, ignore_errors=True)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        os.symlink(box, local)
        return box
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator _ensure_case_box")
        return None


def _consolidate_to_box(local, box_copy):
    """Ri-punta il file/symlink locale del lead alla copia nel box del caso e rimuove
    la vecchia copia orfana (es. attachments/intel_lead/...). Una sola copia fisica."""
    import os
    try:
        if not (box_copy and os.path.isfile(box_copy)):
            return
        old_target = os.path.realpath(local) if os.path.islink(local) else None
        if old_target == box_copy:
            return  # già consolidato
        # sicurezza: stessa dimensione prima di sostituire
        cur = local if os.path.exists(local) else None
        if cur and os.path.getsize(os.path.realpath(local)) != os.path.getsize(box_copy):
            return
        if os.path.lexists(local):
            os.remove(local)
        os.symlink(box_copy, local)
        # rimuovi la copia box orfana (solo sotto /mnt/thanatos-box/attachments/)
        if (old_target and old_target != box_copy
                and old_target.startswith("/mnt/thanatos-box/attachments/")
                and os.path.isfile(old_target)):
            os.remove(old_target)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator _consolidate_to_box")


def archive_lead_docs_to_case(case, lead_name):
    """Archivia i documenti del lead nella cartella Drive del caso (box dedicato),
    sottocartella '01 Documenti'. Dopo l'archiviazione consolida: una sola copia
    fisica nel box del caso, l'allegato del lead diventa symlink a quella copia,
    le copie orfane (attachments/intel_lead) vengono rimosse. Idempotente."""
    import os
    from thanatos_intel.reporting.case_reports import _put_in_drive, _client_name
    _ensure_case_box(case)
    client = _client_name(frappe.get_doc("Investigation Case", case))
    n = 0
    for d in _lead_documents(lead_name):
        local = frappe.get_site_path("private", "files", (d.file_url or "").split("/files/")[-1])
        if not os.path.exists(local):
            continue
        ext = (d.file_name or "").rsplit(".", 1)[-1].lower()
        mime = _MIME.get(ext, "application/octet-stream")
        try:
            with open(local, "rb") as fh:
                drive_name = _put_in_drive(case, d.file_name, fh.read(), mime, client,
                                           subfolder="01 Documenti")
            if drive_name:
                rel = frappe.db.get_value("Drive File", drive_name, "path")
                box_copy = os.path.realpath(
                    frappe.get_site_path("private", "files", rel)) if rel else None
                _consolidate_to_box(local, box_copy)
            n += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"operator archive doc {d.file_name}")
    return n


@frappe.whitelist()
def run_open_case(lead_name, wa_phone=None, sender=None, operator=None):
    """Job: crea un Investigation Case dai documenti allegati al lead e li ingerisce."""
    docs = _lead_documents(lead_name)
    if not docs:
        _reply(wa_phone, sender, lead_name,
               "⚠️ Non trovo allegati su questa conversazione. Inviami prima "
               "i documenti, poi ripeti il comando.")
        return {"ok": False, "reason": "no documents"}

    from thanatos_intel.ai.doc_ingest import ingest_document

    case_types = [r.name for r in frappe.get_all("Case Type", limit=0)]
    cls = _classify_case([d.file_name for d in docs], case_types)
    ctype = cls.get("case_type") if cls.get("case_type") in case_types else (
        "Due Diligence" if "Due Diligence" in case_types else
        (case_types[0] if case_types else None))
    title = (cls.get("case_title") or f"Pratica WhatsApp {now_datetime():%d/%m %H:%M}")[:140]

    case = frappe.new_doc("Investigation Case")
    case.case_title = title
    if ctype:
        case.case_type = ctype
    case.status = "Open"
    case.priority = "High"
    case.opening_date = now_datetime()
    case.description = (cls.get("summary") or "")[:2000]
    case.summary = (cls.get("summary") or "")[:1000]
    case.insert(ignore_permissions=True)
    frappe.db.commit()

    # archivia i documenti nella cartella Drive del caso (box dedicato)
    try:
        archive_lead_docs_to_case(case.name, lead_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator archive_lead_docs")

    results = []
    for d in docs:
        try:
            r = ingest_document(file_url=d.file_url, investigation_case=case.name,
                                document_type="generic") or {}
            ex = r.get("extracted") or {}
            results.append({"file": d.file_name, "summary": ex.get("summary", ""),
                            "flags": ex.get("risk_flags") or [],
                            "entities": ex.get("entities") or [],
                            "authenticity": r.get("authenticity") or "Non determinabile",
                            "evidence": r.get("evidence")})
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"operator ingest {d.file_name}")
            results.append({"file": d.file_name, "summary": "(errore analisi)", "flags": [],
                            "entities": [], "authenticity": "Non determinabile"})
        frappe.db.commit()

    # anagrafica ISO: registra TUTTE le parti come entità + crea l'anagrafica cliente
    all_entities = [e for r in results for e in (r.get("entities") or [])]
    n_parties = 0
    try:
        n_parties = _register_parties(case.name, all_entities)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator register_parties")
    try:
        _ensure_case_client(case.name, lead_name, sender)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator ensure_client")

    op_user = _operator_user(operator)
    try:
        lead = frappe.get_doc("Intel Lead", lead_name)
        lead.db_set("linked_case", case.name, notify=False)
        lead.db_set("status", "Promosso a Caso", notify=False)
        lead.db_set("promoted_at", now_datetime(), notify=False)
        lead.db_set("promoted_by", op_user, notify=False)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator link case")

    n_flags = sum(len(r.get("flags") or []) for r in results)
    suspect = [r for r in results if r.get("authenticity") in ("Dubbio", "Manomesso", "Contraffatto")]
    lines = [f"✅ Pratica aperta: *{case.name}*",
             f"{title}",
             f"Tipo: {ctype or 'n/d'} · {len(results)} documenti analizzati"]
    if n_flags:
        lines.append(f"⚠️ {n_flags} red flag rilevati")
    if suspect:
        lines.append(f"\U0001F50E {len(suspect)} documenti con autenticità non confermata "
                     "(dubbio/manomesso/contraffatto)")
    if n_parties:
        lines.append(f"\U0001F465 {n_parties} parti identificate e schedate (entità)")
    lines.append("\U0001F4E6 documenti archiviati nel box del caso")
    lines.append("")
    _AICON = {"Autentico": "✅", "Dubbio": "❓", "Manomesso": "⚠️",
              "Contraffatto": "⛔", "Non determinabile": "▫️"}
    for r in results[:12]:
        s = (r.get("summary") or "").strip().replace("\n", " ")
        ic = _AICON.get(r.get("authenticity"), "▫️")
        lines.append(f"{ic} {r['file']}: {s[:130]}" if s else f"{ic} {r['file']}")
    if len(results) > 12:
        lines.append(f"… e altri {len(results) - 12} documenti")
    lines.append("")
    lines.append(f"\U0001F517 {get_url('/app/investigation-case/' + case.name)}")
    _reply(wa_phone, sender, lead_name, "\n".join(lines))

    # automazione: lancia l'intera pipeline analitica in background (screening, doppia
    # cessione, domande, riconciliazione fatture, fascicolo, checklist)
    try:
        frappe.enqueue("thanatos_intel.ai.case_orchestrator.run_full_analysis",
                       queue="long", timeout=2400, case=case.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "enqueue full analysis")

    _notify_desk(lead_name, case.name, op_user, len(results), n_flags)
    return {"ok": True, "case": case.name, "documents": len(results), "flags": n_flags}


_ENTITY_TYPE = {"person": "Person", "company": "Company"}


def _register_parties(case_name, entities):
    """Schedatura ISO: ogni parte (persona/azienda) diventa una Investigation Entity
    collegata al caso (Case Entity). Dedup per nome+tipo. Ritorna n. nuove parti."""
    case = frappe.get_doc("Investigation Case", case_name)
    linked = {ce.entity for ce in (case.get("case_entities") or [])}
    seen, created = set(), 0
    for e in entities or []:
        etype = _ENTITY_TYPE.get((e.get("type") or "").lower())
        name = (e.get("name") or "").strip()
        norm = re.sub(r"[^\w\s]", "", name.lower())
        norm = re.sub(r"\b(s\s*r\s*l|srl|spa|s\s*p\s*a|snc|sas|srls)\b", "", norm)
        norm = re.sub(r"\s+", " ", norm).strip()
        key = (etype, norm)
        if not etype or len(name) < 3 or key in seen:
            continue
        seen.add(key)
        ent = frappe.db.get_value("Investigation Entity",
                                  {"full_name": name, "entity_type": etype}, "name")
        if not ent:
            doc = frappe.get_doc({"doctype": "Investigation Entity", "entity_type": etype,
                                  "full_name": name, "primary_identifier": name,
                                  "status": "Active"})
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            ent = doc.name
        if ent not in linked:
            case.append("case_entities", {"entity": ent, "entity_type": etype,
                                          "role_in_case": "Subject",
                                          "notes": (e.get("role") or "")[:140]})
            linked.add(ent)
            created += 1
    if created:
        case.save(ignore_permissions=True)
        frappe.db.commit()
    return created


def _ensure_case_client(case_name, lead_name, sender):
    """Crea/collega l'anagrafica cliente del caso con KYC/KYB da completare.
    Se il mittente è un operatore (caso aperto per conto terzi) crea un placeholder
    «da identificare»; altrimenti usa i dati del lead. ISO: il cliente va sempre
    identificato (KYC/KYB)."""
    case = frappe.get_doc("Investigation Case", case_name)
    if case.get("client"):
        return case.client
    is_operator = bool(find_operator(sender))
    src_name = frappe.db.get_value("Intel Lead", lead_name, "source_name") or ""
    phone = "" if is_operator else (frappe.db.get_value("Intel Lead", lead_name,
                                                        "source_identifier") or "")
    cl = frappe.db.get_value("Investigation Client", {"phone": phone}, "name") if phone else None
    if not cl:
        cname = (src_name if (src_name and not is_operator)
                 else f"Cliente da identificare ({case_name})")
        # Investigation Client si autonamina sull'email → sempre una email valida
        email = (f"wa-{_digits(phone)}@lead.thanatos.agency" if phone
                 else f"caso-{case_name.lower()}@daidentificare.thanatos.agency")
        if frappe.db.exists("Investigation Client", email):
            cl = email
        else:
            doc = frappe.get_doc({"doctype": "Investigation Client", "client_name": cname[:140],
                                  "client_type": "Company", "email": email, "phone": phone,
                                  "onboarding_status": "Pending KYC",
                                  "kyc_status": "Not Started", "kyb_status": "Not Started"})
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            cl = doc.name
    case.db_set("client", cl, notify=False)
    frappe.db.commit()
    return cl


def _reply(wa_phone, to_number, lead_name, body):
    if not (wa_phone and to_number):
        return
    try:
        from thanatos_intel.ingest.wa_bot import _wa_doc, send_text
        wd = _wa_doc(wa_phone)
        if wd:
            send_text(wd, to_number, body, lead_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator reply")


def _notify_desk(lead_name, case, operator, ndocs, nflags):
    try:
        from thanatos_intel.ingest.intel_notifications import _notify
        msg = (f"{case}: {ndocs} documenti analizzati"
               + (f", {nflags} red flag" if nflags else ""))
        _notify(operator or "Administrator", "Pratica aperta da WhatsApp", msg,
                lead_name, "orange" if nflags else "green")
    except Exception:
        pass


def _has_summary(notes):
    return bool(notes and "Sintesi AI" in notes and len(notes) > 80)


def _reprocess_evidence(ev):
    """Ri-OCR + ri-estrae un reperto e aggiorna note/nome in place.
    Ritorna (ok, summary)."""
    import json
    from thanatos_intel.ai.ocr_service import ocr_file
    from thanatos_intel.ai.doc_ingest import (_gateway, _extract_json, _normalize,
                                              _read_text_fallback, EXTRACT_SYSTEM)
    from thanatos_intel.ai.case_architect import _resp_text
    fu = ev.get("attached_file")
    if not fu:
        return False, ""
    try:
        ocr = ocr_file(fu, "generic") or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "reprocess ocr")
        ocr = {}
    text = (ocr.get("raw_text") or "").strip() or (_read_text_fallback(fu) or "").strip()
    if not text:
        return False, ""
    ai = _gateway(f"Testo del documento:\n\n{text[:12000]}", system=EXTRACT_SYSTEM,
                  task_type="extract")
    parsed = _normalize(_extract_json(_resp_text(ai)))
    if not parsed:
        return False, ""
    note_lines = ["— Sintesi AI —", parsed.get("summary") or ""]
    if parsed.get("risk_flags"):
        note_lines.append("Red flag: " + "; ".join(parsed["risk_flags"]))
    if parsed.get("key_fields"):
        note_lines.append("Campi: " + json.dumps(parsed["key_fields"], ensure_ascii=False))
    note_lines.append(f"OCR provider: {ocr.get('provider')} · confidenza: {ocr.get('confidence')}")
    frappe.db.set_value("Investigation Evidence", ev["name"], {
        "notes": "\n".join(x for x in note_lines if x),
        "evidence_name": (parsed.get("document_type", "Documento") or "Documento") + " — AI ingest",
    })
    frappe.db.commit()
    return True, (parsed.get("summary") or "")


@frappe.whitelist()
def reprocess_case_docs(case, lead_name=None, wa_phone=None, sender=None, only_failed=1):
    """Ri-legge i documenti di un caso con l'OCR (utile dopo che è stato corretto un
    documento o aggiunto un motore OCR). Default: solo i reperti senza sintesi."""
    only_failed = int(only_failed)
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=["name", "evidence_name", "notes", "attached_file"], limit=0)
    todo = [e for e in evs if (not only_failed) or not _has_summary(e.get("notes"))]
    done, still = 0, 0
    summaries = []
    for e in todo:
        ok, summ = _reprocess_evidence(e)
        if ok:
            done += 1
            if summ:
                summaries.append((e.get("attached_file") or "").split("/files/")[-1] + ": "
                                 + summ.replace("\n", " ")[:120])
        else:
            still += 1
    if wa_phone and sender and lead_name:
        lines = [f"\U0001F501 Riletti {done}/{len(todo)} documenti del caso {case}."]
        if still:
            lines.append(f"⚠️ {still} ancora illeggibili (scansione di bassa qualità).")
        for s in summaries[:8]:
            lines.append("\U0001F4C4 " + s)
        _reply(wa_phone, sender, lead_name, "\n".join(lines))
    return {"ok": True, "reprocessed": done, "still_failed": still}
