"""Genera PDF Agency Mandate.

Usa mandate_body (HTML editato dall'operatore) come corpo,
avvolto nel layout grafico del print format (header, footer, CSS).
"""
import frappe
from frappe.utils.pdf import get_pdf

PRINT_FORMAT = "Mandato d'Incarico"

PDF_OPTIONS = {
    "margin-top": "22mm",
    "margin-bottom": "28mm",
    "margin-left": "18mm",
    "margin-right": "18mm",
    "page-size": "A4",
    "encoding": "UTF-8",
    "enable-local-file-access": "",
}


def _build_full_html(doc) -> str:
    """Assembla HTML completo: chrome del print format + mandate_body editato."""
    # Recupera il print format come wrapper grafico
    pf_html = frappe.get_print(
        doctype="Agency Mandate",
        name=doc.name,
        print_format=PRINT_FORMAT,
        as_pdf=False,
    )
    return pf_html


@frappe.whitelist()
def generate(mandate_name: str) -> dict:
    """Genera PDF e lo allega al mandato. Restituisce {"ok": True, "file_url": "..."}"""
    m = frappe.get_doc("Agency Mandate", mandate_name)

    try:
        html = _build_full_html(m)
    except Exception:
        # fallback headless (es. da background/console dove printview non e' disponibile)
        body = m.mandate_body or ""
        html = ("<html><head><meta charset='utf-8'><style>"
                "body{font-family:Helvetica,Arial,sans-serif;font-size:11pt;color:#222;margin:0}"
                "h1{color:#C8A96E;text-align:center} h2{color:#0D1B3E}"
                ".parties-box{display:flex;gap:24px;margin:10px 0} .party-block{flex:1}"
                ".clause{margin:10px 0} .clause-num{font-weight:bold;color:#0D1B3E}"
                ".fee-table{width:100%;border-collapse:collapse} .fee-table td,.fee-table th{border:1px solid #ccc;padding:4px} .small{font-size:9pt;color:#555}"
                "</style></head><body><h1>THANATOS INTEL</h1>"
                "<h2 style='text-align:center'>MANDATO D'INCARICO</h2>" + body + "</body></html>")
    pdf_bytes = get_pdf(html, options=PDF_OPTIONS)

    filename = f"{mandate_name}.pdf"
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": filename,
        "content": pdf_bytes,
        "is_private": 1,
        "attached_to_doctype": "Agency Mandate",
        "attached_to_name": mandate_name,
    })
    file_doc.flags.ignore_permissions = True
    file_doc.save(ignore_permissions=True)

    m.db_set("mandate_pdf", file_doc.file_url, update_modified=False)
    frappe.db.commit()

    return {"ok": True, "file_url": file_doc.file_url}


@frappe.whitelist()
def generate_mandate_pdf(mandate_name: str) -> dict:
    return generate(mandate_name)


@frappe.whitelist()
def preview_html(mandate_name: str) -> str:
    m = frappe.get_doc("Agency Mandate", mandate_name)
    return _build_full_html(m)
