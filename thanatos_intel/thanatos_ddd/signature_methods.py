"""Multi-method signature dispatcher per clienti globali.

Metodi supportati:
- SES       : Simple Electronic Signature (canvas + audit hash)   — UE
- SES_OTP   : SES + OTP SMS via Twilio                            — globale
- AES_PADES : PAdES B-B con cert X.509 self-issued (pyhanko)      — globale ISO 32000
- DOCUSIGN  : invio envelope DocuSign                              — globale (richiede DocuSign API key)
- ADOBE_SIGN: invio agreement Adobe Acrobat Sign                  — globale (richiede Adobe API)
- HELLOSIGN : invio Dropbox Sign request                          — globale (richiede HelloSign API)

L'utente sceglie il metodo a livello di Mandate/cliente. Provider esterni
configurati via site_config (DocuSign access_token, etc.).
"""
import os
import io
import json
import random
import hashlib
import datetime
import frappe
import requests
from frappe.utils import now_datetime


# ---------- OTP via Twilio (globale) ----------------------------------------
def _twilio_send_sms(to: str, body: str) -> dict:
    sid = frappe.conf.get("twilio_account_sid")
    token = frappe.conf.get("twilio_auth_token")
    fr = frappe.conf.get("twilio_from")
    if not (sid and token and fr):
        return {"sent": False, "error": "twilio_not_configured",
                "hint": "Set twilio_account_sid/auth_token/from in site_config"}
    try:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data={"From": fr, "To": to, "Body": body}, auth=(sid, token),
            timeout=15)
        r.raise_for_status()
        return {"sent": True, "sid": r.json().get("sid")}
    except Exception as e:
        return {"sent": False, "error": str(e)[:200]}


@frappe.whitelist(methods=["POST"])
def send_otp(mandate: str, phone: str = None) -> dict:
    m = frappe.get_doc("Agency Mandate", mandate)
    if not phone and m.applicant:
        phone = frappe.db.get_value("Applicant Profile", m.applicant, "phone")
    if not phone:
        frappe.throw("Numero telefono mancante")
    code = f"{random.randint(100000, 999999)}"
    frappe.cache().set_value(f"ddd:otp:{mandate}",
                             json.dumps({"code": code, "phone": phone}),
                             expires_in_sec=600)
    r = _twilio_send_sms(phone,
        f"Thanatos: codice firma mandato {mandate}: {code} (valido 10 min)")
    return {"otp_sent": r.get("sent"), "via": "twilio", "phone_masked": phone[:4]+"****"+phone[-2:],
            **({"error": r.get("error"), "hint": r.get("hint")} if not r.get("sent") else {})}


def verify_otp(mandate: str, code: str) -> bool:
    raw = frappe.cache().get_value(f"ddd:otp:{mandate}")
    if not raw:
        return False
    data = json.loads(raw)
    if data.get("code") == code:
        frappe.cache().delete_value(f"ddd:otp:{mandate}")
        return True
    return False


# ---------- AES PAdES via PyHanko ------------------------------------------
def _ensure_cert():
    """Genera (una sola volta) cert X.509 self-issued per Thanatos Signing."""
    cert_dir = frappe.get_site_path("private", "files", "ddd_certs")
    os.makedirs(cert_dir, exist_ok=True)
    p12_path = os.path.join(cert_dir, "thanatos_signing.p12")
    if os.path.exists(p12_path):
        return p12_path

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Thanatos Intel Signing CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OneKey Co."),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IT"),
    ])
    cert = (x509.CertificateBuilder()
            .subject_name(subj).issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow()
                             + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0),
                           critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=True,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))

    p12_bytes = pkcs12.serialize_key_and_certificates(
        name=b"thanatos-signing",
        key=key, cert=cert, cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(b"thanatos"))
    with open(p12_path, "wb") as f:
        f.write(p12_bytes)
    return p12_path


