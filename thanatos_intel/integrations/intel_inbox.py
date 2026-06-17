"""Email auto-linker per Investigation Case.

Hook on Communication insert: parsa mittente, lo associa al caso aperto del
Investigation Client, oppure crea Lead/Ticket se mittente sconosciuto.

Integrazione naturale con Frappe Email Account (IMAP fetch ogni 5 min) +
Communication (reference_doctype/name nativo per agganciare al caso).

Setup: in Frappe Desk → Email Account → cases@thanatos.agency:
  enable_incoming=1
  enable_auto_reply=0
  uid_validity (per dedup)
  default_incoming_link_field e Append-To DocType = Investigation Case
  (Frappe lo usa per auto-link via threading Message-ID; questo file aggiunge
   il fallback sender-email lookup quando il threading non basta).
"""
from __future__ import annotations
import re
import frappe
from frappe.utils import now_datetime

EMAIL_RE = re.compile(r"<([^>]+)>|([^\s,;<>]+@[^\s,;<>]+)")


def on_communication_insert(doc, method=None):
    """Auto-link Communication a Investigation Case via mittente email.

    Logica:
    1. Skip se già linkato a un doctype
    2. Estrai email mittente
    3. Cerca Investigation Client per email
    4. Cerca caso aperto più recente del client (status != Closed/Rejected/Archived)
    5. Linka Communication.reference_doctype/name al caso
    6. Audit log
    7. Se non trova client → crea Lead (CRM) o opens HelpDesk Ticket
    """
    if doc.communication_type != "Communication":
        return
    if doc.sent_or_received != "Received":
        return  # solo inbound
    # NB: NON saltiamo se già linkato — la pratica ha priorità su Helpdesk/CRM
    # (che girano prima e potrebbero aver linkato l'email a un HD Ticket).

    sender = _extract_email(doc.sender or "")
    if not sender:
        return

    client_name = frappe.db.get_value(
        "Investigation Client",
        {"email": sender}, "name")

    if not client_name:
        # fallback: cerca per qualsiasi Contact / User con quell'email
        user = frappe.db.get_value("User", {"email": sender}, "name")
        if user:
            client_name = frappe.db.get_value(
                "Investigation Client",
                {"platform_user": user}, "name")

    if not client_name:
        # nessun cliente noto: se Helpdesk/threading l'ha già linkato (HD Ticket),
        # lascia stare; altrimenti crea un Lead CRM.
        if not (doc.reference_doctype and doc.reference_name):
            _create_lead_from_unknown(doc, sender)
        return

    # Find latest open case for this client
    cases = frappe.get_all(
        "Investigation Case",
        filters={"client": client_name,
                 "status": ["not in", ["Closed", "Rejected", "Archived"]]},
        fields=["name", "case_title", "status"],
        order_by="creation desc",
        limit=1,
    )
    if not cases:
        # client noto ma senza caso aperto → linka comunque al client
        doc.reference_doctype = "Investigation Client"
        doc.reference_name = client_name
        doc.save(ignore_permissions=True)
        _audit("email.linked_to_client", client_name,
               {"sender": sender, "subject": doc.subject})
        return

    case_name = cases[0].name
    doc.reference_doctype = "Investigation Case"
    doc.reference_name = case_name
    doc.save(ignore_permissions=True)

    _audit("email.linked_to_case", case_name,
           {"sender": sender, "client": client_name,
            "subject": doc.subject})

    # Ensure Drive folder exists for this case (creation idempotent)
    try:
        ensure_case_folder(case_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "intel_inbox folder")

    # Deposita gli allegati dell'email nel box (cartella Drive del caso) e
    # classifica i documenti d'identità nel Vault del cliente.
    try:
        _deposit_attachments(doc, case_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "intel_inbox deposit")


