"""
Pannello Comunicazione Universale (PCU)
Threading unificato Email + WhatsApp per qualsiasi DocType.
"""
import frappe
from frappe.utils import now_datetime, get_datetime
import json


def _resolve_recipient(doctype: str, name: str) -> dict:
    """Estrae email/phone destinatario dal doc."""
    doc = frappe.get_doc(doctype, name)
    email, phone, label = None, None, None

    # Pattern 1: ha campo applicant (Link Applicant Profile)
    if hasattr(doc, "applicant") and doc.applicant:
        try:
            ap = frappe.get_doc("Applicant Profile", doc.applicant)
            email = ap.email
            phone = ap.phone
            label = ap.full_legal_name
        except Exception:
            pass

    # Pattern 2: campo client (Link Customer) o intestatario_fattura
    if not email:
        for f in ("client", "intestatario_fattura", "customer"):
            v = getattr(doc, f, None)
            if v:
                # cerca contact primario customer
                primary = frappe.db.sql("""SELECT c.email_id, c.mobile_no, c.first_name, c.last_name
                    FROM `tabContact` c JOIN `tabDynamic Link` dl ON dl.parent=c.name
                    WHERE dl.link_doctype='Customer' AND dl.link_name=%s LIMIT 1""", (v,), as_dict=1)
                if primary:
                    email = primary[0].email_id
                    phone = primary[0].mobile_no
                    label = f"{primary[0].first_name or ''} {primary[0].last_name or ''}".strip() or v
                    break

    # Pattern 3: campo email_id diretto
    if not email and hasattr(doc, "email"):
        email = getattr(doc, "email", None)
    if not phone and hasattr(doc, "phone"):
        phone = getattr(doc, "phone", None)

    return {"email": email, "phone": phone, "label": label or "Destinatario"}


@frappe.whitelist()
def get_recipient(doctype: str, name: str) -> dict:
    return _resolve_recipient(doctype, name)


@frappe.whitelist()
def thread(doctype: str, name: str) -> list:
    """Ritorna thread unificato email+WA per il doc."""
    items = []
    # Email Communications agganciati al doc
    comms = frappe.db.sql("""
        SELECT name, communication_date, sender, recipients, subject, content, sent_or_received,
               communication_medium, status
        FROM tabCommunication
        WHERE reference_doctype=%s AND reference_name=%s
        ORDER BY communication_date ASC
    """, (doctype, name), as_dict=1)
    for c in comms:
        items.append({
            "id": c.name,
            "channel": "email",
            "direction": "out" if c.sent_or_received == "Sent" else "in",
            "ts": str(c.communication_date),
            "from_": c.sender,
            "to": c.recipients,
            "subject": c.subject,
            "text": c.content,
            "status": c.status,
        })

    # WABA WhatsApp Messages: usa custom field reference_doctype/reference_name se presenti
    has_ref = frappe.db.has_column("WABA WhatsApp Message", "reference_doctype")
    if has_ref:
        wa = frappe.db.sql("""
            SELECT name, creation, `from`, `to`, type, message_body, status, message_type
            FROM `tabWABA WhatsApp Message`
            WHERE reference_doctype=%s AND reference_name=%s
            ORDER BY creation ASC
        """, (doctype, name), as_dict=1)
        for m in wa:
            items.append({
                "id": m.name,
                "channel": "whatsapp",
                "direction": "in" if m.type == "Incoming" else "out",
                "ts": str(m.creation),
                "from_": m["from"],
                "to": m["to"],
                "subject": None,
                "text": m.message_body,
                "status": m.status,
            })

    items.sort(key=lambda x: x["ts"])
    return items



def _resolve_sender(doctype: str, name: str):
    """Sceglie l'Email Account in uscita in base alla Billing Entity del doc."""
    try:
        doc = frappe.get_doc(doctype, name)
    except Exception:
        return None, None
    be_name = getattr(doc, "billing_entity", None) or getattr(doc, "intestatario_fattura", None)
    if be_name and frappe.db.exists("Billing Entity", be_name):
        ea = frappe.db.get_value("Billing Entity", be_name, "outgoing_email_account")
        if ea:
            sender = frappe.db.get_value("Email Account", ea, "email_id")
            return ea, sender
    return None, None


