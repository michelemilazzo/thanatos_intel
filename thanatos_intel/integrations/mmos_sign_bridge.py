# -*- coding: utf-8 -*-
"""Bridge mmos_sign ↔ thanatos_intel.

- `on_signature_signed`: hook on_update su Signature Request; quando la firma è
  completata (status=Signed) crea un Investigation Evidence (catena di custodia)
  dal PDF firmato + un Consent Record (base giuridica «Contratto»/mandato).
- `send_case_mandate`: crea un Agency Mandate di raccolta/trattamento documenti
  per una pratica e lo manda in firma al cliente (mmos_sign, firma dal portale).
  È la "delega" corretta: NON usa lo SPID del cliente, è un mandato firmato.
"""
import frappe
from frappe.utils import now_datetime, nowdate


def _case_of_signature(doc):
    ref_dt = doc.get("reference_doctype")
    ref_nm = doc.get("reference_name")
    if ref_dt == "Investigation Case":
        return ref_nm
    if ref_dt == "Agency Mandate" and ref_nm:
        return frappe.db.get_value("Agency Mandate", ref_nm, "investigation_case")
    return None


def on_signature_signed(doc, method=None):
    """Alla firma completata: PDF firmato -> reperto in custodia + consenso."""
    try:
        if doc.get("status") != "Signed":
            return
        prev = doc.get_doc_before_save()
        if prev and prev.get("status") == "Signed":
            return  # già gestito
        signed = doc.get("signed_pdf")
        if not signed:
            return
        case = _case_of_signature(doc)
        if not case:
            return
        # evita duplicati (stessa firma già trasformata in reperto)
        if frappe.db.exists("Investigation Evidence",
                            {"investigation_case": case, "attached_file": signed}):
            return

        label = doc.get("reference_name") or doc.name
        ev = frappe.get_doc({
            "doctype": "Investigation Evidence",
            "investigation_case": case,
            "evidence_name": f"Documento firmato — {label}",
            "evidence_type": "Document",
            "attached_file": signed,
            "hash_value": doc.get("signed_pdf_hash") or "",
            "custody_status": "Received",
            "source": f"mmos_sign firma ({doc.name})",
            "notes": (f"Documento firmato elettronicamente (PAdES) dal cliente via "
                      f"mmos_sign il {doc.get('signed_at') or now_datetime()}. "
                      f"Firmatario: {doc.get('signer_email')}."),
        })
        ev.insert(ignore_permissions=True)
        try:
            frappe.get_doc({
                "doctype": "Chain Of Custody Event", "event_type": "Created",
                "related_reference": ev.name,
                "notes": (f"Firma mmos_sign {doc.name} | SHA256="
                          f"{doc.get('signed_pdf_hash')} | firmatario={doc.get('signer_email')}"),
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "mmos_sign bridge coc")

        # Consent Record: base giuridica Contratto (mandato firmato)
        client = frappe.db.get_value("Investigation Case", case, "client")
        try:
            frappe.get_doc({
                "doctype": "Consent Record",
                "client": client,
                "data_subject": doc.get("signer_name") or doc.get("signer_email"),
                "email": doc.get("signer_email"),
                "purpose": f"Mandato/documento firmato per la pratica {case}"[:140],
                "legal_basis": "Contratto",
                "channel": "mmos_sign (firma elettronica PAdES)",
                "given_on": doc.get("signed_at") or now_datetime(),
                "evidence": signed,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "mmos_sign bridge consent")

        # aggiorna il mandato collegato
        if doc.get("reference_doctype") == "Agency Mandate" and doc.get("reference_name"):
            try:
                frappe.db.set_value("Agency Mandate", doc.reference_name,
                                    {"status": "Signed", "signed_on": nowdate()})
            except Exception:
                pass
        frappe.db.commit()

        # notifica operatore (email + WhatsApp)
        try:
            from thanatos_intel.workflow.notify import _email_operator
            _email_operator(case,
                            subject=f"[Thanatos] Mandato firmato dal cliente — {case}",
                            message=(f"Il cliente ha firmato il documento «{label}» "
                                     f"(reperto {ev.name}). Consenso registrato (mandato)."),
                            from_user="Administrator")
        except Exception:
            pass
        try:
            from thanatos_intel.ingest.wa_bot import notify_operators
            notify_operators(f"✍️ *Mandato firmato* dal cliente per la pratica {case} "
                             f"(reperto {ev.name}, in catena di custodia).")
        except Exception:
            pass
    except Exception:
        frappe.log_error(frappe.get_traceback(), "on_signature_signed")


_MANDATE_BODY = """<p>Il/La sottoscritto/a <b>{name}</b> conferisce a <b>Thanatos Intelligence
Agency</b> mandato, per la pratica <b>{case}</b>, ad acquisire, ricevere e trattare i
documenti e le informazioni da me forniti o da me stesso/a recuperati (anche tramite la
mia identità digitale SPID/CIE sui portali ufficiali degli enti) necessari allo
svolgimento dell'incarico.</p>
<p>Autorizzo in particolare: la raccolta e la verifica documentale, le ricerche su fonti
aperte (OSINT) e i controlli necessari, nei limiti di legge.</p>
<p>Il trattamento dei dati personali avviene per le sole finalità dell'incarico, nel
rispetto del Reg. UE 2016/679 (GDPR); ho diritto di accesso, rettifica, cancellazione e
opposizione. I documenti sono conservati in catena di custodia secondo la policy di
conservazione dell'Agenzia.</p>
<p><i>Il presente testo è un modello e può essere adeguato dall'Agenzia al caso concreto.</i></p>"""


@frappe.whitelist(methods=["POST"])
def send_case_mandate(case, subject_matter=None):
    """Crea un Agency Mandate di raccolta documenti per il caso e lo manda in firma
    al cliente (firma elettronica dal portale). Ritorna il link di firma."""
    if not frappe.db.exists("Investigation Case", case):
        frappe.throw("Pratica non trovata.")
    c = frappe.get_doc("Investigation Case", case)
    client = frappe.get_doc("Investigation Client", c.client) if c.client else None
    email = (client.email if client and client.get("email") else None)
    cname = (client.client_name if client else None) or "Cliente"
    if not email:
        return {"ok": False, "error": "Il cliente della pratica non ha un'email a cui inviare il mandato."}

    m = frappe.get_doc({
        "doctype": "Agency Mandate",
        "investigation_case": case,
        "applicant_name": cname,
        "subject_matter": subject_matter or f"Raccolta e trattamento documenti per la pratica {case}",
        "doc_verification_authorization": 1,
        "osint_authorization": 1,
        "governing_law": "Reg. UE 2016/679 (GDPR)",
        "status": "Draft",
        "mandate_body": _MANDATE_BODY.format(name=cname, case=case),
    })
    m.insert(ignore_permissions=True)

    # PDF del mandato
    try:
        from thanatos_intel.thanatos_ddd.pdf.mandate import generate as _gen
        _gen(m.name)
        m.reload()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "mandate pdf generate")

    # Signature Request con firmatario = email del cliente
    from mmos_sign import api as _ms
    req = frappe.new_doc("Signature Request")
    req.reference_doctype = "Agency Mandate"
    req.reference_name = m.name
    req.signing_mode = "Single"
    req.signer_email = email
    req.signer_name = cname
    try:
        req.signing_plan = "Advanced (AdES)"
    except Exception:
        pass
    req.insert(ignore_permissions=True)

    if m.get("mandate_pdf"):
        src = frappe.get_site_path("private", "files",
                                   m.mandate_pdf.split("/private/files/")[-1])
        with open(src, "rb") as f:
            pdf_bytes = f.read()
        fdoc = frappe.get_doc({
            "doctype": "File", "file_name": f"{req.name}_source.pdf",
            "attached_to_doctype": "Signature Request", "attached_to_name": req.name,
            "is_private": 1, "content": pdf_bytes,
        }).insert(ignore_permissions=True)
        req.db_set("source_pdf", fdoc.file_url, update_modified=False)
        frappe.db.commit()
        res = _ms.send_request(req.name)
    else:
        res = _ms.create_request_from_print(
            reference_doctype="Agency Mandate", reference_name=m.name,
            signer_email=email, signer_name=cname, send=True)

    sign_url = res.get("url")
    m.signature_ref = f"MMOSSign:{req.name}"
    m.status = "Pending Signature"
    m.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "mandate": m.name, "signature_request": req.name,
            "sign_url": sign_url, "client_email": email}