# tipo documento Vault dedotto dal nome file (per gli allegati inbound)
_VAULT_HINTS = (
    ("KYB", ("visura", "kyb", "camerale", "company", "ubo")),
    ("KYC", ("carta", "identit", "passaport", "patente", "cie", "kyc", "id_")),
    ("CIS", ("cis", "casellario", "certificat")),
)


def _vault_kind_for(filename):
    n = (filename or "").lower()
    for kind, hints in _VAULT_HINTS:
        if any(h in n for h in hints):
            return kind
    return None


def _deposit_attachments(comm_doc, case_name):
    """Allegati della Communication → cartella Drive del caso (box, via
    _push_file_to_drive con dedup) + se documenti d'identità crea un Client
    Vault Item (In verifica)."""
    files = frappe.get_all("File", filters={
        "attached_to_doctype": "Communication", "attached_to_name": comm_doc.name},
        fields=["name", "file_name"])
    if not files:
        return
    from thanatos_intel.reporting.case_reports import _push_file_to_drive
    client = frappe.db.get_value("Investigation Case", case_name, "client")
    for f in files:
        frappe.db.set_value("File", f.name, {
            "attached_to_doctype": "Investigation Case", "attached_to_name": case_name})
        try:
            _push_file_to_drive(f.name, case_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "intel_inbox push")
        kind = _vault_kind_for(f.file_name)
        if client and kind and not frappe.db.exists("Client Vault Item",
                {"client": client, "title": f.file_name}):
            file_url = frappe.db.get_value("File", f.name, "file_url")
            frappe.get_doc({
                "doctype": "Client Vault Item", "client": client, "doc_kind": kind,
                "title": f.file_name, "file": file_url, "status": "In verifica",
            }).insert(ignore_permissions=True)


def _extract_email(s: str) -> str | None:
    m = EMAIL_RE.search(s or "")
    if not m:
        return None
    email = m.group(1) or m.group(2)
    return email.lower().strip() if email else None


def _create_lead_from_unknown(doc, sender: str) -> None:
    """Mittente non riconosciuto → crea Lead + HelpDesk Ticket fallback."""
    try:
        if frappe.db.exists("DocType", "Lead"):
            if not frappe.db.exists("Lead", {"email_id": sender}):
                lead = frappe.get_doc({
                    "doctype": "Lead",
                    "lead_name": (doc.sender_full_name or sender)[:140],
                    "email_id": sender,
                    "company_name": "Unknown",
                    "source": "Email",
                    "notes": f"Auto-creato da Communication {doc.name}. "
                             f"Subject: {(doc.subject or '')[:100]}",
                }).insert(ignore_permissions=True)
                doc.reference_doctype = "Lead"
                doc.reference_name = lead.name
                doc.save(ignore_permissions=True)
                _audit("email.lead_created", lead.name,
                       {"sender": sender, "subject": doc.subject})
                return
    except Exception:
        frappe.log_error(frappe.get_traceback(), "intel_inbox lead")

    # HelpDesk fallback
    try:
        if frappe.db.exists("DocType", "HD Ticket"):
            ticket = frappe.get_doc({
                "doctype": "HD Ticket",
                "subject": (doc.subject or "Untagged email")[:140],
                "description": doc.content or "",
                "raised_by": sender,
                "status": "Open",
                "via_customer_portal": 0,
            }).insert(ignore_permissions=True)
            doc.reference_doctype = "HD Ticket"
            doc.reference_name = ticket.name
            doc.save(ignore_permissions=True)
            _audit("email.ticket_created", ticket.name,
                   {"sender": sender, "subject": doc.subject})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "intel_inbox ticket")


def ensure_case_folder(case_name: str) -> str:
    """Crea (se non esiste) la folder Drive per il caso. Struttura:
       /Investigation Cases/CASE-NNN/
         ├── Evidence/
         ├── Reports/
         ├── Email/
         └── Documents/
    """
    parent = "Home"
    # Try Frappe Drive first
    if frappe.db.exists("DocType", "Drive File"):
        return _ensure_drive_folder(case_name)
    # Fallback: pure Frappe File (per app drive non installato)
    return _ensure_file_folder(case_name)