@frappe.whitelist()
def send_email(doctype: str, name: str, recipients: str, subject: str,
               content: str, template: str = None, attachments: str = None,
               from_email: str = None) -> dict:
    """Manda email e aggancia al doc."""
    if template:
        et = frappe.get_doc("Email Template", template)
        ctx = frappe.get_doc(doctype, name).as_dict()
        subject = frappe.render_template(et.subject, ctx)
        content = frappe.render_template(et.response_html or et.response or "", ctx)

    atts = json.loads(attachments) if attachments and isinstance(attachments, str) else (attachments or [])

    if from_email:
        ea_name = frappe.db.get_value("Email Account", {"email_id": from_email}, "name")
        sender_email = from_email
    else:
        ea_name, sender_email = _resolve_sender(doctype, name)
    comm = frappe.get_doc({
        "doctype": "Communication",
        "communication_type": "Communication",
        "communication_medium": "Email",
        "sent_or_received": "Sent",
        "subject": subject,
        "content": content,
        "sender": sender_email or frappe.session.user,
        "recipients": recipients,
        "status": "Linked",
        "email_account": ea_name,
        "reference_doctype": doctype,
        "reference_name": name,
    }).insert(ignore_permissions=True)

    # Tenta anche di registrare in webmail Mail (così appare in /mail)
    try:
        from mail.api.mail import create_mail as _mail_create
        from mail.utils.user import get_user_personal_account
        try:
            acct = get_user_personal_account(frappe.session.user) or f"{frappe.session.user}:{sender_email or frappe.session.user}"
        except Exception:
            acct = f"{frappe.session.user}:{sender_email or frappe.session.user}"
        _mail_create(account=acct, from_email=sender_email or frappe.session.user,
                     to=[{"email": recipients, "display_name": ""}], cc=[], bcc=[],
                     subject=subject, html_body=content,
                     attachments=[{"file_url": a.get("file_url"), "file_name": a.get("file_name","")} for a in atts] if atts else [],
                     save_as_draft=False)
    except Exception as _e:
        frappe.log_error(f"webmail mirror fail: {_e}", "send_email")

    sendmail_kwargs = dict(
        recipients=[recipients],
        subject=subject,
        message=content,
        reference_doctype=doctype,
        reference_name=name,
        communication=comm.name,
        attachments=atts,
        delayed=False,
    )
    if sender_email:
        sendmail_kwargs["sender"] = sender_email
    frappe.sendmail(**sendmail_kwargs)
    return {"ok": True, "communication": comm.name}


@frappe.whitelist()
def send_whatsapp(doctype: str, name: str, to: str, content: str,
                  template: str = None) -> dict:
    """Manda WhatsApp e aggancia al doc."""
    # Cerca/crea contact WABA
    contact = frappe.db.exists("WABA WhatsApp Contact", to)
    if not contact:
        c = frappe.get_doc({
            "doctype": "WABA WhatsApp Contact",
            "wa_id": to,
            "phone_number": to,
        }).insert(ignore_permissions=True)
        contact = c.name

    msg = frappe.get_doc({
        "doctype": "WABA WhatsApp Message",
        "to": to,
        "type": "Outgoing",
        "message_type": "text" if not template else "template",
        "message_body": content,
        "status": "Pending",
    })
    # Custom ref fields se presenti
    if frappe.db.has_column("WABA WhatsApp Message", "reference_doctype"):
        msg.reference_doctype = doctype
        msg.reference_name = name
    msg.insert(ignore_permissions=True)

    # Chiama l'API send esistente
    try:
        result = msg.send()
        return {"ok": True, "message": msg.name, "wa": result}
    except Exception as e:
        return {"ok": False, "error": str(e), "message": msg.name}


@frappe.whitelist()
def quick_links(doctype: str, name: str) -> dict:
    """Genera link rapidi pre-formattati per il doc (mandato, firma, pagamento, upload)."""
    base = frappe.utils.get_url()
    links = {}
    if doctype == "Agency Mandate":
        m = frappe.get_doc(doctype, name)
        last = frappe.db.sql("SELECT file_url FROM `tabFile` WHERE attached_to_doctype=%s AND attached_to_name=%s AND file_url LIKE %s ORDER BY creation DESC LIMIT 1", (doctype, name, "%%.pdf")); links["pdf"] = (base + last[0][0]) if last else ""
        links["sign"] = base + f"/sign/{name}"  # placeholder
        # Find linked proforma + stripe
        pf = frappe.db.sql("SELECT name, stripe_session FROM `tabDiplomatic Proforma` WHERE mandate=%s ORDER BY creation DESC LIMIT 1", (name,), as_dict=1)
        if pf:
            links["payment"] = pf[0].stripe_session or f"{base}/portal/pay/{pf[0].name}"
            links["proforma"] = f"{base}/app/diplomatic-proforma/{pf[0].name}"
    return links


# ----------- DUAL MANDATE ---------------------------------------------------
@frappe.whitelist()
def create_paired_mandate(name: str) -> str:
    src = frappe.get_doc("Agency Mandate", name)
    if getattr(src, "paired_mandate", None):
        return src.paired_mandate
    cm = frappe.copy_doc(src)
    cm.mandate_kind = "Commercial"
    cm.subject_matter = (src.subject_matter or "") + " — Versione commerciale per fatturazione (causale neutra)"
    cm.fee_total = src.fee_total
    cm.status = "Draft"
    cm.paired_mandate = src.name
    cm.mandate_pdf = None
    cm.signed_on = None
    cm.insert(ignore_permissions=True)
    src.db_set("paired_mandate", cm.name)
    frappe.db.commit()
    return cm.name


# ----------- TIMELINE -------------------------------------------------------
DDD_STEPS = [
    ("Draft","Bozza iniziale"),
    ("Questionnaire Pending","Questionario al cliente"),
    ("KYC Pending","Verifica identità (KYC)"),
    ("KYB Pending","Verifica azienda (KYB)"),
    ("Video Identification Pending","Identificazione video"),
    ("Document Review","Revisione documenti"),
    ("OSINT Review","OSINT e fonti aperte"),
    ("Compliance Review","Compliance/AML"),
    ("Legal Review","Revisione legale"),
    ("Mandate Pending Signature","Mandato in firma"),
    ("Payment Step 1 Pending","Acconto in attesa"),
    ("Investigation Active","Investigazione attiva"),
    ("Dossier Preparation","Preparazione dossier"),
    ("Director Review","Revisione direttore"),
    ("Approved for Submission","Approvato per invio"),
    ("Submitted to Authority","Inviato all\'autorità"),
    ("Awaiting Authority Response","In attesa decisione"),
    ("Closed","Chiusa"),
]


