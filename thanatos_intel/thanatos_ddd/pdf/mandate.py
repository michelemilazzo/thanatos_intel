"""Genera PDF Agency Mandate tramite Frappe Print Format (wkhtmltopdf/Chromium).

Fallback a reportlab se wkhtmltopdf non è disponibile.
"""
import frappe
from frappe.utils.pdf import get_pdf

PRINT_FORMAT = "Mandato d'Incarico"


@frappe.whitelist()
def generate(mandate_name: str) -> dict:
    """Genera PDF dal Print Format e lo allega al mandato.
    Restituisce {"ok": True, "file_url": "..."}
    """
    m = frappe.get_doc("Agency Mandate", mandate_name)

    # Genera HTML dal Print Format
    html = frappe.get_print(
        doctype="Agency Mandate",
        name=mandate_name,
        print_format=PRINT_FORMAT,
        as_pdf=False,
    )

    # Converti in PDF
    pdf_bytes = get_pdf(html, options={
        "margin-top": "22mm",
        "margin-bottom": "28mm",
        "margin-left": "18mm",
        "margin-right": "18mm",
        "page-size": "A4",
        "encoding": "UTF-8",
        "enable-local-file-access": "",
    })

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
    """Alias whitelisted usato dal JS del form."""
    return generate(mandate_name)


@frappe.whitelist()
def preview_html(mandate_name: str) -> str:
    """Restituisce l'HTML del print format per anteprima."""
    return frappe.get_print(
        doctype="Agency Mandate",
        name=mandate_name,
        print_format=PRINT_FORMAT,
        as_pdf=False,
    )
