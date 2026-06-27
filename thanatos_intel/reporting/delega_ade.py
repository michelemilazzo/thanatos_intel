"""Generatore DELEGA Agenzia delle Entrate (riusabile per qualsiasi cliente).

Produce un PDF di delega precompilato dall'anagrafica Investigation Client per:
 - Consultazione e acquisizione delle FATTURE ELETTRONICHE (portale Fatture e Corrispettivi)
 - Consultazione del CASSETTO FISCALE
verso un intermediario indicato. Riutilizzabile passando un client diverso.
NB: bozza operativa da far validare al professionista accreditato; la delega va poi
attivata dall'intermediario sui sistemi AdE (Entratel/portale) entro i termini.
"""
import io

import frappe
from frappe.utils import nowdate, now_datetime

NAVY = "#0D1B3E"
GOLD = "#C8A96E"
GREY = "#5A5A5A"


def _client_data(client):
    c = frappe.get_doc("Investigation Client", client)
    sede = ", ".join(x for x in [c.get("res_address_line1"), c.get("res_city"),
                                 c.get("res_postal_code")] if x)
    return {
        "denominazione": c.get("client_name") or "",
        "piva": c.get("vat_number") or "",
        "cf": c.get("codice_fiscale") or c.get("vat_number") or "",
        "sede": sede or (c.get("address") or ""),
        "tipo": c.get("client_type") or "Company",
    }