def _ensure_drive_folder(case_name: str) -> str:
    from drive.utils import get_home_folder
    from drive.api.files import create_folder

    team = frappe.conf.get("thanatos_drive_team") or frappe.db.get_value(
        "Drive Team", {"title": "Thanatos Cases"}, "name")
    if not team:
        return ""

    def ensure(title, parent):
        existing = frappe.db.get_value("Drive File", {
            "title": title, "is_group": 1, "team": team,
            "parent_entity": parent, "is_active": 1}, "name")
        return existing or create_folder(team, title, parent).name

    home = get_home_folder(team)
    cases_root = ensure("Investigation Cases", home["name"])
    case_folder = ensure(case_name, cases_root)
    for sub in ["01 Documenti Cliente", "02 Evidenze", "03 OSINT",
                "04 Blockchain", "05 Report", "06 Email"]:
        ensure(sub, case_folder)
    return case_folder


def _ensure_file_folder(case_name: str) -> str:
    """Fallback se Drive non c'è: usa Frappe File con is_folder."""
    base = f"home/investigation-cases/{case_name}"
    for folder in [
        "home/investigation-cases",
        base,
        f"{base}/evidence", f"{base}/reports",
        f"{base}/email", f"{base}/documents",
    ]:
        name = folder.replace("/", "-")
        if not frappe.db.exists("File", {"file_name": folder.split("/")[-1],
                                         "is_folder": 1}):
            try:
                frappe.get_doc({
                    "doctype": "File",
                    "file_name": folder.split("/")[-1],
                    "is_folder": 1,
                    "folder": ("/".join(folder.split("/")[:-1]) or "Home"),
                }).insert(ignore_permissions=True)
            except Exception:
                pass
    return base


def ensure_case_folder_hook(doc, method=None):
    """Wrapper called by Frappe doc_events on Investigation Case after_insert."""
    try:
        folder_id = ensure_case_folder(doc.name)
        if folder_id:
            frappe.db.set_value("Investigation Case", doc.name, "drive_folder", folder_id, update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ensure_case_folder_hook")


@frappe.whitelist()
def ensure_case_folder_api(case_name: str) -> dict:
    """API per creare/aggiornare cartella Drive da desk form."""
    frappe.has_permission("Investigation Case", "write", case_name, throw=True)
    folder_id = ensure_case_folder(case_name)
    if folder_id:
        frappe.db.set_value("Investigation Case", case_name, "drive_folder", folder_id, update_modified=False)
        frappe.db.commit()
    return {"ok": True, "folder_id": folder_id}


def _audit(event: str, ref: str, payload: dict) -> None:
    try:
        frappe.get_doc({
            "doctype": "Diplomatic Audit Log",
            "event_type": event,
            "new_value": ref,
            "reason": frappe.as_json(payload)[:500],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Investigation Report review workflow enforcement
# -----------------------------------------------------------------------------

REPORT_STATUSES = ["Draft", "Pending Review", "Approved", "Sent", "Archived"]


def before_save_report(doc, method=None):
    """Set first creation status to Draft."""
    if doc.is_new() and not doc.review_status:
        doc.review_status = "Draft"


def on_update_report(doc, method=None):
    """Block submission/email if review_status not Approved.
    Triggered by hooks on Investigation Report.
    """
    if doc.has_value_changed("review_status"):
        if doc.review_status == "Approved":
            doc.approved_by = frappe.session.user
            doc.approved_at = now_datetime()
        elif doc.review_status == "Sent" and doc.get_doc_before_save() and \
             doc.get_doc_before_save().review_status not in ("Approved", "Sent"):
            frappe.throw("Un report può essere inviato solo dopo l'approvazione del responsabile.")
