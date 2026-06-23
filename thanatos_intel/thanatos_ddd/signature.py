"""Firma elettronica nativa eIDAS SES (Simple Electronic Signature).

Flow:
1. Cliente firma su canvas HTML5 (signature_pad.js)
2. POST signature_image (base64 PNG) → backend
3. Backend re-stampa il PDF del Mandato con:
   - immagine firma (signature pad)
   - timestamp + IP + User-Agent
   - hash SHA256 del PDF originale
4. Hash del PDF firmato + audit log immutabile
"""
import base64
import hashlib
import io
import frappe
from thanatos_intel.thanatos_ddd.portal_acl import can_access_mandate
from frappe.utils import now_datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors


def _client_ip():
    try:
        return frappe.local.request.headers.get("X-Forwarded-For") \
            or frappe.local.request.remote_addr
    except Exception:
        return "n/a"


def _ua():
    try:
        return frappe.local.request.headers.get("User-Agent", "")[:200]
    except Exception:
        return ""


def _stamp_signature(original_pdf_path: str, sig_png: bytes,
                     signer_name: str, ip: str, ua: str,
                     orig_hash: str) -> bytes:
    """Aggiunge una pagina di firma in coda al PDF originale."""
    # Usa pypdf per concat + reportlab per generare la pagina firma
    import pypdf
    base = pypdf.PdfReader(original_pdf_path)
    writer = pypdf.PdfWriter()
    for p in base.pages:
        writer.add_page(p)

    # Pagina di firma generata con ReportLab
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFillColor(colors.HexColor("#0A0E1A"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, 27*cm, "FIRMA ELETTRONICA / ELECTRONIC SIGNATURE")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    c.drawString(2*cm, 26.2*cm,
                 "Tipologia: eIDAS SES (Simple Electronic Signature)")
    c.drawString(2*cm, 25.7*cm, f"Firmatario: {signer_name}")
    c.drawString(2*cm, 25.2*cm, f"Data/ora: {now_datetime():%Y-%m-%d %H:%M:%S} UTC+1")
    c.drawString(2*cm, 24.7*cm, f"IP: {ip}")
    c.drawString(2*cm, 24.2*cm, f"User-Agent: {ua}")
    c.drawString(2*cm, 23.7*cm, f"SHA256 del documento (pre-firma): {orig_hash}")

    # Immagine firma
    if sig_png:
        from reportlab.lib.utils import ImageReader
        img = ImageReader(io.BytesIO(sig_png))
        c.setStrokeColor(colors.HexColor("#c8a96e"))
        c.rect(2*cm, 17*cm, 16*cm, 5*cm, stroke=1, fill=0)
        c.drawImage(img, 2.2*cm, 17.2*cm, width=15.6*cm, height=4.6*cm,
                    preserveAspectRatio=True, mask="auto")

    c.setFillColor(colors.HexColor("#7a1c1c"))
    c.setFont("Helvetica", 7.5)
    c.drawString(2*cm, 16*cm,
        "Thanatos performs investigative, due diligence, compliance and "
        "eligibility assessment services only. Thanatos does NOT issue,")
    c.drawString(2*cm, 15.6*cm,
        "sell, broker or guarantee diplomatic, consular, governmental or "
        "identity documents.")
    c.save()
    buf.seek(0)

    sig_pdf = pypdf.PdfReader(buf)
    for p in sig_pdf.pages:
        writer.add_page(p)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@frappe.whitelist(methods=["POST"])
def sign_mandate(mandate: str, signature_base64: str,
                 signer_name: str = None) -> dict:
    if not can_access_mandate(mandate):
        frappe.throw("Non sei autorizzato per questo mandato", frappe.PermissionError)
    if not signature_base64:
        frappe.throw("Firma mancante")
    m = frappe.get_doc("Agency Mandate", mandate)
    if not m.mandate_pdf:
        frappe.throw("PDF mandato non generato — eseguire prima la generazione")
    if m.status in ("Signed", "Active", "Completed"):
        frappe.throw(f"Mandato già firmato ({m.status})")

    site_path = frappe.get_site_path("private", "files",
        m.mandate_pdf.split("/private/files/")[-1])

    # Hash originale
    with open(site_path, "rb") as f:
        orig_bytes = f.read()
    orig_hash = hashlib.sha256(orig_bytes).hexdigest()

    # Decode signature
    if "," in signature_base64:
        signature_base64 = signature_base64.split(",", 1)[1]
    sig_png = base64.b64decode(signature_base64)

    applicant_name = signer_name
    if not applicant_name and m.applicant:
        applicant_name = frappe.db.get_value("Applicant Profile",
                                             m.applicant, "full_legal_name")

    signed_bytes = _stamp_signature(site_path, sig_png,
                                    applicant_name or frappe.session.user,
                                    _client_ip(), _ua(), orig_hash)
    signed_hash = hashlib.sha256(signed_bytes).hexdigest()

    fdoc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"{m.name}-SIGNED.pdf",
        "is_private": 1,
        "content": signed_bytes,
        "attached_to_doctype": "Agency Mandate",
        "attached_to_name": m.name,
    })
    fdoc.save(ignore_permissions=True)

    m.mandate_pdf = fdoc.file_url
    m.status = "Signed"
    m.signed_on = frappe.utils.today()
    m.signature_ref = f"SES:{signed_hash[:16]}"
    m.save(ignore_permissions=True)

    if m.ddd_case:
        frappe.get_doc({
            "doctype": "Diplomatic Audit Log",
            "ddd_case": m.ddd_case,
            "ts": now_datetime(),
            "user": frappe.session.user,
            "event_type": "Decision",
            "old_value": "Pending Signature",
            "new_value": "Signed (SES)",
            "reason": f"orig={orig_hash[:16]} signed={signed_hash[:16]} "
                      f"ip={_client_ip()}",
            "ip": _client_ip(),
        }).insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "mandate": m.name, "status": m.status,
        "signed_pdf": fdoc.file_url,
        "original_hash": orig_hash, "signed_hash": signed_hash,
        "ses_level": "eIDAS SES",
        "ip": _client_ip(),
    }
