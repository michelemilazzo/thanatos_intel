"""Fascicolo del caso Thanatos (pipeline ISO).

Compila in un unico PDF: copertina brand, identità del caso, parti identificate
(entità + livello di rischio), indice documenti con verdetto di autenticità e
hash SHA-256 (catena di custodia), analisi doppia cessione, screening sanzioni/
VIES, prossimi passi (step del blueprint). In coda accoda i PDF dei documenti.
Salvato negli allegati del caso + nella cartella Drive (box dedicato).
"""
import hashlib
import io
import os

import frappe
from frappe.utils import nowdate, now_datetime

NAVY = "#0D1B3E"
GOLD = "#C8A96E"
GREY = "#5A5A5A"

_AUTH_LABEL = {"Autentico": "AUTENTICO", "Dubbio": "DUBBIO", "Manomesso": "MANOMESSO",
               "Contraffatto": "CONTRAFFATTO", "Non determinabile": "N/D"}


def _styles():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    ss = getSampleStyleSheet()
    return {
        "cell": ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica", fontSize=8, leading=10),
        "mono": ParagraphStyle("m", parent=ss["Normal"], fontName="Courier", fontSize=6.4, leading=8),
        "hd": ParagraphStyle("h", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8.2,
                             leading=10, textColor=colors.white),
        "ss": ss,
    }


