"""Integrazione DocuSeal per firma digitale interna.

DocuSeal è già deploy su docuseal.thanatos.agency (site_config: docuseal_*).
Pipeline:
  1. generate_mandate_pdf() → PDF allegato al mandato
  2. submit_for_signing(mandate) → crea submission su DocuSeal → restituisce signing URL
  3. Webhook POST /api/method/thanatos_intel.integrations.docuseal.webhook
     → aggiorna mandato: status=Signed, signed_on, docuseal_signed_pdf
  4. signed PDF salvato come file privato Frappe + Drive entity se Drive configurato
"""
import hashlib
import hmac
import json

import frappe
import requests
from frappe.utils import now_datetime, today


def _conf():
    c = frappe.conf
    return {
        "base_url": c.get("docuseal_base_url", "").rstrip("/"),
        "api_key": c.get("docuseal_api_key", ""),
        "template_id": c.get("docuseal_template_id"),
        "webhook_secret": c.get("docuseal_webhook_secret", ""),
    }


def _headers():
    return {"X-Auth-Token": _conf()["api_key"], "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Submit mandate per firma
# ---------------------------------------------------------------------------

def submit_mandate_for_signing(mandate_name: str) -> dict:
    """Invia il mandato a DocuSeal.
    Restituisce {"ok": True, "submission_id": int, "signing_url": str}
    """
    mandate = frappe.get_doc("Agency Mandate", mandate_name)
    if not mandate.mandate_pdf:
        frappe.throw("Generare prima il PDF del mandato.")
    if mandate.docuseal_submission_id:
        return {"ok": False, "error": "Mandato già inviato a DocuSeal."}

    conf = _conf()
    if not conf["base_url"] or not conf["api_key"]:
        frappe.throw("DocuSeal non configurato (mancano docuseal_base_url/docuseal_api_key in site_config).")

    # Recupera dati richiedente per pre-compilare il form
    email = ""
    name = ""
    if mandate.applicant:
        ap = frappe.db.get_value("Applicant Profile", mandate.applicant,
                                  ["full_name", "email"], as_dict=1) or {}
        email = ap.get("email", "")
        name = ap.get("full_name", mandate.applicant)

    if not email:
        # fallback: client del caso DDD
        client_name = frappe.db.get_value("Diplomatic Eligibility Case",
                                           mandate.ddd_case, "client") if mandate.ddd_case else None
        if client_name:
            email = frappe.db.get_value("Investigation Client", client_name, "email") or ""
            name = frappe.db.get_value("Investigation Client", client_name, "client_name") or name

    if not email:
        frappe.throw("Nessuna email trovata per il richiedente. Impossibile inviare a DocuSeal.")

    # Costruisci payload submission
    payload = {
        "template_id": conf["template_id"],
        "send_email": True,
        "submitters": [{
            "role": "First Party",
            "email": email,
            "name": name,
            "fields": [
                {"name": "mandate_number", "default_value": mandate.name},
                {"name": "fee_total", "default_value": str(mandate.fee_total or "")},
                {"name": "governing_law", "default_value": mandate.governing_law or ""},
            ],
        }],
        "metadata": {
            "mandate": mandate.name,
            "case": mandate.ddd_case or "",
        },
    }

    resp = requests.post(f"{conf['base_url']}/api/submissions",
                         headers=_headers(), json=payload, timeout=15)
    if resp.status_code not in (200, 201):
        frappe.throw(f"DocuSeal error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    submission_id = data.get("id")
    # signing URL: first submitter's embed_src or slug
    submitters = data.get("submitters", [])
    signing_url = ""
    if submitters:
        slug = submitters[0].get("slug", "")
        signing_url = f"{conf['base_url']}/s/{slug}" if slug else submitters[0].get("embed_src", "")

    mandate.db_set("docuseal_submission_id", submission_id, update_modified=False)
    mandate.db_set("docuseal_signing_url", signing_url, update_modified=False)
    mandate.db_set("status", "Pending Signature", update_modified=False)
    frappe.db.commit()

    return {"ok": True, "submission_id": submission_id, "signing_url": signing_url}


# ---------------------------------------------------------------------------
# Webhook da DocuSeal
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook():
    """POST /api/method/thanatos_intel.integrations.docuseal.webhook
    DocuSeal notifica completion o eventi intermedi.
    Verifica HMAC con docuseal_webhook_secret.
    """
    raw = frappe.request.get_data()
    conf = _conf()

    # Verifica firma HMAC
    if conf["webhook_secret"]:
        sig_header = frappe.request.headers.get("X-Docuseal-Signature", "")
        expected = hmac.new(conf["webhook_secret"].encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            frappe.response["http_status_code"] = 401
            return {"error": "Invalid signature"}

    try:
        payload = json.loads(raw)
    except Exception:
        frappe.response["http_status_code"] = 400
        return {"error": "Invalid JSON"}

    event_type = payload.get("event_type", "")
    submission = payload.get("submission", {}) or payload.get("data", {})
    submission_id = submission.get("id") or payload.get("id")

    if not submission_id:
        return {"ok": True, "note": "no submission_id"}

    # Trova il mandato
    mandate_name = frappe.db.get_value("Agency Mandate",
                                        {"docuseal_submission_id": submission_id}, "name")
    if not mandate_name:
        # cerca in metadata
        meta = submission.get("metadata", {})
        mandate_name = meta.get("mandate")

    if not mandate_name:
        return {"ok": True, "note": "mandate not found"}

    if event_type in ("submission.completed", "form.completed"):
        _on_submission_completed(mandate_name, submission)
    elif event_type == "submission.expired":
        frappe.db.set_value("Agency Mandate", mandate_name, "status", "Draft", update_modified=False)
        frappe.db.commit()

    return {"ok": True}


def _on_submission_completed(mandate_name: str, submission: dict):
    """Mandato firmato: scarica il PDF da DocuSeal, salva su Frappe."""
    conf = _conf()
    documents = submission.get("documents", []) or []
    signed_pdf_url = ""
    local_file_url = ""

    for doc in documents:
        url = doc.get("url", "")
        if url and doc.get("name", "").lower().endswith(".pdf"):
            signed_pdf_url = url
            break

    if signed_pdf_url and conf["base_url"] in signed_pdf_url:
        # Scarica il PDF da DocuSeal
        try:
            resp = requests.get(signed_pdf_url, headers=_headers(), timeout=30)
            if resp.status_code == 200:
                filename = f"{mandate_name}_signed.pdf"
                site_path = frappe.get_site_path("private", "files", filename)
                with open(site_path, "wb") as f:
                    f.write(resp.content)
                file_doc = frappe.get_doc({
                    "doctype": "File",
                    "file_name": filename,
                    "file_url": f"/private/files/{filename}",
                    "is_private": 1,
                    "attached_to_doctype": "Agency Mandate",
                    "attached_to_name": mandate_name,
                }).insert(ignore_permissions=True)
                local_file_url = file_doc.file_url
        except Exception as e:
            frappe.log_error(f"DocuSeal PDF download error: {e}", "DocuSeal")

    frappe.db.set_value("Agency Mandate", mandate_name, {
        "status": "Signed",
        "signed_on": today(),
        "docuseal_signed_pdf": local_file_url or signed_pdf_url,
    }, update_modified=True)
    frappe.db.commit()

    _push_signed_to_drive(mandate_name, local_file_url)


# ---------------------------------------------------------------------------
# Drive: push del PDF firmato nella cartella del caso
# ---------------------------------------------------------------------------

def _push_signed_to_drive(mandate_name: str, file_url: str):
    """Crea un Drive Entity nella cartella del caso."""
    if not file_url:
        return
    try:
        mandate = frappe.get_doc("Agency Mandate", mandate_name)
        case_name = mandate.ddd_case
        if not case_name:
            return
        folder = _get_or_create_case_drive_folder(case_name)
        if not folder:
            return

        frappe.get_doc({
            "doctype": "Drive Entity",
            "title": f"{mandate_name}_signed.pdf",
            "file_size": 0,
            "mime_type": "application/pdf",
            "parent_drive_entity": folder,
            "file_ext": "pdf",
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Drive push error: {e}", "DocuSeal Drive")


def _get_or_create_case_drive_folder(case_name: str) -> str | None:
    """Trova o crea la cartella Drive per il caso. Restituisce il name del Drive Entity."""
    existing = frappe.db.get_value("Drive Entity",
                                    {"title": case_name, "is_group": 1}, "name")
    if existing:
        return existing
    try:
        folder = frappe.get_doc({
            "doctype": "Drive Entity",
            "title": case_name,
            "is_group": 1,
            "mime_type": "frappe_drive/folder",
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        return folder.name
    except Exception as e:
        frappe.log_error(f"Drive folder creation error: {e}", "DocuSeal Drive")
        return None


# ---------------------------------------------------------------------------
# Whitelist API per il desk
# ---------------------------------------------------------------------------

@frappe.whitelist()
def send_to_docuseal(mandate_name: str) -> dict:
    """Chiamata dal form Agency Mandate → pulsante 'Invia a DocuSeal'."""
    return submit_mandate_for_signing(mandate_name)


@frappe.whitelist()
def get_submission_status(submission_id: int) -> dict:
    """Stato corrente di una submission DocuSeal."""
    conf = _conf()
    resp = requests.get(f"{conf['base_url']}/api/submissions/{submission_id}",
                        headers=_headers(), timeout=10)
    if resp.status_code == 200:
        return {"ok": True, "data": resp.json()}
    return {"ok": False, "status_code": resp.status_code}