@frappe.whitelist()
def genera_delega(client=None, case=None, delegato_nome="", delegato_cf="",
                  legale_rappresentante="", lr_cf="", lr_nato_a="", lr_nato_il="",
                  durata_anni=4, servizi=None):
    """Genera il PDF della delega AdE per un Investigation Client. Riusabile."""
    if not client and case:
        client = frappe.db.get_value("Investigation Case", case, "client")
    if not client:
        frappe.throw("Indicare il cliente (Investigation Client) o un caso con cliente.")
    d = _client_data(client)
    servizi = servizi or ["fatture", "cassetto"]
    if isinstance(servizi, str):
        import json
        try:
            servizi = json.loads(servizi)
        except Exception:
            servizi = [s.strip() for s in servizi.split(",")]

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=10, leading=15, alignment=TA_JUSTIFY)
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, leading=11, textColor=colors.HexColor(GREY))
    h = ParagraphStyle("h", parent=ss["Heading3"], fontSize=11, textColor=colors.HexColor(NAVY), spaceBefore=10, spaceAfter=4)

    def field(label, value):
        return Paragraph(f"<b>{label}:</b> {frappe.utils.escape_html(value) if value else '_________________________'}", body)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=22 * mm, bottomMargin=18 * mm)
    S = []
    S.append(Paragraph("DELEGA ALL'UTILIZZO DEI SERVIZI ONLINE DELL'AGENZIA DELLE ENTRATE",
                       ParagraphStyle("t", parent=ss["Title"], fontSize=13, textColor=colors.HexColor(NAVY), alignment=TA_CENTER)))
    S.append(Paragraph("Consultazione e acquisizione delle fatture elettroniche · Cassetto fiscale",
                       ParagraphStyle("st", parent=ss["Normal"], fontSize=9, textColor=colors.HexColor(GREY), alignment=TA_CENTER, spaceAfter=12)))

    S.append(Paragraph("DELEGANTE (titolare dei dati)", h))
    S.append(field("Denominazione / Nome", d["denominazione"]))
    S.append(field("Codice fiscale / Partita IVA", d["cf"] or d["piva"]))
    S.append(field("Sede / Residenza", d["sede"]))
    if (d["tipo"] or "").lower().startswith(("comp", "azienda", "law", "account")) or True:
        S.append(Paragraph("in persona del legale rappresentante:", body))
        S.append(field("Legale rappresentante", legale_rappresentante))
        S.append(field("C.F. legale rappresentante", lr_cf))
        S.append(field("Nato a / il", (lr_nato_a + (" il " + lr_nato_il if lr_nato_il else "")) if lr_nato_a else ""))

    S.append(Paragraph("DELEGA", ParagraphStyle("d", parent=ss["Heading3"], fontSize=12, textColor=colors.HexColor(GOLD), alignment=TA_CENTER, spaceBefore=10, spaceAfter=4)))
    S.append(Paragraph("DELEGATO (intermediario incaricato)", h))
    S.append(field("Nome / Studio", delegato_nome))
    S.append(field("Codice fiscale del delegato", delegato_cf))

    S.append(Paragraph("ad operare per proprio conto, presso l'Agenzia delle Entrate, "
                       "relativamente ai seguenti servizi:", body))
    items = []
    if "fatture" in servizi:
        items.append("Consultazione e acquisizione delle fatture elettroniche e dei loro "
                     "duplicati informatici (area riservata «Fatture e Corrispettivi»), inclusi "
                     "i dati delle fatture emesse e ricevute e i relativi file XML.")
    if "cassetto" in servizi:
        items.append("Consultazione del Cassetto fiscale del delegante (dichiarazioni, "
                     "versamenti F24, comunicazioni, atti, crediti d'imposta e relativo stato).")
    rows = [[Paragraph("[X]", body), Paragraph(it, body)] for it in items]
    t = Table(rows, colWidths=[22, 444])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    S.append(t)

    S.append(Spacer(1, 6))
    S.append(field("Durata della delega (anni, max consentito)", str(durata_anni)))
    S.append(Paragraph("La presente delega potrà essere revocata in qualsiasi momento. Ai sensi "
                       "del Reg. UE 2016/679, i dati sono trattati per le sole finalità connesse "
                       "all'esecuzione del mandato professionale.", small))

    S.append(Spacer(1, 16))
    S.append(field("Luogo e data", nowdate()))
    S.append(Spacer(1, 18))
    sig = Table([[Paragraph("Firma del delegante<br/><br/>______________________", body),
                  Paragraph("Firma per accettazione del delegato<br/><br/>______________________", body)]],
                colWidths=[225, 225])
    S.append(sig)
    S.append(Spacer(1, 10))
    S.append(Paragraph("Si allega copia del documento d'identità del delegante in corso di validità.", small))
    S.append(Paragraph("Documento generato da Thanatos Intel — bozza operativa da validare con "
                       "il professionista accreditato prima della trasmissione ai sistemi AdE.", small))

    def hf(canv, dc):
        w, hh = A4
        canv.saveState()
        canv.setStrokeColor(colors.HexColor(GOLD)); canv.setLineWidth(0.8)
        canv.line(20 * mm, hh - 16 * mm, w - 20 * mm, hh - 16 * mm)
        canv.setFont("Times-Bold", 9); canv.setFillColor(colors.HexColor(NAVY))
        canv.drawString(20 * mm, hh - 13 * mm, "THANATOS · INTEL")
        canv.setFont("Helvetica", 7); canv.setFillColor(colors.HexColor(GREY))
        canv.drawRightString(w - 20 * mm, hh - 13 * mm, "DELEGA AGENZIA DELLE ENTRATE")
        canv.restoreState()

    doc.build(S, onFirstPage=hf, onLaterPages=hf)
    content = buf.getvalue()

    fname = f"DELEGA AdE - {d['denominazione']}.pdf"
    attach_to = ("Investigation Case", case) if case else ("Investigation Client", client)
    old = frappe.db.get_value("File", {"attached_to_doctype": attach_to[0],
                                       "attached_to_name": attach_to[1], "file_name": fname}, "name")
    if old:
        frappe.delete_doc("File", old, ignore_permissions=True, force=True)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1, "content": content,
                        "attached_to_doctype": attach_to[0], "attached_to_name": attach_to[1]})
    f.save(ignore_permissions=True)
    if case:
        try:
            from thanatos_intel.reporting.case_reports import _put_in_drive
            _put_in_drive(case, fname, content, "application/pdf", d["denominazione"], subfolder="07 Legale")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "delega drive")
    frappe.db.commit()
    return {"ok": True, "file_url": f.file_url, "client": client}
