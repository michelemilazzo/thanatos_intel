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


@frappe.whitelist()
def send_email(doctype: str, name: str, recipients: str, subject: str,
               content: str, template: str = None, attachments: str = None) -> dict:
    """Manda email e aggancia al doc."""
    if template:
        et = frappe.get_doc("Email Template", template)
        ctx = frappe.get_doc(doctype, name).as_dict()
        subject = frappe.render_template(et.subject, ctx)
        content = frappe.render_template(et.response_html or et.response or "", ctx)

    atts = json.loads(attachments) if attachments and isinstance(attachments, str) else (attachments or [])

    comm = frappe.get_doc({
        "doctype": "Communication",
        "communication_type": "Communication",
        "communication_medium": "Email",
        "sent_or_received": "Sent",
        "subject": subject,
        "content": content,
        "sender": frappe.session.user,
        "recipients": recipients,
        "status": "Linked",
        "reference_doctype": doctype,
        "reference_name": name,
    }).insert(ignore_permissions=True)

    frappe.sendmail(
        recipients=[recipients],
        subject=subject,
        message=content,
        reference_doctype=doctype,
        reference_name=name,
        communication=comm.name,
        attachments=atts,
        delayed=False,
    )
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
    gw = frappe.conf.get("ai_gateway_url") or "http://10.10.0.4:8800"
    key = frappe.conf.get("ai_gateway_key") or ""
    doc = frappe.get_doc(doctype, name).as_dict()
    keep = {k: v for k, v in doc.items() if not k.startswith("_") and not isinstance(v, list)}
    prompt = (
        f"Sei un assistente Thanatos Intel. Analizza il seguente documento "
        f"{doctype}/{name} e suggerisci 3 azioni operative concrete e prioritizzate "
        f"per portare avanti la pratica. Rispondi in italiano, formato lista puntata.\n\n"
        f"DOC: {keep}"
    )
    try:
        r = requests.post(f"{gw}/v1/chat", json={"prompt": prompt, "max_tokens": 600},
                          headers={"Authorization": f"Bearer {key}"} if key else {},
                          timeout=20)
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "text": data.get("text") or data.get("response") or str(data)}
        return {"ok": False, "error": f"AI gateway HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": f"AI gateway irraggiungibile: {e}"}
