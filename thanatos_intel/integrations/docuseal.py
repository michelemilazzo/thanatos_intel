"""Integrazione DocuSeal per firma digitale interna.

DocuSeal è già deploy su docuseal.thanatos.agency (site_config: docuseal_*).
Pipeline:
  1. generate_mandate_pdf() → PDF allegato al mandato
  2. submit_for_signing(mandate) → crea template con il PDF specifico del mandato
     → crea submission → restituisce signing URL al firmatario via email
  3. Webhook POST /api/method/thanatos_intel.integrations.docuseal.webhook
     → aggiorna mandato: status=Signed, signed_on, docuseal_signed_pdf
  4. signed PDF salvato come file privato Frappe + Drive entity se Drive configurato

Flusso creazione template:
  - Clone del template base (docuseal_base_template_id, default 1)
    che ha i campi firma/data nelle posizioni corrette
  - Replace documento con il PDF del mandato via docker exec rails runner
  - Template monouso: archiviato dopo la firma
"""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import time

import frappe
import requests
from frappe.utils import now_datetime, today


def _conf():
    c = frappe.conf
    return {
        "base_url": c.get("docuseal_base_url", "").rstrip("/"),
        "api_key": c.get("docuseal_api_key", ""),
        # Template base con campi firma/data nelle posizioni standard — viene clonato
        # per ogni mandato e il documento viene sostituito col PDF specifico.
        "base_template_id": int(c.get("docuseal_base_template_id", 1)),
        # Container Docker DocuSeal (per rails runner via docker exec)
        "container": c.get("docuseal_container", "thanatos-docuseal"),
        "webhook_secret": c.get("docuseal_webhook_secret", ""),
        "hmac_secret": c.get("docuseal_hmac_secret", ""),
    }


