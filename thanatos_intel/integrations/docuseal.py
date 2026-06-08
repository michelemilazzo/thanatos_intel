"""Integrazione DocuSeal per firma digitale interna.

DocuSeal è già deploy su docuseal.thanatos.agency (site_config: docuseal_*).
Pipeline:
  1. generate_mandate_pdf() → PDF allegato al mandato
  2. submit_for_signing(mandate) → crea submission su DocuSeal → restituisce signing URL
  3. Webhook POST /api/method/thanatos_intel.integrations.docuseal.webhook
     → aggiorna mandato: status=Signed, signed_on, docuseal_signed_pdf
  4. signed PDF salvato come file privato Frappe + Drive entity se Drive configurato
"""
import base64
import hashlib
import hmac
import json
import time

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
        # hmac_secret auto-generato da DocuSeal (formato: whsec_<base64>)
        # firma: "{ts}.{HMAC_SHA256(hmac_secret, '{ts}.{body}')}"
        "hmac_secret": c.get("docuseal_hmac_secret", ""),
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
                                  ["full_legal_name", "email"], as_dict=1) or {}
        email = ap.get("email", "")
        name = ap.get("full_legal_name", mandate.applicant)

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
    # Legge i ruoli dal template per usare il nome esatto
    tmpl_resp = requests.get(f"{conf['base_url']}/api/templates/{conf['template_id']}",
                             headers=_headers(), timeout=10)
    submitter_role = "First Party"
    if tmpl_resp.status_code == 200:
        roles = [s.get("name", "") for s in tmpl_resp.json().get("submitters", [])]
        if roles:
            submitter_role = roles[0]

    payload = {
        "template_id": conf["template_id"],
        "send_email": True,
        "submitters": [{
            "role": submitter_role,
            "email": email,
            "name": name,
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
    # DocuSeal POST /api/submissions returns a list of submitter objects
    submitters = data if isinstance(data, list) else data.get("submitters", [])
    first = submitters[0] if submitters else {}
    submission_id = first.get("submission_id") or first.get("id")
    slug = first.get("slug", "")
    signing_url = f"{conf['base_url']}/s/{slug}" if slug else first.get("embed_src", "")

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

    # Verifica firma HMAC DocuSeal
    # Formato header: "{timestamp}.{HMAC_SHA256(hmac_secret, '{timestamp}.{body}')}"
    hmac_secret = conf.get("hmac_secret", "")
    if hmac_secret:
        sig_header = frappe.request.headers.get("X-Docuseal-Signature", "")
        parts = sig_header.split(".", 1)
        if len(parts) != 2:
            frappe.response["http_status_code"] = 401
            return {"error": "Invalid signature format"}
        ts_str, sig = parts
        try:
            ts = int(ts_str)
        except ValueError:
            frappe.response["http_status_code"] = 401
            return {"error": "Invalid timestamp"}
        # tolleranza 10 minuti
        if abs(int(time.time()) - ts) > 600:
            frappe.response["http_status_code"] = 401
            return {"error": "Timestamp out of range"}
        # decodifica il secret (prefisso whsec_ + base64)
        raw_secret = hmac_secret
        if raw_secret.startswith("whsec_"):
            try:
                raw_secret = base64.b64decode(hmac_secret[6:])
            except Exception:
                raw_secret = hmac_secret.encode()
        elif isinstance(raw_secret, str):
            raw_secret = raw_secret.encode()
        signed_payload = f"{ts_str}.{raw.decode('utf-8', errors='replace')}".encode()
        expected = hmac.new(raw_secret, signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
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
    """Copia il PDF firmato in Drive sotto Mandati Firmati/{case_name}/."""
    if not file_url:
        return
    try:
        import os, shutil
        from pathlib import Path

        mandate = frappe.get_doc("Agency Mandate", mandate_name)
        case_name = mandate.ddd_case
        if not case_name:
            return

        filename = f"{mandate_name}_signed.pdf"
        src_path = frappe.get_site_path("private", "files", filename)
        if not os.path.exists(src_path):
            return

        file_size = os.path.getsize(src_path)

        # Esegui come Administrator per avere accesso Drive
        prev_user = frappe.session.user
        frappe.set_user("Administrator")
        try:
            from drive.utils import get_home_folder, create_drive_file
            from drive.utils.files import FileManager
            from drive.api.files import create_folder

            # Team Drive per i mandati firmati — configurabile via site_config drive_admin_team
            team = frappe.conf.get("drive_admin_team", "c6o2dfl3t7")
            home = get_home_folder(team)

            # Cartella "Mandati Firmati" sotto root
            mandati = frappe.db.get_value("Drive File", {
                "title": "Mandati Firmati", "parent_entity": home["name"],
                "is_group": 1, "team": team, "is_active": 1,
            }, "name")
            if not mandati:
                mandati = create_folder(team, "Mandati Firmati", home["name"]).name

            # Cartella per il caso
            case_folder = frappe.db.get_value("Drive File", {
                "title": case_name, "parent_entity": mandati,
                "is_group": 1, "team": team, "is_active": 1,
            }, "name")
            if not case_folder:
                case_folder = create_folder(team, case_name, mandati).name

            manager = FileManager()

            drive_file = create_drive_file(
                team, filename, case_folder, "application/pdf",
                lambda entity: manager.get_disk_path(entity, home),
                file_size,
            )

            dst_path = manager.site_folder / drive_file.path
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, str(dst_path))
            frappe.db.commit()

        finally:
            frappe.set_user(prev_user)

    except Exception as e:
        frappe.log_error(f"Drive push error: {e}", "DocuSeal Drive")


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
