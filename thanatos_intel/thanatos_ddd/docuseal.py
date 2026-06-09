"""DocuSeal integration — template upload + submission + webhook.

Config site_config.json:
  docuseal_base_url            https://docuseal.thanatos.agency
  docuseal_api_key             <api key>
  docuseal_admin_email         admin@thanatos.agency   (default)
  docuseal_admin_password      <password>
  docuseal_webhook_secret      <optional HMAC secret>

Flow:
  1. send(mandate)  — upload PDF as template (session), create submission, email applicant
  2. webhook()      — receive DocuSeal callbacks, update Mandate status + pull signed PDF
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import io
import json
import re
import time

import frappe
import requests


# ── config helpers ────────────────────────────────────────────────────────────

def _cfg() -> tuple[str, str]:
    """Returns (base_url, api_key) or raises if not configured."""
    base = (frappe.conf.get("docuseal_base_url") or "").rstrip("/")
    key = frappe.conf.get("docuseal_api_key") or ""
    if not (base and key):
        frappe.throw(
            "DocuSeal non configurato. Aggiungere docuseal_base_url e "
            "docuseal_api_key in site_config.json.",
            title="DocuSeal config mancante",
        )
    return base, key


def _headers(key: str) -> dict:
    return {"X-Auth-Token": key, "Content-Type": "application/json"}


# ── session login (per template upload — API Pro-only) ────────────────────────

def _login_session(base: str) -> requests.Session:
    """Autentica come admin via web session. Cache cookie 1 ora."""
    cache_key = "ddd:ds_session_v2"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        s = requests.Session()
        s.cookies.update(json.loads(cached))
        # quick check
        r = s.get(f"{base}/dashboard", timeout=10, allow_redirects=False)
        if r.status_code != 302:
            return s
        frappe.cache().delete_key(cache_key)

    user = frappe.conf.get("docuseal_admin_email") or "admin@thanatos.agency"
    pw = frappe.conf.get("docuseal_admin_password") or ""
    if not pw:
        frappe.throw("site_config.docuseal_admin_password mancante")

    s = requests.Session()
    r = s.get(f"{base}/sign_in", timeout=15)
    tok = re.search(r'csrf-token["\s]+content="([^"]+)"', r.text)
    if not tok:
        frappe.throw("DocuSeal: CSRF token non trovato in /sign_in")
    csrf = tok.group(1)
    s.headers.update({
        "X-CSRF-Token": csrf,
        "Accept": "text/vnd.turbo-stream.html, text/html, */*",
        "Origin": base,
        "Referer": f"{base}/sign_in",
    })
    r = s.post(f"{base}/sign_in",
               data={"authenticity_token": csrf,
                     "user[email]": user,
                     "user[password]": pw},
               allow_redirects=True, timeout=15)
    if "sign_in" in r.url or r.status_code >= 400:
        frappe.throw(f"DocuSeal login fallito (HTTP {r.status_code})")
    frappe.cache().set_value(cache_key,
                             json.dumps(dict(s.cookies.get_dict())),
                             expires_in_sec=3600)
    return s


# ── PDF URL temporanea (10 min) ───────────────────────────────────────────────

def _signed_pdf_url(mandate: str) -> str:
    ts = str(int(time.time()) + 600)
    secret = (frappe.conf.get("encryption_key") or "").encode()
    sig = _hmac.new(secret, f"{mandate}|{ts}".encode(), hashlib.sha256).hexdigest()
    return (
        f"{frappe.utils.get_url()}/api/method/"
        "thanatos_intel.thanatos_ddd.docuseal.serve_mandate_pdf"
        f"?mandate={mandate}&token={ts}.{sig}"
    )


@frappe.whitelist(allow_guest=True)
def serve_mandate_pdf(mandate: str, token: str):
    """Endpoint temporaneo per servire il PDF mandate a DocuSeal."""
    try:
        ts, sig = token.split(".", 1)
        if int(ts) < int(time.time()):
            frappe.throw("Token scaduto", frappe.PermissionError)
        secret = (frappe.conf.get("encryption_key") or "").encode()
        expected = _hmac.new(secret, f"{mandate}|{ts}".encode(), hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(sig, expected):
            frappe.throw("Token non valido", frappe.PermissionError)
    except (ValueError, AttributeError):
        frappe.throw("Token malformato", frappe.PermissionError)

    m = frappe.get_doc("Agency Mandate", mandate)
    path = frappe.get_site_path("private", "files",
                                m.mandate_pdf.split("/private/files/")[-1])
    with open(path, "rb") as f:
        content = f.read()
    frappe.local.response.filename = f"Mandate-{mandate}.pdf"
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.headers = {"Content-Type": "application/pdf"}


# ── template lookup / creation ────────────────────────────────────────────────

def _find_existing_template(mandate: str, base: str, key: str) -> int | None:
    """Cerca un template già creato per questo mandate (evita duplicati)."""
    expected_name = f"Mandate-{mandate}"
    try:
        r = requests.get(f"{base}/api/templates",
                         headers={"X-Auth-Token": key}, timeout=15)
        for tpl in (r.json() if isinstance(r.json(), list) else r.json().get("data", [])):
            if tpl.get("name") == expected_name:
                return tpl["id"]
    except Exception:
        pass
    return None


def _upload_template(mandate: str, base: str, key: str) -> int:
    """Crea template DocuSeal dall'URL PDF firmato. Ritorna template_id."""
    pdf_url = _signed_pdf_url(mandate)
    s = _login_session(base)

    # Fresh CSRF dopo login
    rp = s.get(f"{base}/templates", timeout=15)
    csrf_m = re.search(r'csrf-token["\s]+content="([^"]+)"', rp.text)
    csrf = csrf_m.group(1) if csrf_m else s.headers.get("X-CSRF-Token", "")
    if csrf:
        s.headers["X-CSRF-Token"] = csrf

    resp = s.post(
        f"{base}/templates_upload",
        data={
            "url": pdf_url,
            "filename": f"Mandate-{mandate}.pdf",
            "authenticity_token": csrf,
        },
        allow_redirects=False,
        timeout=60,
    )
    if resp.status_code not in (200, 302):
        frappe.throw(f"DocuSeal templates_upload failed: HTTP {resp.status_code} — {resp.text[:200]}")

    # Estrai template_id dal redirect o dal body
    loc = resp.headers.get("Location", "")
    m_id = re.search(r"/templates/(\d+)", loc) or re.search(r'"id"\s*:\s*(\d+)', resp.text)
    if not m_id:
        frappe.throw(f"template_id non trovato. Location={loc[:200]} body={resp.text[:200]}")
    tpl_id = int(m_id.group(1))

    # Rinomina il template con il nome del mandate
    requests.put(
        f"{base}/api/templates/{tpl_id}",
        headers=_headers(key),
        json={"name": f"Mandate-{mandate}"},
        timeout=15,
    )

    # Aggiungi campo firma + data se non presenti
    info = requests.get(f"{base}/api/templates/{tpl_id}",
                        headers={"X-Auth-Token": key}, timeout=15).json()
    sub_uuid = (info.get("submitters") or [{}])[0].get("uuid", "")
    existing_fields = {f["name"] for f in (info.get("fields") or [])}
    new_fields = []
    if "signature" not in existing_fields:
        new_fields.append({
            "name": "signature", "type": "signature",
            "submitter_uuid": sub_uuid, "required": True,
            "areas": [{"x": 0.55, "y": 0.85, "w": 0.35, "h": 0.05, "page": 0}],
        })
    if "date" not in existing_fields:
        new_fields.append({
            "name": "date", "type": "date",
            "submitter_uuid": sub_uuid, "required": True,
            "areas": [{"x": 0.10, "y": 0.92, "w": 0.20, "h": 0.03, "page": 0}],
        })
    if new_fields:
        requests.put(
            f"{base}/api/templates/{tpl_id}",
            headers=_headers(key),
            json={"fields": (info.get("fields") or []) + new_fields},
            timeout=15,
        )
    return tpl_id


