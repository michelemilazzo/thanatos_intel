"""Genera il fascicolo integrale del case con copertina-indice e hash SHA-256
(catena di custodia). Riutilizzabile su ogni Investigation Case (bottone).

Unisce i documenti-dossier del case in un unico PDF preceduto da una pagina
indice con il digest SHA-256 di ciascun documento; i Piani di Estrazione sono
elencati come allegati separati (non uniti). Idempotente sul nome file.
"""
import hashlib
import io
import os

import frappe
from frappe.utils import nowdate

# documenti DA UNIRE, in ordine (match per sottostringa, ultima versione)
MERGE_KEYS = [
    ("Dossier illustrato (grafici)", "Dossier Illustrato"),
    ("Dossier SBLC illustrato (organigramma)", "Dossier SBLC Illustrato"),
    ("Galleria evidenze (screenshot)", "GALLERIA Evidenze"),
    ("Dossier completo (testo)", "Dossier Completo"),
    ("KYB Due Diligence", "KYB Due Diligence"),
    ("Evidenza patrimoniale", "Evidenza patrimoniale"),
    ("Nota cliente - legale vs software", "Recupero via legale vs software"),
]
# documenti DA ELENCARE come collegati separati (non uniti)
LINK_KEYS = [("Piano di Estrazione completo", "Piano di Estrazione")]
# escludi sempre questi (per non auto-includere il fascicolo stesso)
EXCLUDE = ("INTEGRALE", "Fascicolo", "custodia", "indice")


def _latest(case_name, key):
    fs = frappe.get_all("File", filters={"attached_to_doctype": "Investigation Case",
                                         "attached_to_name": case_name,
                                         "file_name": ["like", "%" + key + "%"]},
                        fields=["file_name", "file_url", "is_private"], order_by="creation desc")
    for f in fs:
        if any(x.lower() in f.file_name.lower() for x in EXCLUDE):
            continue
        p = frappe.get_site_path("private" if f.is_private else "public", "files",
                                 f.file_url.split("/files/")[-1])
        if os.path.exists(p):
            return p
    return None


def _meta(path):
    from pypdf import PdfReader
    data = open(path, "rb").read()
    return data, hashlib.sha256(data).hexdigest(), len(PdfReader(io.BytesIO(data)).pages)