def sign_padded(mandate: str, signer_name: str, reason: str) -> dict:
    """PAdES B-B cryptographic signature via PyHanko."""
    from pyhanko.sign import signers, fields
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

    m = frappe.get_doc("Agency Mandate", mandate)
    if not m.mandate_pdf:
        frappe.throw("PDF mandato non disponibile")

    src = frappe.get_site_path("private", "files",
        m.mandate_pdf.split("/private/files/")[-1])
    p12 = _ensure_cert()
    signer = signers.SimpleSigner.load_pkcs12(pfx_file=p12, passphrase=b"thanatos")

    out_bytes = io.BytesIO()
    with open(src, "rb") as f:
        w = IncrementalPdfFileWriter(f)
        sig_meta = signers.PdfSignatureMetadata(
            field_name="ThanatosSignature1",
            reason=reason or "Mandato professionale",
            location="Thanatos Intel",
            name=signer_name,
            subfilter=fields.SigSeedSubFilter.PADES,
        )
        signers.sign_pdf(w, sig_meta, signer=signer, output=out_bytes)
    out_bytes.seek(0)
    out = out_bytes.getvalue()
    digest = hashlib.sha256(out).hexdigest()

    fdoc = frappe.get_doc({
        "doctype": "File", "file_name": f"{m.name}-PADES.pdf",
        "is_private": 1, "content": out,
        "attached_to_doctype": "Agency Mandate", "attached_to_name": m.name,
    })
    fdoc.save(ignore_permissions=True)
    m.mandate_pdf = fdoc.file_url
    m.status = "Signed"
    m.signed_on = frappe.utils.today()
    m.signature_ref = f"PAdES-B-B:{digest[:16]}"
    m.save(ignore_permissions=True)
    return {"method": "AES_PADES", "signed_pdf": fdoc.file_url,
            "sha256": digest, "level": "PAdES-B-B"}