# ── main send ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def send(mandate: str) -> dict:
    """Invia il mandate per firma via DocuSeal.

    Flow:
    1. Trova o crea template per questo mandate
    2. Crea submission con email al firmatario
    3. Aggiorna Mandate.status = Pending Signature
    """
    base, key = _cfg()
    m = frappe.get_doc("Agency Mandate", mandate)
    if not m.mandate_pdf:
        return {"error": "mandate_pdf_missing",
                "hint": "Generare prima il PDF (thanatos_ddd.pdf)"}
    if m.status in ("Signed", "Active", "Completed"):
        return {"error": f"mandate_already_{m.status.lower()}"}

    app = frappe.get_doc("Applicant Profile", m.applicant) if m.applicant else None
    if not app or not app.email:
        return {"error": "applicant_email_missing"}

    # Template: riusa se esiste, altrimenti crea
    tpl_id = _find_existing_template(mandate, base, key) or _upload_template(mandate, base, key)

    # Submission
    info = requests.get(f"{base}/api/templates/{tpl_id}",
                        headers={"X-Auth-Token": key}, timeout=15).json()
    role = (info.get("submitters") or [{}])[0].get("name", "Firmatario")

    r = requests.post(
        f"{base}/api/submissions",
        headers=_headers(key),
        json={
            "template_id": tpl_id,
            "send_email": True,
            "submitters": [{
                "email": app.email,
                "name": app.full_legal_name or app.name,
                "role": role,
                "metadata": {"mandate": mandate, "ddd_case": m.ddd_case or ""},
            }],
        },
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    sub = body[0] if isinstance(body, list) else body
    sub_id = sub.get("id")
    slug = sub.get("slug") or (sub.get("submitters") or [{}])[0].get("slug")
    sign_url = f"{base}/s/{slug}" if slug else None

    m.signature_ref = f"DocuSeal:{tpl_id}/{sub_id}"
    m.status = "Pending Signature"
    m.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "method": "DOCUSEAL",
        "template_id": tpl_id,
        "submission_id": sub_id,
        "sign_url": sign_url,
        "email_sent_to": app.email,
        "status": "sent",
    }