def _cover(case_name, client, title, components, linked):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    NAVY = colors.HexColor("#0D1B3E"); GOLD = colors.HexColor("#C8A96E"); GREY = colors.HexColor("#5A5A5A")
    ss = getSampleStyleSheet()
    CELL = ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    MONO = ParagraphStyle("m", parent=ss["Normal"], fontName="Courier", fontSize=6.6, leading=8)
    HD = ParagraphStyle("h", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8.2, leading=10, textColor=colors.white)

    def htable(rows, widths):
        t = Table(rows, colWidths=widths)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F3EC")]),
            ("BOX", (0, 0), (-1, -1), 0.5, GOLD), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm)
    S = [Spacer(1, 10),
         Paragraph("<font color='#C8A96E'><b>THANATOS INTEL</b></font>", ParagraphStyle("t", parent=ss["Title"], fontSize=22, alignment=TA_CENTER)),
         Paragraph(title, ParagraphStyle("s", parent=ss["Title"], fontSize=15, textColor=NAVY, alignment=TA_CENTER, spaceAfter=2)),
         Paragraph("Indice e catena di custodia — %s &middot; %s &middot; %s" % (client, case_name, nowdate()),
                   ParagraphStyle("u", parent=ss["Normal"], fontSize=9, textColor=GREY, alignment=TA_CENTER, spaceAfter=16))]
    rows = [[Paragraph("#", HD), Paragraph("Documento / sezione", HD), Paragraph("Pag.", HD), Paragraph("SHA-256", HD)]]
    for i, (name, sha, pg) in enumerate(components, 1):
        rows.append([Paragraph(str(i), CELL), Paragraph(name, CELL), Paragraph(str(pg), CELL), Paragraph(sha, MONO)])
    S.append(htable(rows, [18, 150, 28, 250]))
    if linked:
        S.append(Spacer(1, 10)); S.append(Paragraph("<b>Documenti collegati (fascicolo separato):</b>", CELL))
        lr = [[Paragraph("Documento", HD), Paragraph("Pag.", HD), Paragraph("SHA-256", HD)]]
        for name, sha, pg in linked:
            lr.append([Paragraph(name, CELL), Paragraph(str(pg), CELL), Paragraph(sha, MONO)])
        S.append(htable(lr, [170, 28, 248]))
    S.append(Spacer(1, 14))
    S.append(Paragraph("Catena di custodia: ogni documento e identificato dal proprio digest crittografico SHA-256, calcolato sul file PDF originale. Qualsiasi modifica successiva al file ne altera l'hash, rendendo l'alterazione rilevabile. Documento riservato al committente.",
                       ParagraphStyle("d", parent=ss["Normal"], fontName="Times-Italic", fontSize=8.5, textColor=GREY, leading=12,
                                      borderColor=GOLD, borderWidth=0.5, borderPadding=8, backColor=colors.HexColor("#F8F6F0"))))

    def hf(canv, d):
        w, h = A4; canv.saveState(); canv.setStrokeColor(GOLD); canv.setLineWidth(0.8); canv.line(18 * mm, h - 16 * mm, w - 18 * mm, h - 16 * mm)
        canv.setFont("Times-Bold", 9); canv.setFillColor(NAVY); canv.drawString(18 * mm, h - 13 * mm, "THANATOS · INTEL")
        canv.setFont("Helvetica", 7); canv.setFillColor(GREY); canv.drawRightString(w - 18 * mm, h - 13 * mm, "CATENA DI CUSTODIA — " + case_name)
        canv.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm); canv.drawString(18 * mm, 9 * mm, "Cliente: " + client); canv.drawRightString(w - 18 * mm, 9 * mm, "Indice"); canv.restoreState()
    doc.build(S, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()


@frappe.whitelist()
def generate_custody_dossier(case_name):
    """Unisce i documenti del case in un fascicolo integrale con indice+SHA-256."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    from pypdf import PdfWriter, PdfReader
    case = frappe.get_doc("Investigation Case", case_name)
    client = (frappe.db.get_value("Investigation Client", case.client, "client_name")
              if case.client else None) or "Cliente"

    parts, metas = [], []
    for label, key in MERGE_KEYS:
        p = _latest(case_name, key)
        if not p:
            continue
        data, sha, pg = _meta(p)
        parts.append(p); metas.append((label, sha, pg))
    if not parts:
        frappe.throw("Nessun documento-dossier trovato da unire per questo case.")
    linked = []
    for label, key in LINK_KEYS:
        p = _latest(case_name, key)
        if p:
            _, sha, pg = _meta(p)
            linked.append((label, sha, pg))

    title = "DOSSIER INTEGRALE (catena di custodia)"
    cov = _cover(case_name, client, title, metas, linked)
    w = PdfWriter()
    for pg in PdfReader(io.BytesIO(cov)).pages:
        w.add_page(pg)
    for p in parts:
        for pg in PdfReader(p).pages:
            w.add_page(pg)
    b = io.BytesIO(); w.write(b); content = b.getvalue()

    fname = "%s - DOSSIER INTEGRALE (custodia) - %s.pdf" % (client, case_name)
    old = frappe.db.get_value("File", {"attached_to_doctype": "Investigation Case",
                                       "attached_to_name": case_name, "file_name": fname}, "name")
    if old:
        frappe.delete_doc("File", old, ignore_permissions=True, force=True)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1, "content": content,
                        "attached_to_doctype": "Investigation Case", "attached_to_name": case_name})
    f.save(ignore_permissions=True)
    try:
        from thanatos_intel.reporting.case_reports import _put_in_drive
        _put_in_drive(case_name, fname, content, "application/pdf", client, subfolder="05 Report")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "custody drive")
    frappe.db.commit()
    return {"file_url": f.file_url, "merged": len(parts), "linked": len(linked),
            "pages": len(PdfReader(io.BytesIO(content)).pages),
            "sha256": hashlib.sha256(content).hexdigest()}