def _headers():
    return {"X-Auth-Token": _conf()["api_key"], "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Template dinamico: clone base + replace PDF via Docker rails runner
# ---------------------------------------------------------------------------

_RAILS_SCRIPT = """
require 'tempfile'

pdf_path    = ARGV[0]
tmpl_name   = ARGV[1]
base_tmpl_id = ARGV[2].to_i

pdf_data = File.read(pdf_path, mode: 'rb')
user     = User.first
base     = Template.find(base_tmpl_id)

# Clone (non salvato)
template = Templates::Clone.call(base, author: user, name: tmpl_name)
template.save!

# Crea file upload in-memory
tempfile = Tempfile.new([tmpl_name, '.pdf'])
tempfile.binmode
tempfile.write(pdf_data)
tempfile.rewind

upload = ActionDispatch::Http::UploadedFile.new(
  filename: tmpl_name + '.pdf',
  type:     'application/pdf',
  tempfile: tempfile
)

Templates::ReplaceAttachments.call(template, files: [upload])
template.save!

tempfile.close
tempfile.unlink

puts template.id.to_s
"""


def _create_template_from_pdf(mandate_name: str, pdf_path: str) -> int:
    """Crea un template DocuSeal dal PDF del mandato.
    Clona il template base, sostituisce il documento, restituisce il nuovo template_id.
    Usa docker exec + rails runner per aggirare il limite API.
    """
    conf = _conf()
    container = conf["container"]
    base_tmpl_id = conf["base_template_id"]

    # Copia il PDF nel container
    container_pdf = f"/tmp/mandate_{mandate_name.replace(' ', '_')}.pdf"
    cp_result = subprocess.run(
        ["docker", "cp", pdf_path, f"{container}:{container_pdf}"],
        capture_output=True, text=True, timeout=30
    )
    if cp_result.returncode != 0:
        frappe.throw(f"docker cp fallito: {cp_result.stderr[:300]}")

    # Scrive lo script Ruby in un file temporaneo nel container
    script_path = f"/tmp/create_tmpl_{mandate_name.replace(' ', '_')}.rb"
    write_result = subprocess.run(
        ["docker", "exec", container, "sh", "-c",
         f"cat > {script_path}"],
        input=_RAILS_SCRIPT, capture_output=True, text=True, timeout=10
    )
    if write_result.returncode != 0:
        frappe.throw(f"Scrittura script Ruby fallita: {write_result.stderr[:200]}")

    # Esegui lo script
    run_result = subprocess.run(
        ["docker", "exec", container, "sh", "-c",
         f"cd /app && bundle exec rails runner {script_path} "
         f"'{container_pdf}' '{mandate_name}' '{base_tmpl_id}'"],
        capture_output=True, text=True, timeout=120
    )

    # Cleanup container temp files
    subprocess.run(
        ["docker", "exec", container, "sh", "-c",
         f"rm -f {container_pdf} {script_path}"],
        capture_output=True, timeout=10
    )

    if run_result.returncode != 0:
        frappe.log_error(f"rails runner stderr: {run_result.stderr[:500]}", "DocuSeal")
        frappe.throw(f"Creazione template DocuSeal fallita: {run_result.stderr[-300:]}")

    lines = [l.strip() for l in run_result.stdout.strip().split('\n') if l.strip()]
    try:
        return int(lines[-1])
    except (ValueError, IndexError):
        frappe.log_error(f"Output rails runner: {run_result.stdout[:300]}", "DocuSeal")
        frappe.throw("Impossibile leggere template_id da output rails runner")


def _resolve_pdf_path(file_url: str) -> str:
    """Risolve file_url Frappe in path assoluto sul filesystem."""
    if "/private/files/" in file_url:
        return frappe.get_site_path("private", "files",
                                    file_url.split("/private/files/")[-1])
    return frappe.get_site_path("public", "files",
                                file_url.lstrip("/"))


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

    # Risolvi email e nome del firmatario
    email = name = ""
    if mandate.applicant:
        ap = frappe.db.get_value("Applicant Profile", mandate.applicant,
                                  ["full_legal_name", "email"], as_dict=1) or {}
        email = ap.get("email", "")
        name = ap.get("full_legal_name", mandate.applicant)
    if not email and mandate.ddd_case:
        client_name = frappe.db.get_value("Diplomatic Eligibility Case", mandate.ddd_case, "client")
        if client_name:
            email = frappe.db.get_value("Investigation Client", client_name, "email") or ""
            name = frappe.db.get_value("Investigation Client", client_name, "client_name") or name
    if not email:
        frappe.throw("Nessuna email trovata per il richiedente. Impossibile inviare a DocuSeal.")

    # ── Crea template DocuSeal con il PDF specifico del mandato ──
    pdf_path = _resolve_pdf_path(mandate.mandate_pdf)
    if not os.path.exists(pdf_path):
        frappe.throw(f"PDF mandato non trovato sul filesystem: {pdf_path}")

    template_id = _create_template_from_pdf(mandate_name, pdf_path)

    # Leggi ruolo submitter dal template appena creato
    tmpl_resp = requests.get(f"{conf['base_url']}/api/templates/{template_id}",
                             headers=_headers(), timeout=10)
    submitter_role = "Prima parte"
    if tmpl_resp.status_code == 200:
        roles = [s.get("name", "") for s in tmpl_resp.json().get("submitters", [])]
        if roles:
            submitter_role = roles[0]

    # ── Crea submission ──
    payload = {
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

    resp = requests.post(f"{conf['base_url']}/api/templates/{template_id}/submissions",
                         headers=_headers(), json=payload, timeout=15)
    if resp.status_code not in (200, 201):
        # Archivia il template orfano in caso di errore
        requests.delete(f"{conf['base_url']}/api/templates/{template_id}",
                        headers=_headers(), timeout=5)
        frappe.throw(f"DocuSeal submission error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    submitters = data if isinstance(data, list) else data.get("submitters", [])
    first = submitters[0] if submitters else {}
    submission_id = first.get("submission_id") or first.get("id")
    slug = first.get("slug", "")
    signing_url = f"{conf['base_url']}/s/{slug}" if slug else first.get("embed_src", "")

    mandate.db_set("docuseal_submission_id", submission_id, update_modified=False)
    mandate.db_set("docuseal_signing_url", signing_url, update_modified=False)
    # Memorizza template_id monouso per archiviarlo dopo la firma
    mandate.db_set("docuseal_template_id", template_id, update_modified=False)
    mandate.db_set("status", "Pending Signature", update_modified=False)
    frappe.db.commit()

    return {"ok": True, "submission_id": submission_id, "signing_url": signing_url,
            "template_id": template_id}


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

    # Archivia il template monouso (mantiene storico ma non appare nei template attivi)
    tmpl_id = frappe.db.get_value("Agency Mandate", mandate_name, "docuseal_template_id")
    if tmpl_id:
        try:
            conf = _conf()
            requests.delete(f"{conf['base_url']}/api/templates/{tmpl_id}",
                            headers=_headers(), timeout=5)
        except Exception:
            pass

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