# ── webhook ───────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook():
    """Riceve callback DocuSeal e aggiorna Agency Mandate.

    Events: form.viewed, form.started, form.completed, submission.completed,
            form.declined.
    Autenticazione: HMAC-SHA256 body → header X-DocuSeal-Signature (opzionale).
    """
    secret = frappe.conf.get("docuseal_webhook_secret") or ""
    raw = frappe.request.get_data() or b""
    if secret:
        sig = frappe.get_request_header("X-DocuSeal-Signature") or ""
        expected = _hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(expected, sig):
            frappe.local.response["http_status_code"] = 401
            return {"error": "invalid_signature"}

    try:
        payload = frappe.parse_json(raw.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    evt = (payload or {}).get("event_type") or ""
    data = (payload or {}).get("data") or {}
    sub_id = (data.get("submission_id") or data.get("id")
              or (data.get("submission") or {}).get("id"))
    tpl_id = data.get("template_id") or (data.get("template") or {}).get("id")

    if not sub_id:
        return {"ok": True, "skipped": "no_submission_id", "event": evt}

    # Trova mandate da signature_ref
    rows = frappe.db.sql(
        "SELECT name FROM `tabAgency Mandate` WHERE signature_ref LIKE %s LIMIT 1",
        (f"DocuSeal:%/{sub_id}",),
    )
    if not rows and tpl_id:
        rows = frappe.db.sql(
            "SELECT name FROM `tabAgency Mandate` WHERE signature_ref LIKE %s LIMIT 1",
            (f"DocuSeal:{tpl_id}/%",),
        )
    if not rows:
        return {"ok": True, "skipped": "mandate_not_found", "event": evt, "sub_id": sub_id}

    mname = rows[0][0]
    m = frappe.get_doc("Agency Mandate", mname)

    status_map = {
        "form.viewed":          ("Pending Signature", "viewed"),
        "form.started":         ("Pending Signature", "started"),
        "submission.created":   ("Pending Signature", "created"),
        "form.completed":       ("Signed",            "completed"),
        "submission.completed": ("Signed",            "completed"),
        "form.declined":        ("Terminated",        "declined"),
    }
    if evt not in status_map:
        return {"ok": True, "ignored_event": evt}

    new_status, short = status_map[evt]

    if new_status == "Signed":
        _pull_signed_pdf(m, sub_id)
        m.signed_on = frappe.utils.now_datetime()

    m.status = new_status
    try:
        m.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"DocuSeal webhook mandate save: {e}", "docuseal_webhook")

    try:
        frappe.get_doc({
            "doctype": "Diplomatic Audit Log",
            "ddd_case": m.ddd_case,
            "event_type": f"docuseal.{short}",
            "new_value": new_status,
            "reason": json.dumps({
                "mandate": m.name, "submission_id": sub_id,
                "template_id": tpl_id, "event": evt,
            })[:500],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {"ok": True, "mandate": m.name, "status": new_status, "event": evt}


def _pull_signed_pdf(m, sub_id: int):
    """Scarica il PDF firmato da DocuSeal e lo salva come File Frappe."""
    try:
        base, key = _cfg()
        info = requests.get(f"{base}/api/submissions/{sub_id}",
                            headers={"X-Auth-Token": key}, timeout=20).json()
        docs = info.get("documents") or []
        pdf_url = next(
            (d["url"] for d in docs if (d.get("filename") or "").lower().endswith(".pdf")),
            None,
        )
        if not pdf_url:
            return
        p = requests.get(pdf_url, timeout=60)
        if not p.ok:
            return
        saved = frappe.get_doc({
            "doctype": "File",
            "file_name": f"Mandate-{m.name}-signed.pdf",
            "is_private": 1,
            "content": p.content,
            "attached_to_doctype": "Agency Mandate",
            "attached_to_name": m.name,
        }).insert(ignore_permissions=True)
        m.mandate_pdf = saved.file_url
    except Exception as e:
        frappe.log_error(f"DocuSeal pull signed pdf: {e}", "docuseal_webhook")


# ── utility: configura webhook su DocuSeal via sessione admin ─────────────────

@frappe.whitelist()
def configure_webhook() -> dict:
    """Imposta il webhook DocuSeal → questo sito. Solo System Manager."""
    frappe.only_for("System Manager")
    base, key = _cfg()
    webhook_url = (
        f"{frappe.utils.get_url()}/api/method/"
        "thanatos_intel.thanatos_ddd.docuseal.webhook"
    )
    events = [
        "form.viewed", "form.started", "form.completed",
        "submission.completed", "form.declined",
    ]
    try:
        s = _login_session(base)
        rp = s.get(f"{base}/settings/webhooks", timeout=15)
        csrf_m = re.search(r'csrf-token["\s]+content="([^"]+)"', rp.text)
        csrf = csrf_m.group(1) if csrf_m else s.headers.get("X-CSRF-Token", "")
        if csrf:
            s.headers["X-CSRF-Token"] = csrf
        r = s.post(
            f"{base}/settings/webhooks",
            data={
                "authenticity_token": csrf,
                "webhook[url]": webhook_url,
                "webhook[events][]": events,
            },
            allow_redirects=True,
            timeout=15,
        )
        return {"ok": r.status_code < 400, "http": r.status_code, "url": webhook_url}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