@frappe.whitelist()
def get_timeline(doctype: str, name: str) -> dict:
    doc = frappe.get_doc(doctype, name)
    current = getattr(doc, "workflow_state", None) or getattr(doc, "status", None) or "Draft"
    steps = DDD_STEPS if doctype == "Diplomatic Eligibility Case" else [
        ("Open","Aperta"),("In Progress","In lavorazione"),
        ("Awaiting Client","In attesa cliente"),("Closed","Chiusa"),
    ]
    out = []
    found = False
    for k, label in steps:
        if k == current:
            state = "current"; found = True
        elif not found:
            state = "done"
        else:
            state = "todo"
        out.append({"key": k, "label": label, "state": state})

    # Next actions concrete
    next_actions = []
    if doctype == "Diplomatic Eligibility Case":
        if current == "KYC Pending":
            next_actions.append("Caricare 4 fototessere ICAO 35x45 sfondo bianco")
            next_actions.append("Verificare documento identità in corso di validità")
        if current == "Mandate Pending Signature":
            next_actions.append("Inviare mandato per firma elettronica via mmos_sign")
        if current == "Payment Step 1 Pending":
            next_actions.append("Verificare incasso acconto entro 72h (pena risoluzione)")
        if current == "Submitted to Authority":
            next_actions.append("Follow-up con autorità ogni 5 giorni")

    return {"steps": out, "current": current, "next_actions": next_actions}