def _table(rows, widths):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F3EC")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(GOLD)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _cover_and_sections(case, client, entities, docs, cessioni, screening, steps, activities=None):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    st = _styles()
    ss, CELL, MONO, HD = st["ss"], st["cell"], st["mono"], st["hd"]
    P = lambda t, s=CELL: Paragraph(t, s)

    def H(txt):
        return Paragraph(f"<font color='{NAVY}'><b>{txt}</b></font>",
                         ParagraphStyle("sec", parent=ss["Heading2"], fontSize=12,
                                        textColor=colors.HexColor(NAVY), spaceBefore=12, spaceAfter=6))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=22 * mm, bottomMargin=18 * mm)
    S = [Spacer(1, 8),
         Paragraph(f"<font color='{GOLD}'><b>THANATOS INTEL</b></font>",
                   ParagraphStyle("t", parent=ss["Title"], fontSize=22, alignment=TA_CENTER)),
         Paragraph("FASCICOLO DEL CASO",
                   ParagraphStyle("s", parent=ss["Title"], fontSize=15,
                                  textColor=colors.HexColor(NAVY), alignment=TA_CENTER)),
         Paragraph(f"{case.case_title}",
                   ParagraphStyle("st2", parent=ss["Normal"], fontSize=10,
                                  textColor=colors.HexColor(GREY), alignment=TA_CENTER, spaceAfter=10)),
         Paragraph(f"Cliente: {client} &middot; {case.name} &middot; {nowdate()}",
                   ParagraphStyle("u", parent=ss["Normal"], fontSize=9,
                                  textColor=colors.HexColor(GREY), alignment=TA_CENTER, spaceAfter=6))]

    # Identità
    S.append(H("1. Identità del caso"))
    idrows = [[P("Campo", HD), P("Valore", HD)]]
    for k, v in [("Tipo", case.case_type), ("Stato", case.status), ("Priorità", case.priority),
                 ("Apertura", str(case.opening_date or "")[:10]),
                 ("Sintesi", (case.summary or case.description or "")[:400])]:
        idrows.append([P(k), P(frappe.utils.escape_html(str(v or "-")))])
    S.append(_table(idrows, [90, 360]))

    # Parti
    S.append(H(f"2. Parti identificate ({len(entities)})"))
    prows = [[P("Tipo", HD), P("Nome", HD), P("Ruolo", HD), P("Rischio", HD)]]
    for e in entities:
        prows.append([P(e["type"]), P(frappe.utils.escape_html(e["name"])[:60]),
                      P(frappe.utils.escape_html(e["role"] or "")[:40]), P(e["risk"] or "-")])
    S.append(_table(prows, [50, 200, 140, 60]))

    # Documenti + custodia
    S.append(H(f"3. Documenti — autenticità e catena di custodia ({len(docs)})"))
    drows = [[P("#", HD), P("Documento", HD), P("Autenticità", HD), P("SHA-256", HD)]]
    for i, d in enumerate(docs, 1):
        drows.append([P(str(i)), P(frappe.utils.escape_html(d["name"])[:48]),
                      P(_AUTH_LABEL.get(d["auth"], "N/D")), P(d["hash"] or "-", MONO)])
    S.append(_table(drows, [16, 190, 80, 164]))

    # Doppia cessione
    S.append(H("4. Analisi cessioni (rilevatore doppia cessione)"))
    if cessioni:
        S.append(Paragraph(frappe.utils.escape_html(cessioni).replace("\n", "<br/>"),
                           ParagraphStyle("cz", parent=ss["Normal"], fontSize=8.5, leading=12)))
    else:
        S.append(P("Non eseguita."))

    # Screening
    S.append(H("5. Screening parti (VIES / checksum P.IVA / sanzioni)"))
    if screening:
        S.append(Paragraph(frappe.utils.escape_html(screening).replace("\n", "<br/>"),
                           ParagraphStyle("sz", parent=ss["Normal"], fontSize=8.5, leading=12)))
    else:
        S.append(P("Non eseguito."))

    # Prossimi passi
    S.append(H("6. Percorso operativo (step del caso)"))
    srows = [[P("#", HD), P("Step", HD), P("Stato", HD)]]
    for s in steps:
        srows.append([P(str(s["seq"])), P(frappe.utils.escape_html(s["label"])[:80]), P(s["status"])])
    S.append(_table(srows, [16, 360, 74]))

    # Attività e accertamenti (screening, doppia cessione, domande, analisi documenti)
    if activities:
        S.append(H(f"7. Attività investigative e accertamenti ({len(activities)})"))
        for a in activities:
            txt = (a.get("description") or "").strip()
            if not txt:
                continue
            head = f"<b>[{a.get('type') or 'Nota'}] {a.get('date') or ''}</b>"
            S.append(Paragraph(head, ParagraphStyle("ah", parent=ss["Normal"], fontSize=8.5,
                              textColor=colors.HexColor(GOLD), spaceBefore=6, spaceAfter=1)))
            S.append(Paragraph(frappe.utils.escape_html(txt).replace("\n", "<br/>"),
                              ParagraphStyle("at", parent=ss["Normal"], fontSize=8.2, leading=11)))

    S.append(Spacer(1, 12))
    S.append(Paragraph(
        "Catena di custodia: ogni documento è identificato dal proprio digest SHA-256, "
        "calcolato sul file originale; qualsiasi modifica successiva ne altera l'hash. "
        "Le valutazioni di autenticità sono indicative (analisi forense AI + metadati) e "
        "vanno confermate con perizia ove rilevante. Documento riservato al committente.",
        ParagraphStyle("disc", parent=ss["Normal"], fontName="Times-Italic", fontSize=8,
                       textColor=colors.HexColor(GREY), leading=11,
                       borderColor=colors.HexColor(GOLD), borderWidth=0.5, borderPadding=8,
                       backColor=colors.HexColor("#F8F6F0"))))

    def hf(canv, d):
        w, h = A4
        canv.saveState()
        canv.setStrokeColor(colors.HexColor(GOLD)); canv.setLineWidth(0.8)
        canv.line(18 * mm, h - 16 * mm, w - 18 * mm, h - 16 * mm)
        canv.setFont("Times-Bold", 9); canv.setFillColor(colors.HexColor(NAVY))
        canv.drawString(18 * mm, h - 13 * mm, "THANATOS · INTEL")
        canv.setFont("Helvetica", 7); canv.setFillColor(colors.HexColor(GREY))
        canv.drawRightString(w - 18 * mm, h - 13 * mm, "FASCICOLO — " + case.name)
        canv.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
        canv.drawString(18 * mm, 9 * mm, "Cliente: " + client)
        canv.drawRightString(w - 18 * mm, 9 * mm, "pag. %d" % canv.getPageNumber())
        canv.restoreState()

    doc.build(S, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()


def _recent_activity(case_name, needle):
    rows = frappe.get_all("Case Activity", filters={"parent": case_name},
                          fields=["description"], order_by="activity_date desc", limit=0)
    for r in rows:
        if needle.lower() in (r.description or "").lower():
            return r.description
    return ""


@frappe.whitelist()
def genera_fascicolo(case_name):
    """Genera il fascicolo PDF del caso (copertina + sezioni ISO + documenti uniti)."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator",
                     "Thanatos Investigator", "Thanatos Supervisor", "Thanatos Director"))
    from pypdf import PdfReader, PdfWriter
    case = frappe.get_doc("Investigation Case", case_name)
    client = (frappe.db.get_value("Investigation Client", case.client, "client_name")
              if case.client else None) or "Cliente"

    entities = []
    for ce in (case.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity,
                                 ["full_name", "entity_type", "risk_level"], as_dict=True) or {}
        entities.append({"type": et.get("entity_type") or "", "name": et.get("full_name") or ce.entity,
                         "role": ce.notes or ce.role_in_case or "", "risk": et.get("risk_level") or ""})

    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case_name},
                         fields=["evidence_name", "authenticity", "hash_value", "attached_file"],
                         order_by="creation asc", limit=0)
    docs = [{"name": (e.attached_file or e.evidence_name or "").split("/files/")[-1],
             "auth": e.authenticity or "Non determinabile", "hash": e.hash_value or "",
             "file": e.attached_file} for e in evs]

    steps = [{"seq": s.seq, "label": s.step_label or "", "status": s.status or ""}
             for s in (case.get("case_steps") or [])]

    cessioni = _recent_activity(case_name, "DOPPIA CESSIONE")
    screening = _recent_activity(case_name, "Screening automatico parti") or \
        _recent_activity(case_name, "VERIFICA PARTI")
    activities = [{"date": str(a.activity_date or "")[:16], "type": a.activity_type,
                   "description": a.description}
                  for a in (case.get("case_activities") or []) if (a.description or "").strip()]

    cover = _cover_and_sections(case, client, entities, docs, cessioni, screening, steps, activities)

    writer = PdfWriter()
    for pg in PdfReader(io.BytesIO(cover)).pages:
        writer.add_page(pg)
    merged = 0
    for d in docs:
        fu = d["file"]
        if not fu:
            continue
        try:
            path = frappe.get_site_path("private", "files", fu.split("/files/")[-1])
            if os.path.exists(path) and path.lower().endswith(".pdf"):
                for pg in PdfReader(path).pages:
                    writer.add_page(pg)
                merged += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"fascicolo merge {d['name']}")
    out = io.BytesIO(); writer.write(out); content = out.getvalue()

    fname = f"{client} - FASCICOLO - {case_name}.pdf"
    old = frappe.db.get_value("File", {"attached_to_doctype": "Investigation Case",
                                       "attached_to_name": case_name, "file_name": fname}, "name")
    if old:
        frappe.delete_doc("File", old, ignore_permissions=True, force=True)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1, "content": content,
                        "attached_to_doctype": "Investigation Case", "attached_to_name": case_name})
    f.flags.ignore_validate = True
    try:
        f.save(ignore_permissions=True)
        file_url = f.file_url
    except Exception:
        # se l'attach nativo fallisce (es. policy box), prosegui col solo Drive
        frappe.log_error(frappe.get_traceback(), "fascicolo attach")
        file_url = None
    drive_url = None
    try:
        from thanatos_intel.reporting.case_reports import _put_in_drive
        dn = _put_in_drive(case_name, fname, content, "application/pdf", client, subfolder="05 Report")
        if dn:
            drive_url = f"/drive/file/{dn}"
    except Exception:
        frappe.log_error(frappe.get_traceback(), "fascicolo drive")
    frappe.db.commit()
    return {"ok": True, "file_url": file_url, "drive_url": drive_url, "documents": merged,
            "pages": len(PdfReader(io.BytesIO(content)).pages),
            "sha256": hashlib.sha256(content).hexdigest()}
