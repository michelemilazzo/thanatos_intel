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
