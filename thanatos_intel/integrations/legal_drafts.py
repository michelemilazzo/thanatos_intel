"""Bozze legali del caso come writer condivisi (Frappe Drive Document).

Le bozze (BOZZA_/MODELLO_/NOTA_ *.txt) allegate al caso vengono materializzate
come Drive Document collaborativi nella sottocartella Drive "07 Legale" del caso
(quindi nel box + condivisibili). Il portale le mostra come link che aprono il
writer: /drive/document/<entity>.
"""
import frappe
from frappe.utils import escape_html

# keyword nel nome file -> (destinatario, scopo) per ricostruire la tabella
_DRAFT_META = [
    ("hostinger", "abuse@hostinger.com", "Preservazione + takedown sito fake"),
    ("wix", "Wix Trust & Safety", "Preservazione + takedown sito collegato"),
    ("google", "Google LERS", "Preservazione mailbox collegata"),
    ("kraken", "le@kraken.com", "Preservazione + freeze + KYC account di cash-out"),
    ("eio", "Legale del cliente", "Come instradare le richieste internazionali"),
    ("mlat", "Legale del cliente", "Come instradare le richieste internazionali"),
    ("querela", "Polizia Postale / GdF", "Struttura della querela + elementi allegati"),
]


def _meta_for(filename):
    low = filename.lower()
    for kw, dest, scopo in _DRAFT_META:
        if kw in low:
            return dest, scopo
    return "", ""


def _is_draft(filename):
    low = (filename or "").lower()
    return low.endswith(".txt") and (
        low.startswith("bozza") or low.startswith("modello") or low.startswith("nota_"))


def _txt_to_html(text):
    paras = [escape_html(line) if line.strip() else "&nbsp;" for line in (text or "").splitlines()]
    return "<p>" + "</p><p>".join(paras) + "</p>" if paras else "<p></p>"


def _legale_subfolder(case):
    folder = case.get("drive_folder")
    if not folder or not frappe.db.exists("Drive File", folder):
        return None, None
    team = frappe.db.get_value("Drive File", folder, "team")
    sub = frappe.db.get_value(
        "Drive File", {"title": "07 Legale", "parent_entity": folder, "is_group": 1}, "name")
    return (sub or folder), team


def ensure_legal_writers(case_name):
    """Crea i Drive Document mancanti dalle bozze del caso. Idempotente."""
    case = frappe.get_doc("Investigation Case", case_name)
    sub, team = _legale_subfolder(case)
    if not sub:
        return []
    from drive.api.files import create_document_entity

    drafts = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Investigation Case", "attached_to_name": case_name},
        fields=["name", "file_name"])
    created = []
    for f in drafts:
        if not _is_draft(f.file_name):
            continue
        title = f.file_name.rsplit(".", 1)[0]
        if frappe.db.exists("Drive File", {"title": title, "parent_entity": sub, "mime_type": "frappe_doc"}):
            continue
        try:
            text = frappe.get_doc("File", f.name).get_content()
            if isinstance(text, bytes):
                text = text.decode("utf-8", "replace")
            ent = create_document_entity(team, title=title, parent=sub)
            ename = ent.get("name") if isinstance(ent, dict) else ent.name
            docname = frappe.db.get_value("Drive File", ename, "document")
            if docname:
                # raw_content = HTML iniziale; content(yjs) azzerato così l'editor
                # collaborativo fa seeding dal raw_content (altrimenti lo stato yjs
                # vuoto di create_document_entity vince e il writer appare bianco).
                frappe.db.set_value("Drive Document", docname,
                                    {"raw_content": _txt_to_html(text), "content": None})
            created.append(ename)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "legal_drafts.ensure")
    if created:
        frappe.db.commit()
    return created


@frappe.whitelist()
def list_legal_writers(case_name):
    """Bozze legali del caso come link al writer (crea i mancanti, poi elenca)."""
    from thanatos_intel.workflow.api import _can_see_case
    if not _can_see_case(case_name):
        frappe.throw("Accesso negato.", frappe.PermissionError)
    ensure_legal_writers(case_name)
    case = frappe.get_doc("Investigation Case", case_name)
    sub, _team = _legale_subfolder(case)
    if not sub:
        return []
    rows = frappe.get_all(
        "Drive File",
        filters={"parent_entity": sub, "mime_type": "frappe_doc"},
        fields=["name", "title"], order_by="title")
    out = []
    for r in rows:
        dest, scopo = _meta_for(r.title)
        out.append({"title": r.title, "url": f"/drive/document/{r.name}",
                    "destinatario": dest, "scopo": scopo})
    return out