# ---------- External provider stubs ----------------------------------------
def docusign_send(mandate: str) -> dict:
    """Invia envelope DocuSign. Richiede:
       site_config.docusign_access_token, docusign_account_id."""
    token = frappe.conf.get("docusign_access_token")
    acct = frappe.conf.get("docusign_account_id")
    if not (token and acct):
        return {"error": "docusign_not_configured",
                "hint": "site_config: docusign_access_token + docusign_account_id"}
    m = frappe.get_doc("Agency Mandate", mandate)
    src = frappe.get_site_path("private", "files",
        m.mandate_pdf.split("/private/files/")[-1])
    import base64
    with open(src, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    app = frappe.get_doc("Applicant Profile", m.applicant)
    envelope = {
        "emailSubject": f"Firma Mandato {m.name}",
        "documents": [{"documentBase64": b64, "name": f"{m.name}.pdf",
                       "fileExtension": "pdf", "documentId": "1"}],
        "recipients": {"signers": [{
            "email": app.email, "name": app.full_legal_name,
            "recipientId": "1", "routingOrder": "1",
            "tabs": {"signHereTabs": [{"documentId": "1", "pageNumber": "1",
                                       "xPosition": "100", "yPosition": "100"}]}
        }]},
        "status": "sent",
    }
    try:
        r = requests.post(
            f"https://demo.docusign.net/restapi/v2.1/accounts/{acct}/envelopes",
            headers={"Authorization": f"Bearer {token}"},
            json=envelope, timeout=30)
        r.raise_for_status()
        env_id = r.json().get("envelopeId")
        m.signature_ref = f"DocuSign:{env_id}"
        m.status = "Pending Signature"
        m.save(ignore_permissions=True)
        return {"method": "DOCUSIGN", "envelope_id": env_id, "status": "sent"}
    except Exception as e:
        return {"error": str(e)[:300]}


def adobe_sign_send(mandate: str) -> dict:
    """Invia agreement Adobe Acrobat Sign."""
    token = frappe.conf.get("adobe_sign_access_token")
    if not token:
        return {"error": "adobe_sign_not_configured",
                "hint": "site_config: adobe_sign_access_token + adobe_sign_base_uri"}
    return {"todo": "adobe_sign_send minimal envelope payload",
            "method": "ADOBE_SIGN", "configured": True}


def hellosign_send(mandate: str) -> dict:
    """Invia signature request via Dropbox Sign (HelloSign)."""
    key = frappe.conf.get("hellosign_api_key")
    if not key:
        return {"error": "hellosign_not_configured",
                "hint": "site_config: hellosign_api_key"}
    return {"todo": "hellosign_send minimal payload", "method": "HELLOSIGN",
            "configured": True}


# ---------- DocuSeal (17k⭐, single container, MIT) ------------------------
# Logica spostata in docuseal.py — queste funzioni sono stub di compatibilità.

@frappe.whitelist(allow_guest=True)
def fetch_mandate_pdf(mandate: str, token: str):
    """Compat shim → docuseal.serve_mandate_pdf."""
    from .docuseal import serve_mandate_pdf
    return serve_mandate_pdf(mandate, token)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def docuseal_webhook():
    """Compat shim → docuseal.webhook."""
    from .docuseal import webhook
    return webhook()


def docuseal_send(mandate: str) -> dict:
    """Compat shim → docuseal.send."""
    from .docuseal import send
    return send(mandate)


# ---------- Documenso (13k⭐, Next.js, supporta PAdES) ---------------------
def documenso_send(mandate: str) -> dict:
    base = frappe.conf.get("documenso_base_url")
    key = frappe.conf.get("documenso_api_key")
    if not (base and key):
        return {"error": "documenso_not_configured",
                "hint": "site_config: documenso_base_url + documenso_api_key"}
    m = frappe.get_doc("Agency Mandate", mandate)
    app = frappe.get_doc("Applicant Profile", m.applicant) if m.applicant else None
    if not app or not app.email:
        return {"error": "applicant_email_missing"}
    src = frappe.get_site_path("private", "files",
        m.mandate_pdf.split("/private/files/")[-1])
    try:
        # Step 1: upload document
        with open(src, "rb") as f:
            up = requests.post(f"{base}/api/v1/documents",
                files={"file": (f"{m.name}.pdf", f, "application/pdf")},
                headers={"Authorization": f"Bearer {key}"}, timeout=30)
        up.raise_for_status()
        doc_id = up.json().get("id")
        # Step 2: add recipient + send
        r = requests.post(f"{base}/api/v1/documents/{doc_id}/recipients",
            json={"name": app.full_legal_name, "email": app.email,
                  "role": "SIGNER"},
            headers={"Authorization": f"Bearer {key}"}, timeout=30)
        r.raise_for_status()
        s = requests.post(f"{base}/api/v1/documents/{doc_id}/send",
            headers={"Authorization": f"Bearer {key}"}, timeout=30)
        s.raise_for_status()
        m.signature_ref = f"Documenso:{doc_id}"
        m.status = "Pending Signature"
        m.save(ignore_permissions=True)
        return {"method": "DOCUMENSO", "document_id": doc_id, "status": "sent"}
    except Exception as e:
        return {"error": str(e)[:300], "method": "DOCUMENSO"}


# ---------- OpenSign vero (org opensign, 6.5k⭐ AGPL) ---------------------
def opensign_real_send(mandate: str) -> dict:
    base = frappe.conf.get("opensign_base_url")
    key = frappe.conf.get("opensign_api_key")
    if not (base and key):
        return {"error": "opensign_not_configured",
                "hint": "site_config: opensign_base_url + opensign_api_key. "
                        "Docker image: opensign/opensign + opensign/opensignserver"}
    m = frappe.get_doc("Agency Mandate", mandate)
    app = frappe.get_doc("Applicant Profile", m.applicant) if m.applicant else None
    if not app or not app.email:
        return {"error": "applicant_email_missing"}
    src = frappe.get_site_path("private", "files",
        m.mandate_pdf.split("/private/files/")[-1])
    import base64
    with open(src, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    try:
        r = requests.post(
            f"{base}/api/app/functions/savetemplate",
            json={"Name": f"Thanatos Mandate {m.name}",
                  "URL": f"data:application/pdf;base64,{b64}",
                  "Signers": [{"email": app.email,
                               "name": app.full_legal_name}]},
            headers={"X-Parse-Application-Id": "opensign",
                     "sessionToken": key},
            timeout=60)
        r.raise_for_status()
        tpl_id = r.json().get("objectId")
        m.signature_ref = f"OpenSign:{tpl_id}"
        m.status = "Pending Signature"
        m.save(ignore_permissions=True)
        return {"method": "OPENSIGN", "template_id": tpl_id, "status": "sent"}
    except Exception as e:
        return {"error": str(e)[:300], "method": "OPENSIGN"}


# ---------- LibreSign (Nextcloud app, AGPL OSS, cert ICP-Brasil + X.509) ----
def libresign_send(mandate: str) -> dict:
    """Crea sign request via LibreSign su Nextcloud self-hosted.

    Richiede in site_config:
      libresign_base_url   : es. https://nextcloud.thanatos.local
      libresign_user       : utente Nextcloud con cert installato
      libresign_app_token  : app-password Nextcloud (Settings > Security)
    """
    import base64
    base = frappe.conf.get("libresign_base_url")
    user = frappe.conf.get("libresign_user")
    token = frappe.conf.get("libresign_app_token")
    if not (base and user and token):
        return {"error": "libresign_not_configured",
                "hint": "site_config: libresign_base_url + libresign_user + libresign_app_token"}

    m = frappe.get_doc("Agency Mandate", mandate)
    if not m.mandate_pdf:
        frappe.throw("PDF mandato non disponibile")
    src = frappe.get_site_path("private", "files",
        m.mandate_pdf.split("/private/files/")[-1])
    with open(src, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    app = frappe.get_doc("Applicant Profile", m.applicant) if m.applicant else None
    if not app or not app.email:
        return {"error": "applicant_email_missing"}

    # LibreSign API: POST /ocs/v2.php/apps/libresign/api/v1/request-signature
    payload = {
        "name": f"Thanatos Mandate {m.name}",
        "file": {"base64": f"data:application/pdf;base64,{b64}"},
        "users": [{
            "email": app.email,
            "display_name": app.full_legal_name,
        }],
    }
    try:
        r = requests.post(
            f"{base}/ocs/v2.php/apps/libresign/api/v1/request-signature",
            json=payload, auth=(user, token),
            headers={"OCS-APIREQUEST": "true",
                     "Accept": "application/json"},
            timeout=60)
        r.raise_for_status()
        body = r.json().get("ocs", {}).get("data", {})
        request_id = body.get("uuid") or body.get("id")
        m.signature_ref = f"LibreSign:{request_id}"
        m.status = "Pending Signature"
        m.save(ignore_permissions=True)
        return {"method": "LIBRESIGN", "request_id": request_id,
                "sign_url": body.get("links", [{}])[0].get("href"),
                "status": "sent"}
    except Exception as e:
        return {"error": str(e)[:300], "method": "LIBRESIGN"}


# ---------- MMOS Sign (engine PAdES, additivo accanto a DocuSeal) ----------
def mmos_sign_send(mandate: str) -> dict:
    """Crea una Signature Request mmos_sign dal mandato e la invia in firma.

    Metodo AGGIUNTIVO accanto a DocuSeal: usa l'engine PAdES interno
    (mmos-sign-engine) via mmos_sign.api. Riusa il PDF gia' renderizzato del
    mandato (m.mandate_pdf) se presente, altrimenti rende il print format.
    """
    m = frappe.get_doc("Agency Mandate", mandate)
    app = frappe.get_doc("Applicant Profile", m.applicant) if m.applicant else None
    signer_email = (app.email if app and app.email else None) or "guest@thanatos.agency"
    signer_name = (app.full_legal_name if app else None) or signer_email

    from mmos_sign import api as _ms

    # Se esiste gia' un PDF del mandato, crea la richiesta direttamente da quel PDF;
    # altrimenti delega al render del print format via create_request_from_print.
    if m.mandate_pdf:
        src = frappe.get_site_path("private", "files",
            m.mandate_pdf.split("/private/files/")[-1])
        with open(src, "rb") as f:
            pdf_bytes = f.read()
        req = frappe.new_doc("Signature Request")
        req.reference_doctype = "Agency Mandate"
        req.reference_name = m.name
        req.signing_mode = "Single"
        req.signer_email = signer_email
        req.signer_name = signer_name
        try:
            req.signing_plan = "Advanced (AdES)"
        except Exception:
            pass
        req.insert(ignore_permissions=True)
        fdoc = frappe.get_doc({
            "doctype": "File", "file_name": f"{req.name}_source.pdf",
            "attached_to_doctype": "Signature Request", "attached_to_name": req.name,
            "is_private": 1, "content": pdf_bytes,
        }).insert(ignore_permissions=True)
        req.db_set("source_pdf", fdoc.file_url, update_modified=False)
        frappe.db.commit()
        res = _ms.send_request(req.name)
        sig_req, sign_url = req.name, res.get("url")
    else:
        out = _ms.create_request_from_print(
            reference_doctype="Agency Mandate", reference_name=m.name,
            signer_email=signer_email, signer_name=signer_name, send=True,
        )
        sig_req, sign_url = out.get("signature_request"), out.get("url")

    m.signature_ref = f"MMOSSign:{sig_req}"
    m.status = "Pending Signature"
    m.save(ignore_permissions=True)
    frappe.db.commit()
    return {"method": "MMOS_SIGN", "signature_request": sig_req,
            "sign_url": sign_url, "status": "sent"}


# ---------- Dispatcher -------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def dispatch(mandate: str, method: str, **kw) -> dict:
    """method: SES | SES_OTP | AES_PADES | DOCUSIGN | ADOBE_SIGN | HELLOSIGN"""
    method = (method or "SES").upper()
    if method == "SES":
        from thanatos_intel.thanatos_ddd.signature import sign_mandate
        return sign_mandate(mandate, kw.get("signature_base64"),
                            kw.get("signer_name"))
    if method == "SES_OTP":
        if not verify_otp(mandate, kw.get("otp", "")):
            frappe.throw("OTP non valido o scaduto")
        from thanatos_intel.thanatos_ddd.signature import sign_mandate
        r = sign_mandate(mandate, kw.get("signature_base64"),
                         kw.get("signer_name"))
        r["otp_verified"] = True
        return r
    if method == "AES_PADES":
        return sign_padded(mandate, kw.get("signer_name", ""),
                           kw.get("reason", ""))
    if method == "DOCUSIGN":
        return docusign_send(mandate)
    if method == "ADOBE_SIGN":
        return adobe_sign_send(mandate)
    if method == "HELLOSIGN":
        return hellosign_send(mandate)
    if method == "LIBRESIGN":
        return libresign_send(mandate)
    if method == "MMOS_SIGN":
        return mmos_sign_send(mandate)
    if method == "DOCUSEAL":
        return docuseal_send(mandate)
    if method == "DOCUMENSO":
        return documenso_send(mandate)
    if method == "OPENSIGN":
        return opensign_real_send(mandate)
    frappe.throw(f"Metodo firma sconosciuto: {method}")


@frappe.whitelist()
def list_methods() -> list:
    return [
        {"id": "MMOS_SIGN", "label": "MMOS Sign \u2014 PAdES interno (firma avanzata)",
         "scope": "Globale (ISO 32000 / ETSI PAdES)", "level": "Avanzata (default)",
         "enabled": True, "default": True},
        {"id": "SES", "label": "Firma elettronica semplice (canvas)",
         "scope": "Globale", "level": "Base", "enabled": True},
        {"id": "SES_OTP", "label": "SES + OTP SMS",
         "scope": "Globale", "level": "Rafforzata",
         "enabled": bool(frappe.conf.get("twilio_account_sid"))},
        {"id": "AES_PADES", "label": "AES PAdES-B-B (PDF crittografico)",
         "scope": "Globale (ISO 32000 / ETSI)", "level": "Avanzata",
         "enabled": True},
        {"id": "DOCUSIGN", "label": "DocuSign envelope",
         "scope": "Globale", "level": "Provider esterno",
         "enabled": bool(frappe.conf.get("docusign_access_token"))},
        {"id": "ADOBE_SIGN", "label": "Adobe Acrobat Sign",
         "scope": "Globale", "level": "Provider esterno",
         "enabled": bool(frappe.conf.get("adobe_sign_access_token"))},
        {"id": "HELLOSIGN", "label": "Dropbox Sign (HelloSign)",
         "scope": "Globale", "level": "Provider esterno",
         "enabled": bool(frappe.conf.get("hellosign_api_key"))},
        {"id": "LIBRESIGN", "label": "LibreSign (Nextcloud self-hosted, AGPL OSS)",
         "scope": "Globale + ICP-Brasil", "level": "Provider self-hosted",
         "enabled": bool(frappe.conf.get("libresign_base_url"))},
        {"id": "DOCUSEAL", "label": "DocuSeal self-hosted (17k⭐ MIT)",
         "scope": "Globale", "level": "Provider self-hosted",
         "enabled": bool(frappe.conf.get("docuseal_base_url"))},
        {"id": "DOCUMENSO", "label": "Documenso self-hosted (13k⭐ AGPL)",
         "scope": "Globale + PAdES nativo", "level": "Provider self-hosted",
         "enabled": bool(frappe.conf.get("documenso_base_url"))},
        {"id": "OPENSIGN", "label": "OpenSign self-hosted (6.5k⭐ AGPL)",
         "scope": "Globale", "level": "Provider self-hosted",
         "enabled": bool(frappe.conf.get("opensign_base_url"))},
    ]