# ----------- AI SUGGEST -----------------------------------------------------
@frappe.whitelist()
def ai_suggest(doctype: str, name: str) -> dict:
    import requests
    gw = (frappe.conf.get("mmos_ai_gateway_url") or frappe.conf.get("ai_gateway_url") or "http://10.10.0.4:8800").rstrip("/")
    key = frappe.conf.get("mmos_ai_gateway_key") or frappe.conf.get("ai_gateway_key") or ""
    doc = frappe.get_doc(doctype, name).as_dict()
    # Campi essenziali (limita payload + token)
    SKIP = {"docstatus","idx","owner","modified","creation","modified_by","_user_tags","_comments","_assign","_liked_by","mandate_body","content","description","html_body","message_body","summary","decision_notes","mandate_pdf","source_pdf","signed_pdf"}
    keep = {}
    for k, v in doc.items():
        if k.startswith("_") or k in SKIP: continue
        if isinstance(v, (list, dict)): continue
        if v is None or v == "": continue
        sval = str(v)
        if len(sval) > 200: sval = sval[:200]+"…"
        keep[k] = sval
    message = (
        f"Sei un assistente Thanatos Intel. Analizza il seguente documento "
        f"{doctype}/{name} e suggerisci 3 azioni operative concrete e prioritizzate "
        f"per portare avanti la pratica. Rispondi in italiano, formato lista puntata.\n\n"
        f"DOC: {keep}"
    )
    try:
        r = requests.post(f"{gw}/chat",
                          json={"message": message},
                          headers={"X-MMOS-AI-KEY": key, "Content-Type": "application/json"} if key else {},
                          timeout=60)
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "text": data.get("reply") or data.get("text") or data.get("response") or str(data),
                    "model": data.get("model"), "engine": data.get("engine")}
        return {"ok": False, "error": f"AI gateway HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"AI gateway irraggiungibile: {e}"}


# ----------- SENDER SELECTION -----------------------------------------------
@frappe.whitelist()
def get_senders() -> list:
    """Ritorna lista di mittenti email disponibili (Email Account outgoing)."""
    accounts = frappe.db.sql("""
        SELECT name, email_id, email_account_name, default_outgoing
        FROM `tabEmail Account`
        WHERE enable_outgoing=1
        ORDER BY default_outgoing DESC, email_id
    """, as_dict=1)
    out = []
    for a in accounts:
        out.append({
            "value": a.email_id,
            "label": f"{a.email_account_name} <{a.email_id}>" + (" ⭐" if a.default_outgoing else ""),
            "account_name": a.name,
            "default": bool(a.default_outgoing),
        })
    return out


@frappe.whitelist()
def get_wa_senders() -> list:
    """Ritorna lista numeri WhatsApp configurati."""
    try:
        rows = frappe.db.sql("""
            SELECT name, phone_number, display_name
            FROM `tabWhatsApp Number`
            ORDER BY phone_number
        """, as_dict=1)
        return [{"value": r.phone_number, "label": f"{r.display_name or r.name} <{r.phone_number}>"} for r in rows]
    except Exception:
        return []


# ----------- RECIPIENT AUTOCOMPLETE -----------------------------------------
@frappe.whitelist()
def search_recipients(query: str = "", channel: str = "email", limit: int = 20) -> list:
    """Cerca destinatari (email o telefono) tra Contact / Customer / Applicant / User / Lead."""
    if not query: query = ""
    q = f"%{query.strip()}%"
    out = []
    seen = set()
    if channel == "email":
        # Contact
        for r in frappe.db.sql("""SELECT c.email_id, c.first_name, c.last_name, c.name
            FROM `tabContact` c WHERE c.email_id IS NOT NULL AND c.email_id != ''
            AND (c.email_id LIKE %s OR c.full_name LIKE %s OR c.first_name LIKE %s)
            LIMIT %s""", (q, q, q, limit), as_dict=1):
            if r.email_id and r.email_id not in seen:
                seen.add(r.email_id)
                full = (f"{r.first_name or ''} {r.last_name or ''}".strip() or r.name)
                out.append({"value": r.email_id, "label": f"{full} <{r.email_id}>", "source": "Contact"})
        # Customer (email field)
        for r in frappe.db.sql("""SELECT name, customer_name, email_id FROM `tabCustomer`
            WHERE email_id IS NOT NULL AND email_id != ''
            AND (email_id LIKE %s OR customer_name LIKE %s) LIMIT %s""", (q, q, limit), as_dict=1):
            if r.email_id and r.email_id not in seen:
                seen.add(r.email_id)
                out.append({"value": r.email_id, "label": f"{r.customer_name} <{r.email_id}>", "source": "Customer"})
        # Applicant Profile
        for r in frappe.db.sql("""SELECT name, full_legal_name, email FROM `tabApplicant Profile`
            WHERE email IS NOT NULL AND email != ''
            AND (email LIKE %s OR full_legal_name LIKE %s) LIMIT %s""", (q, q, limit), as_dict=1):
            if r.email and r.email not in seen:
                seen.add(r.email)
                out.append({"value": r.email, "label": f"{r.full_legal_name} <{r.email}>", "source": "Applicant"})
        # User
        for r in frappe.db.sql("""SELECT name, full_name FROM `tabUser`
            WHERE enabled=1 AND name != 'Administrator' AND name != 'Guest'
            AND (name LIKE %s OR full_name LIKE %s) LIMIT %s""", (q, q, limit), as_dict=1):
            if r.name not in seen:
                seen.add(r.name)
                out.append({"value": r.name, "label": f"{r.full_name or r.name} <{r.name}>", "source": "User"})
    else:
        # WhatsApp / telefono
        for r in frappe.db.sql("""SELECT name, full_name, mobile_no FROM `tabContact`
            WHERE mobile_no IS NOT NULL AND mobile_no != ''
            AND (mobile_no LIKE %s OR full_name LIKE %s) LIMIT %s""", (q, q, limit), as_dict=1):
            if r.mobile_no and r.mobile_no not in seen:
                seen.add(r.mobile_no)
                out.append({"value": r.mobile_no, "label": f"{r.full_name or r.name} {r.mobile_no}", "source": "Contact"})
        for r in frappe.db.sql("""SELECT name, full_legal_name, phone FROM `tabApplicant Profile`
            WHERE phone IS NOT NULL AND phone != ''
            AND (phone LIKE %s OR full_legal_name LIKE %s) LIMIT %s""", (q, q, limit), as_dict=1):
            if r.phone and r.phone not in seen:
                seen.add(r.phone)
                out.append({"value": r.phone, "label": f"{r.full_legal_name} {r.phone}", "source": "Applicant"})
    return out[:limit]


# ----------- TRADUZIONE GENERICA + MULTI-LINGUA -----------------------------
@frappe.whitelist()
def translate_doc_pdf(doctype: str, name: str, target_lang: str = "en") -> dict:
    """Traduce qualsiasi documento via Print Format del DocType + LibreTranslate.
    Per Agency Mandate/Diplomatic Proforma delega ai loro handler specifici.
    Per Signature Request: traduce il source_pdf via copy-source PDF + nuova anteprima Print Format del doc referenziato.
    """
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request as WzRequest
    from frappe.utils.pdf import get_pdf
    from frappe.utils.file_manager import save_file
    import frappe as _f
    src_lang = _f.conf.get("mandate_source_lang") or "it"
    if target_lang == src_lang:
        return {"ok": False, "error": "stessa lingua origine"}

    # Delegate ai handler specifici dove esistono
    if doctype == "Agency Mandate":
        from thanatos_intel.api.translate import translate_mandate_pdf
        return translate_mandate_pdf(name, target_lang)
    if doctype == "Diplomatic Proforma":
        from thanatos_intel.api.translate import translate_proforma_pdf
        return translate_proforma_pdf(name, target_lang)

    # Signature Request → traduci il doc referenziato e aggiorna source_pdf
    if doctype == "Signature Request":
        sr = frappe.get_doc("Signature Request", name)
        if not sr.reference_doctype or not sr.reference_name:
            return {"ok": False, "error": "Signature Request senza reference"}
        sub = translate_doc_pdf(sr.reference_doctype, sr.reference_name, target_lang)
        if sub.get("ok"):
            # Aggiorna source PDF della Request al PDF tradotto
            frappe.db.set_value("Signature Request", name, "source_pdf", sub["file_url"])
            frappe.db.commit()
        return sub

    # Fallback generico: traduci campi testo principali via Print Format standard del DocType
    pf = frappe.db.get_value("Print Format", {"doc_type": doctype, "standard": "Yes"}, "name") or "Standard"
    try:
        builder = EnvironBuilder(method="GET", path="/printview")
        frappe.local.request = WzRequest(builder.get_environ())
        frappe.local.form_dict = frappe._dict()
        if not getattr(frappe.local, "session_obj", None):
            import frappe.sessions as _fsessions
            frappe.local.session_obj = _fsessions.Session(user="Administrator", resume=False)
        # NB: per ora HTML non tradotto (richiederebbe processing per DocType). Genera PDF in lingua originale.
        html = frappe.get_print(doctype, name, pf)
        from thanatos_intel.api.translate import translate_html as _th
        html_tr = _th(html, target=target_lang, source=src_lang)
        pdf = get_pdf(html_tr)
        fdoc = save_file(f"{name}_{target_lang}.pdf", pdf, doctype, name, is_private=1)
        return {"ok": True, "file_url": fdoc.file_url, "lang": target_lang}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def send_email_multilang(doctype: str, name: str, recipients: str, subject: str,
                          content: str, langs: str = "en", from_email: str = None) -> dict:
    """Manda lo stesso messaggio in più lingue (CSV: 'en,bg,ro')."""
    from thanatos_intel.api.translate import translate_html
    import frappe as _f
    src_lang = _f.conf.get("mandate_source_lang") or "it"
    if isinstance(langs, str):
        targets = [l.strip() for l in langs.split(",") if l.strip()]
    else:
        targets = list(langs)
    out = {"sent": [], "errors": []}
    for lang in targets:
        try:
            if lang == src_lang:
                tr_content = content
                tr_subject = subject
            else:
                tr_content = translate_html(content, target=lang, source=src_lang)
                from thanatos_intel.api.translate import translate as _t
                tr_subject = _t(subject, target=lang, source=src_lang)
            r = send_email(doctype, name, recipients=recipients,
                           subject=f"[{lang.upper()}] {tr_subject}",
                           content=tr_content, from_email=from_email)
            out["sent"].append({"lang": lang, "ok": r.get("ok"), "communication": r.get("communication")})
        except Exception as e:
            out["errors"].append({"lang": lang, "error": str(e)})
    return out


# ----------- DOSSIER COMPLETO MULTI-LINGUA ----------------------------------
@frappe.whitelist()
def send_dossier_email(case_name: str = None, mandate_name: str = None,
                       recipient: str = None, langs: str = "it,en",
                       from_email: str = None, send: int = 0) -> dict:
    """Compone mail dossier con tutti i PDF (mandati + proforme + ddd) in N lingue
    e crea bozze Communication (send=1 per invio immediato).

    Identifica i doc collegati a partire da case_name (Investigation Case) o
    direttamente mandate_name (Agency Mandate). Per ognuno genera PDF nelle
    lingue richieste e li allega alla Communication.
    """
    import frappe as _f
    from thanatos_intel.api.translate import translate_mandate_pdf, translate_proforma_pdf, translate_html, translate as _t

    # Risolvi anchor doc
    if case_name:
        anchor_dt, anchor_name = "Investigation Case", case_name
    elif mandate_name:
        anchor_dt, anchor_name = "Agency Mandate", mandate_name
    else:
        return {"ok": False, "error": "case_name o mandate_name richiesto"}

    # Trova mandati collegati
    mandates = []
    proforme = []
    ddd_cases = set()
    if case_name:
        for m in frappe.db.sql("SELECT name FROM `tabAgency Mandate` WHERE investigation_case=%s AND status!='Terminated'", (case_name,), as_dict=1):
            mandates.append(m.name)
            md = frappe.get_doc("Agency Mandate", m.name)
            if md.ddd_case: ddd_cases.add(md.ddd_case)
    if mandate_name:
        mandates.append(mandate_name)
        md = frappe.get_doc("Agency Mandate", mandate_name)
        if md.ddd_case: ddd_cases.add(md.ddd_case)
        # Aggiungi mandato gemello
        if md.paired_mandate: mandates.append(md.paired_mandate)

    for m in mandates:
        for p in frappe.db.sql("SELECT name FROM `tabDiplomatic Proforma` WHERE mandate=%s AND status!='Void'", (m,), as_dict=1):
            proforme.append(p.name)

    # Lang list
    lang_list = [l.strip() for l in langs.split(",") if l.strip()]
    src_lang = _f.conf.get("mandate_source_lang") or "it"

    # Genera PDF per ogni doc in ogni lingua
    pdf_paths = []  # [{"label": "Mandato A (IT)", "url": "/private/..."}]
    for m in mandates:
        m_doc = frappe.get_doc("Agency Mandate", m)
        for lang in lang_list:
            if lang == src_lang:
                # Cerca ultimo PDF italiano
                last = frappe.db.sql("""SELECT file_url FROM `tabFile`
                    WHERE attached_to_doctype='Agency Mandate' AND attached_to_name=%s
                    AND file_url LIKE %s ORDER BY creation DESC LIMIT 1""",
                    (m, "%.pdf"))
                if last: pdf_paths.append({"label": f"Mandato {m} ({lang.upper()})", "url": last[0][0]})
            else:
                r = translate_mandate_pdf(m, lang)
                if r.get("ok"): pdf_paths.append({"label": f"Mandato {m} ({lang.upper()})", "url": r["file_url"]})
    for p in proforme:
        for lang in lang_list:
            if lang == src_lang:
                last = frappe.db.sql("""SELECT file_url FROM `tabFile`
                    WHERE attached_to_doctype='Diplomatic Proforma' AND attached_to_name=%s
                    AND file_url LIKE %s ORDER BY creation DESC LIMIT 1""",
                    (p, "%.pdf"))
                if last: pdf_paths.append({"label": f"Proforma {p} ({lang.upper()})", "url": last[0][0]})
            else:
                r = translate_proforma_pdf(p, lang)
                if r.get("ok"): pdf_paths.append({"label": f"Proforma {p} ({lang.upper()})", "url": r["file_url"]})

    # Trova Signature Requests + token per ogni firmatario "esterno" (gestione@petterson)
    base = frappe.utils.get_url()
    sign_links = []
    for m in mandates:
        for sr in frappe.db.sql("""SELECT name FROM `tabSignature Request`
            WHERE reference_doctype='Agency Mandate' AND reference_name=%s
            AND status IN ('Draft','Sent','Partially Signed')""", (m,), as_dict=1):
            sr_doc = frappe.get_doc("Signature Request", sr.name)
            # Trova token del primo signer non firmato
            tok = None
            sname = None
            if sr_doc.signing_mode == "Sequential" and sr_doc.signers:
                for s in sr_doc.signers:
                    if s.status != "Signed":
                        tok = s.token; sname = s.signer_name; break
            else:
                tok = sr_doc.token; sname = sr_doc.signer_name
            if tok:
                sign_links.append({"label": f"Firma {sr.name} ({sname})", "url": f"{base}/sign?token={tok}", "mandate": m})
    # Anche le SR di accettazione proforma
    for p in proforme:
        for sr in frappe.db.sql("""SELECT name FROM `tabSignature Request`
            WHERE reference_doctype='Diplomatic Proforma' AND reference_name=%s
            AND status='Draft'""", (p,), as_dict=1):
            sr_doc = frappe.get_doc("Signature Request", sr.name)
            tok = sr_doc.token
            if tok:
                sign_links.append({"label": f"Accettazione {p}", "url": f"{base}/sign?token={tok}", "mandate": None})

    # HTML IT body
    pdf_list_html = "".join(f'<li>📎 <b>{x["label"]}</b><br><small><a href="{base}{x["url"]}">{base}{x["url"]}</a></small></li>' for x in pdf_paths)
    sign_list_html = "".join(f'<li>🖊 <b>{x["label"]}</b><br><a href="{x["url"]}">{x["url"]}</a></li>' for x in sign_links)
    body_it = f"""
<p>Gentile Sig. Foglio,</p>

<p>in seguito ai nostri accordi, le inviamo il <b>dossier completo</b> per la pratica
<b>Due Diligence Diplomatica – Repubblica di Bulgaria</b> a Suo favore, e per il
<b>mandato quadro Report Africa</b> intestato a Petterson Holding UK Ltd.</p>

<h3>📜 Mandati</h3>
<ul>
<li><b>Mandato A — DDD Bulgaria</b> (€ 50.000,00 totali · acconto € 25.000,00 entro 72 ore dalla firma · saldo alla consegna del passaporto diplomatico)</li>
<li><b>Mandato B — Quadro Report Africa</b> (a consumo secondo listino allegato)</li>
</ul>

<h3>💶 Articolazione pagamenti DDD Bulgaria</h3>
<table style="border-collapse:collapse;width:100%">
<tr style="background:#f5f5f5"><th style="border:1px solid #ddd;padding:6px">Tranche</th><th style="border:1px solid #ddd;padding:6px">Importo</th><th style="border:1px solid #ddd;padding:6px">Scadenza</th><th style="border:1px solid #ddd;padding:6px">Emittente fattura</th></tr>
<tr><td style="border:1px solid #ddd;padding:6px"><b>Acconto</b></td><td style="border:1px solid #ddd;padding:6px"><b>€ 25.000,00</b></td><td style="border:1px solid #ddd;padding:6px">Entro 72 ore dalla firma</td><td style="border:1px solid #ddd;padding:6px">ARES Investigazioni S.r.l.</td></tr>
<tr><td style="border:1px solid #ddd;padding:6px">Saldo</td><td style="border:1px solid #ddd;padding:6px">€ 25.000,00</td><td style="border:1px solid #ddd;padding:6px">Alla consegna del passaporto</td><td style="border:1px solid #ddd;padding:6px">ARES Investigazioni S.r.l.</td></tr>
</table>

<h3>📦 Pacchetto documentale bulgaro</h3>
<ul>
<li>Passaporto diplomatico bulgaro a <b>durata illimitata</b></li>
<li>Carta d'identità diplomatica</li>
<li>Patente di guida bulgara</li>
<li>Targhe diplomatiche (CD) per autoveicolo</li>
<li>Documenti accessori (libretto di circolazione, codice fiscale bulgaro/EGN, registrazione domicilio)</li>
</ul>
<p><b>Stato di avanzamento:</b> la prima fase istruttoria è stata completata.
Per il perfezionamento restano da consegnare esclusivamente <b>n. 4 fototessere</b>
formato 35×45 mm, sfondo bianco, standard ICAO.</p>

<h3 style="color:#a00">⚠ Clausola risolutiva — 72 ore</h3>
<p style="background:#fff7f7;border-left:4px solid #a00;padding:10px">
Il mancato versamento dell'acconto di € 25.000,00 entro 72 ore dalla sottoscrizione
comporta la risoluzione automatica del mandato ai sensi dell'art. 1456 c.c., con
iscrizione del Mandante nella <b>Blacklist Thanatos Intel</b> e segnalazione ai
partner di rete.
</p>

<h3>🖊 Link per la firma elettronica avanzata (AdES + OTP)</h3>
<ul>{sign_list_html}</ul>
<p>Ordine sequenziale: Foglio (persona fisica) → Petterson Holding (CEO) → ARES → Thanatos.
La firma successiva è abilitata automaticamente dopo il completamento della precedente.</p>

<h3>📎 Documenti allegati / link diretti</h3>
<ul>{pdf_list_html}</ul>

<h3>Struttura del mandato</h3>
<p>Il mandato è conferito a <b>Thanatos Investigazioni S.r.l.</b> (mandataria capofila — direzione e responsabilità).
In sub-mandato espressamente autorizzato opera <b>ARES Investigazioni S.r.l.</b> (esecuzione materiale + emissione fatture
direttamente a Petterson Holding UK Ltd).</p>

<h3>Prossimi passi</h3>
<ol>
<li>Firma del Mandato A (4 firmatari sequenziali)</li>
<li>Versamento acconto € 25.000 entro 72 ore (link Stripe nella proforma allegata)</li>
<li>Invio delle 4 fototessere ICAO</li>
<li>Avvio operativo presso le competenti Autorità della Repubblica di Bulgaria</li>
</ol>

<p>Restiamo a disposizione per ogni chiarimento.</p>
<p>Cordialmente,<br>
<b>THANATOS INVESTIGAZIONI S.R.L.</b><br>
Str. Baba Novac 185, 900366 Constanța, România<br>
admin@thanatos.agency · <a href="https://thanatos.agency">thanatos.agency</a><br>
<small>Fatturazione operativa: ARES Investigazioni S.R.L. — Voghera (PV)</small></p>
"""

    # Traduzione EN
    body_en = translate_html(body_it, target="en", source="it")
    subject_it = "Dossier completo — DDD Bulgaria e Framework Africa | Mandati, proforme, link di firma"
    subject_en = _t(subject_it, target="en", source="it")

    # Componi mail bilingue (IT in alto + EN in basso)
    final_body = body_it + '<hr style="margin:30px 0;border:0;border-top:2px dashed #aaa"><p style="font-style:italic;color:#666">English version below — versione inglese di seguito</p><hr>' + body_en
    final_subject = f"{subject_it}  /  {subject_en}"

    # Crea Communication agganciata al case
    attachments_list = [{"file_url": x["url"]} for x in pdf_paths]
    comm = frappe.get_doc({
        "doctype": "Communication",
        "communication_type": "Communication",
        "communication_medium": "Email",
        "sent_or_received": "Sent" if int(send) else "Sent",  # mark as sent in either case once dispatched
        "subject": final_subject,
        "content": final_body,
        "sender": from_email or "admin@thanatos.agency",
        "recipients": recipient,
        "status": "Linked",
        "reference_doctype": anchor_dt,
        "reference_name": anchor_name,
    }).insert(ignore_permissions=True)

    if int(send):
        ea_name = frappe.db.get_value("Email Account", {"email_id": from_email}, "name") if from_email else None
        # Tenta anche di registrare in webmail Mail (così appare in /mail)
    try:
        from mail.api.mail import create_mail as _mail_create
        from mail.utils.user import get_user_personal_account
        try:
            acct = get_user_personal_account(frappe.session.user) or f"{frappe.session.user}:{sender_email or frappe.session.user}"
        except Exception:
            acct = f"{frappe.session.user}:{sender_email or frappe.session.user}"
        _mail_create(account=acct, from_email=sender_email or frappe.session.user,
                     to=[{"email": recipients, "display_name": ""}], cc=[], bcc=[],
                     subject=subject, html_body=content,
                     attachments=[{"file_url": a.get("file_url"), "file_name": a.get("file_name","")} for a in atts] if atts else [],
                     save_as_draft=False)
    except Exception as _e:
        frappe.log_error(f"webmail mirror fail: {_e}", "send_email")

    sendmail_kwargs = dict(
            recipients=[recipient],
            subject=final_subject,
            message=final_body,
            reference_doctype=anchor_dt,
            reference_name=anchor_name,
            communication=comm.name,
            attachments=attachments_list,
            delayed=False,
        )
        if from_email:
            sendmail_kwargs["sender"] = from_email
        try:
            frappe.sendmail(**sendmail_kwargs)
            return {"ok": True, "sent": True, "communication": comm.name, "pdf_count": len(pdf_paths), "sign_links": len(sign_links)}
        except Exception as e:
            return {"ok": False, "error": str(e), "communication": comm.name}
    else:
        return {"ok": True, "draft": True, "communication": comm.name,
                "pdf_count": len(pdf_paths), "sign_links": len(sign_links),
                "subject": final_subject}


# ----------- WEBMAIL: lista conversazioni unificate -----------------------
@frappe.whitelist()
def list_conversations(limit: int = 200) -> list:
    """Lista conversazioni grouped per indirizzo (email/telefono)."""
    convs = {}
    # Email Communications
    rows = frappe.db.sql("""
        SELECT name, communication_date, sender, recipients, subject, content,
               sent_or_received, reference_doctype, reference_name, status,
               communication_medium
        FROM `tabCommunication`
        WHERE communication_medium='Email'
        ORDER BY communication_date DESC
        LIMIT %s
    """, (limit,), as_dict=1)
    for r in rows:
        addr = (r.sender if r.sent_or_received == "Received" else (r.recipients or "").split(",")[0]).strip()
        if not addr: continue
        key = f"email::{addr.lower()}"
        if key not in convs:
            convs[key] = {"key": key, "channel": "email", "icon": "📧", "addr": addr, "who": addr,
                          "count": 0, "unread": 0, "ts": None, "snippet": "", "ref_doctype": r.reference_doctype, "ref_name": r.reference_name}
        c = convs[key]
        c["count"] += 1
        if r.sent_or_received == "Received" and r.status != "Read":
            c["unread"] += 1
        if not c["ts"] or str(r.communication_date) > str(c["ts"]):
            c["ts"] = str(r.communication_date)
            c["snippet"] = (r.subject or "")[:80]
    # WhatsApp
    try:
        wa_has_ref = frappe.db.has_column("WABA WhatsApp Message", "reference_doctype")
        rows = frappe.db.sql("""
            SELECT name, creation, `from`, `to`, type, message_body, status
            FROM `tabWABA WhatsApp Message`
            ORDER BY creation DESC LIMIT %s
        """, (limit,), as_dict=1)
        for r in rows:
            addr = (r["from"] if r.type == "Incoming" else r["to"]) or ""
            if not addr: continue
            key = f"wa::{addr}"
            if key not in convs:
                convs[key] = {"key": key, "channel": "whatsapp", "icon": "💬", "addr": addr, "who": addr,
                              "count": 0, "unread": 0, "ts": None, "snippet": ""}
            c = convs[key]
            c["count"] += 1
            if r.type == "Incoming" and r.status != "Read":
                c["unread"] += 1
            if not c["ts"] or str(r.creation) > str(c["ts"]):
                c["ts"] = str(r.creation)
                c["snippet"] = (r.message_body or "")[:80]
    except Exception:
        pass
    # Risolvi who → nome reale via lookup
    for key, c in convs.items():
        if c["channel"] == "email":
            for table, fld_name, fld_addr in (
                ("Contact", "full_name", "email_id"),
                ("Customer", "customer_name", "email_id"),
                ("Applicant Profile", "full_legal_name", "email"),
            ):
                nm = frappe.db.get_value(table, {fld_addr: c["addr"]}, fld_name)
                if nm:
                    c["who"] = f"{nm}"
                    break
    out = sorted(convs.values(), key=lambda x: x["ts"] or "", reverse=True)
    return out


@frappe.whitelist()
def conversation_thread(key: str) -> dict:
    """Ritorna tutti i messaggi di una conversazione (email o WA)."""
    if "::" not in key: return {"info": {}, "messages": []}
    ch, addr = key.split("::", 1)
    info = {"addr": addr, "who": addr}
    msgs = []
    if ch == "email":
        rows = frappe.db.sql("""
            SELECT name, communication_date, sender, recipients, subject, content,
                   sent_or_received, reference_doctype, reference_name, status
            FROM `tabCommunication`
            WHERE communication_medium='Email'
            AND (LOWER(sender) LIKE %s OR LOWER(recipients) LIKE %s)
            ORDER BY communication_date ASC LIMIT 500
        """, (f"%{addr.lower()}%", f"%{addr.lower()}%"), as_dict=1)
        for r in rows:
            msgs.append({
                "channel": "email",
                "direction": "in" if r.sent_or_received == "Received" else "out",
                "ts": str(r.communication_date),
                "subject": r.subject,
                "text": r.content,
                "status": r.status,
            })
        if msgs:
            info["ref_doctype"] = rows[-1].reference_doctype
            info["ref_name"] = rows[-1].reference_name
    else:
        try:
            rows = frappe.db.sql("""
                SELECT name, creation, `from`, `to`, type, message_body, status
                FROM `tabWABA WhatsApp Message`
                WHERE `from`=%s OR `to`=%s
                ORDER BY creation ASC LIMIT 500
            """, (addr, addr), as_dict=1)
            for r in rows:
                msgs.append({
                    "channel": "whatsapp",
                    "direction": "in" if r.type == "Incoming" else "out",
                    "ts": str(r.creation),
                    "text": r.message_body,
                    "status": r.status,
                })
        except Exception:
            pass
    # Resolve nome
    for table, fld_name, fld_addr in (
        ("Contact", "full_name", "email_id"),
        ("Customer", "customer_name", "email_id"),
        ("Applicant Profile", "full_legal_name", "email"),
    ):
        nm = frappe.db.get_value(table, {fld_addr: addr}, fld_name)
        if nm:
            info["who"] = nm
            break
    return {"info": info, "messages": msgs}
