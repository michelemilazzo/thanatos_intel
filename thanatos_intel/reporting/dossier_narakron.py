"""Dossier illustrato — CASE-2026-0011 NAR AKRON INVESTMENTS LTD / rifiuto onboarding Andaria.
Stesso template operativo del dossier illustrato (cover, gauge, flow, grafici, timeline) personalizzato sul caso.
"""
import hashlib
import io
import os

import frappe
from frappe.utils import nowdate

NAVY = "#0D1B3E"; GOLD = "#C8A96E"; RED = "#C0392B"; GREEN = "#2E7D52"; GREY = "#5A5A5A"
LOGO = "/home/frappe/bench-cli/benches/thanatos/apps/thanatos_intel/thanatos_intel/public/images/thanatos-logo-mark.png"


def _client_name(case):
    if case.client:
        return frappe.db.get_value("Investigation Client", case.client, "client_name") or case.client
    return "Cliente"


@frappe.whitelist()
def generate(case_name="CASE-2026-0011"):
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak,
                                    Table, TableStyle, Flowable)
    from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart

    navy, gold, red, green, grey = (colors.HexColor(x) for x in (NAVY, GOLD, RED, GREEN, GREY))
    case = frappe.get_doc("Investigation Case", case_name)
    client = _client_name(case)
    risk = case.risk_score_final or 75

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Times-Bold", fontSize=15, textColor=navy, spaceBefore=12, spaceAfter=6)
    BODY = ParagraphStyle("B", parent=ss["Normal"], fontName="Times-Roman", fontSize=10, leading=14, alignment=TA_JUSTIFY)
    CAP = ParagraphStyle("C", parent=ss["Normal"], fontName="Helvetica-Oblique", fontSize=8, textColor=grey, alignment=TA_CENTER, spaceBefore=2)
    BUL = ParagraphStyle("bul", parent=BODY, leftIndent=14, spaceAfter=2)

    def bullets(items):
        return [Paragraph("<font color='%s'>&bull;</font>  %s" % (GOLD, x), BUL) for x in items]

    CELL = ParagraphStyle("cell", parent=ss["Normal"], fontName="Helvetica", fontSize=8.2, leading=10.5)
    CELL_H = ParagraphStyle("cellh", parent=CELL, fontName="Helvetica-Bold", fontSize=8.4, textColor=colors.white)
    CELL_K = ParagraphStyle("cellk", parent=CELL, fontName="Helvetica-Bold", textColor=navy)
    CELL_R = ParagraphStyle("cellr", parent=CELL, textColor=red)
    CELL_KR = ParagraphStyle("cellkr", parent=CELL_K, textColor=red)

    def tbl(rows, widths, redrow=None, head=True):
        wrapped = []
        for ri, row in enumerate(rows):
            out = []
            for ci, cell in enumerate(row):
                if head and ri == 0:
                    sty = CELL_H
                elif redrow is not None and ri == redrow:
                    sty = CELL_KR if ci == 0 else CELL_R
                elif ci == 0:
                    sty = CELL_K
                else:
                    sty = CELL
                out.append(Paragraph(str(cell), sty))
            wrapped.append(out)
        t = Table(wrapped, colWidths=widths)
        sty = [("VALIGN", (0, 0), (-1, -1), "TOP"),
               ("BOX", (0, 0), (-1, -1), 0.5, gold), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F3EC")]),
               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
               ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
        if head:
            sty.append(("BACKGROUND", (0, 0), (-1, 0), navy))
        t.setStyle(TableStyle(sty)); return t

    def pie(data, labels, cols, w=240, h=150):
        d = Drawing(w, h); p = Pie(); p.x = 55; p.y = 12; p.width = 120; p.height = 120
        p.data = data; p.labels = ["%s %d%%" % (l, v) for l, v in zip(labels, data)]
        p.slices.strokeWidth = 0.5; p.slices.strokeColor = colors.white
        for i, c in enumerate(cols): p.slices[i].fillColor = c
        p.sideLabels = True; p.simpleLabels = 0; d.add(p); return d

    def vbar(values, cats, col, w=430, h=170, maxv=None, fmt="%d"):
        d = Drawing(w, h); bc = VerticalBarChart()
        bc.x = 32; bc.y = 32; bc.width = w - 55; bc.height = h - 60
        bc.data = [values]; bc.categoryAxis.categoryNames = cats; bc.bars[0].fillColor = col
        bc.valueAxis.valueMin = 0
        if maxv: bc.valueAxis.valueMax = maxv
        bc.barLabels.nudge = 8; bc.barLabelFormat = fmt; bc.barLabels.fontName = "Helvetica"; bc.barLabels.fontSize = 7
        bc.categoryAxis.labels.boxAnchor = "ne"; bc.categoryAxis.labels.angle = 25
        bc.categoryAxis.labels.fontName = "Helvetica"; bc.categoryAxis.labels.fontSize = 7
        bc.valueAxis.labels.fontName = "Helvetica"; bc.valueAxis.labels.fontSize = 7
        d.add(bc); return d

    def gauge(score):
        d = Drawing(240, 70)
        d.add(Rect(20, 30, 200, 16, fillColor=colors.HexColor("#E6E2D6"), strokeColor=None))
        col = red if score >= 61 else (gold if score >= 31 else green)
        d.add(Rect(20, 30, 2 * score, 16, fillColor=col, strokeColor=None))
        d.add(String(20, 52, "RISK SCORE", fontName="Helvetica-Bold", fontSize=8, fillColor=navy))
        d.add(String(220, 52, "%d/100" % score, fontName="Helvetica-Bold", fontSize=10, fillColor=col, textAnchor="end"))
        lab = "CRITICO" if score >= 86 else ("ALTO" if score >= 61 else ("MEDIO" if score >= 31 else "BASSO"))
        d.add(String(20, 14, lab, fontName="Helvetica", fontSize=8, fillColor=grey)); return d

    def timeline():
        # storico societario UK del titolare 2012-2026
        d = Drawing(460, 140)
        x0, x1, ya = 130, 440, 105
        y0, y1 = 2012, 2026
        def px(y):
            return x0 + (y - y0) / float(y1 - y0) * (x1 - x0)
        for y in range(y0, y1 + 1, 2):
            d.add(Line(px(y), 18, px(y), ya + 8, strokeColor=colors.HexColor("#D8D2BE"), strokeWidth=0.5))
            d.add(String(px(y), 8, str(y), fontName="Helvetica", fontSize=7, fillColor=grey, textAnchor="middle"))
        bars = [("RAFLESIA LTD (strike-off)", 2012.99, 2015.90, red),
                ("FABIANS SON LTD (strike-off)", 2019.74, 2022.08, red),
                ("NAR AKRON INVESTMENTS LTD", 2025.75, 2026.45, navy)]
        for i, (name, s, e, col) in enumerate(bars):
            yy = ya - i * 26
            d.add(String(124, yy - 3, name, fontName="Helvetica", fontSize=7, fillColor=navy, textAnchor="end"))
            d.add(Rect(px(s), yy - 7, max(px(e) - px(s), 4), 9, fillColor=col, strokeColor=navy, strokeWidth=0.4))
        d.add(String((x0 + x1) / 2, 128, "3 societa UK in 14 anni — le prime 2 cancellate d'ufficio (compulsory strike-off)",
                     fontName="Helvetica-Bold", fontSize=8, fillColor=red, textAnchor="middle"))
        return d

    def flow():
        d = Drawing(460, 240)
        def box(x, y, w, h, text, fill, tcol=colors.white, fs=8):
            d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=navy, strokeWidth=0.5, rx=4, ry=4))
            for i, line in enumerate(text.split("\n")):
                d.add(String(x + w / 2, y + h / 2 + 4 - i * 9, line, fontName="Helvetica-Bold", fontSize=fs, fillColor=tcol, textAnchor="middle"))
        import math
        def arrow(x1, y1, x2, y2):
            d.add(Line(x1, y1, x2, y2, strokeColor=gold, strokeWidth=1.2))
            a = math.atan2(y2 - y1, x2 - x1)
            d.add(Polygon([x2, y2, x2 - 6 * math.cos(a - 0.4), y2 - 6 * math.sin(a - 0.4),
                           x2 - 6 * math.cos(a + 0.4), y2 - 6 * math.sin(a + 0.4)], fillColor=gold, strokeColor=gold))
        box(10, 195, 100, 36, "NAR AKRON\nINVESTMENTS LTD", navy)
        box(135, 195, 95, 36, "Application\nconto vIBAN", colors.HexColor("#3A4668"))
        box(255, 195, 95, 36, "ANDARIA\n(EMI MFSA/FCA)", colors.HexColor("#7A5C2E"))
        box(375, 195, 75, 36, "RIFIUTO\n11/06/2026", red)
        arrow(110, 213, 135, 213); arrow(230, 213, 255, 213); arrow(350, 213, 375, 213)
        box(150, 125, 160, 28, "INTERNAL REVIEW\n(risk appetite)", colors.HexColor("#3A4668"), fs=7)
        arrow(302, 195, 245, 153); arrow(280, 139, 390, 195)
        labels = ["SIC 64999\nno FCA", "Shell GBP 1\nno storia", "Virtual office\nWC1N 3AX", "No substance\nUK", "2 strike-off\npregressi", "Link Serbia\nNar Akron doo"]
        for i, t in enumerate(labels):
            box(10 + i * 76, 45, 70, 30, t, red if i in (0, 4) else navy, fs=6.4)
            arrow(45 + i * 76, 75, 215 + (i - 2) * 6, 125)
        d.add(String(230, 20, "6 fattori del profilo confluiti nella valutazione di risk appetite dell'EMI",
                     fontName="Helvetica-Oblique", fontSize=8, fillColor=grey, textAnchor="middle"))
        return d

    class C(Flowable):
        def __init__(self, dr): self.d = dr; self.width = dr.width; self.height = dr.height
        def draw(self):
            from reportlab.graphics import renderPDF
            renderPDF.draw(self.d, self.canv, (A4[0] - 2 * 20 * mm - self.width) / 2, 0)

    def hf(canv, doc):
        w, h = A4; canv.saveState()
        canv.setStrokeColor(gold); canv.setLineWidth(0.8); canv.line(20 * mm, h - 16 * mm, w - 20 * mm, h - 16 * mm)
        canv.setFont("Times-Bold", 9); canv.setFillColor(navy); canv.drawString(20 * mm, h - 13 * mm, "THANATOS · INTEL")
        canv.setFont("Helvetica", 7); canv.setFillColor(grey); canv.drawRightString(w - 20 * mm, h - 13 * mm, "RISERVATO — " + case_name)
        canv.line(20 * mm, 14 * mm, w - 20 * mm, 14 * mm); canv.drawString(20 * mm, 9 * mm, "Cliente: " + client)
        canv.drawRightString(w - 20 * mm, 9 * mm, "Pag. %d" % doc.page); canv.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=22 * mm, bottomMargin=18 * mm, title="Dossier " + case_name)
    S = []
    # COVER
    S.append(Spacer(1, 36))
    if os.path.exists(LOGO):
        try: S.append(Image(LOGO, width=78, height=78, hAlign="CENTER"))
        except Exception: pass
    S.append(Spacer(1, 8))
    S.append(Paragraph("<font color='%s'><b>THANATOS INTEL</b></font>" % GOLD, ParagraphStyle("x", parent=ss["Title"], fontSize=26, alignment=TA_CENTER)))
    S.append(Paragraph("INVESTIGAZIONI · DUE DILIGENCE · INTELLIGENCE", ParagraphStyle("y", parent=ss["Normal"], fontSize=9, textColor=grey, alignment=TA_CENTER, spaceAfter=26)))
    S.append(Paragraph("DOSSIER INVESTIGATIVO", ParagraphStyle("z", parent=ss["Title"], fontSize=22, textColor=navy, alignment=TA_CENTER)))
    S.append(Paragraph("<font color='%s'>Rifiuto onboarding EMI — Due Diligence Companies House &amp; OSINT</font>" % RED,
                       ParagraphStyle("w", parent=ss["Normal"], fontSize=14, alignment=TA_CENTER, spaceAfter=22)))
    S.append(tbl([["Cliente", client], ["Soggetto", "NAR AKRON INVESTMENTS LTD (CH 16762394)"],
                  ["Ref. caso", case_name], ["Controparte", "Andaria Financial Services (MFSA C97170 / FCA)"],
                  ["Data", nowdate()], ["Classificazione", "CONFIDENZIALE"]], [120, 290], head=False))
    S.append(Spacer(1, 14)); S.append(C(gauge(risk))); S.append(PageBreak())

    # 1 quadro + flow
    S.append(Paragraph("1. Quadro d'insieme", H1))
    S.append(Paragraph("L'11/06/2026 (ore 12:13) Andaria Financial Services ha comunicato il rifiuto dell'onboarding di NAR AKRON "
                       "INVESTMENTS LTD citando esclusivamente il proprio <i>risk appetite</i>, senza dettaglio dei motivi — prassi AML "
                       "standard (divieto di tipping-off). La due diligence su Companies House e l'indagine OSINT ricostruiscono con "
                       "ragionevole certezza i fattori del profilo societario e personale che hanno determinato l'esito.", BODY))
    S.append(Spacer(1, 6)); S.append(C(flow()))
    S.append(Paragraph("Fig. 1 — Percorso dell'application e fattori confluiti nella internal review di Andaria.", CAP))
    S.append(PageBreak())

    # 2 KYB societa
    S.append(Paragraph("2. Profilo societario (KYB) — NAR AKRON INVESTMENTS LTD", H1))
    S.append(tbl([["Elemento", "Evidenza", "Valutazione"],
                  ["Costituzione", "03/10/2025 (8 mesi di vita)", "Nessuna storia operativa"],
                  ["Capitale sociale", "GBP 1", "Simbolico, nessuna patrimonializzazione"],
                  ["SIC", "64999 Financial intermediation n.e.c.", "Attivita finanziaria SENZA autorizzazione FCA"],
                  ["Sede legale", "27 Old Gloucester St, WC1N 3AX", "Virtual office di massa (~18.700 societa, ICIJ/Panama Papers)"],
                  ["Bilanci", "Primi conti dovuti 03/07/2027", "Nessun dato finanziario disponibile"],
                  ["Presenza web", "Nessun sito / footprint", "Attivita non riscontrabile"],
                  ["Procedure", "Nessuna (no strike-off, no Gazette)", "Posizione regolare ma vuota"]],
                 [95, 175, 200], redrow=3))
    S.append(Spacer(1, 6))
    S.append(Paragraph("La combinazione <b>SIC finanziario + nessuna licenza FCA</b> colloca la societa nella categoria "
                       "\"unregulated financial services\": per la quasi totalita degli EMI europei e una <b>categoria proibita</b> "
                       "a prescindere dagli altri elementi. Questo e, con ogni probabilita, il fattore decisivo del rifiuto.", BODY))
    S.append(PageBreak())

    # 3 fattori esclusione
    S.append(Paragraph("3. Fattori di esclusione dal risk appetite", H1))
    S.append(C(vbar([25, 25, 15, 15, 10, 10], ["SIC no FCA", "2 strike-off", "Virtual office", "No substance", "Shell GBP 1", "Link Serbia"], red, maxv=30)))
    S.append(Paragraph("Fig. 2 — Peso dei fattori di rischio rilevati (punti risk engine Thanatos).", CAP))
    S.append(Spacer(1, 4))
    S.append(C(pie([35, 40, 25], ["Regolatorio", "Struttura/substance", "Track record"], [red, navy, colors.HexColor("#B8AE90")])))
    S.append(Paragraph("Fig. 3 — Ripartizione per macro-causa del rifiuto.", CAP))
    S.append(Spacer(1, 6))
    S.extend(bullets([
        "<b>Regolatorio:</b> SIC 64999 senza autorizzazione FCA = categoria vietata per gli EMI.",
        "<b>Struttura:</b> shell di 8 mesi, GBP 1, virtual office, zero presenza web, direttore unico non residente UK.",
        "<b>Track record:</b> due precedenti societa UK del titolare cancellate d'ufficio, una senza alcun bilancio depositato.",
        "Risk score Thanatos: societa <b>75/100 (Alto)</b>, titolare <b>70/100 (Alto)</b>.",
    ]))
    S.append(PageBreak())

    # 4 titolare
    S.append(Paragraph("4. Titolare effettivo e storico societario (PSC)", H1))
    S.append(tbl([["Soggetto", "Ruolo", "Elementi"],
                  ["Gennaro Cammarota (04/1974, IT)", "Direttore, segretario e PSC unico (75%+)", "Residente in Italia; mind &amp; management fuori UK; ID verification CH dovuta entro 03/11/2026, non completata"],
                  ["RAFLESIA LTD (08341945)", "Director 2012-2015", "Dormant; compulsory strike-off 24/11/2015"],
                  ["FABIANS SON LTD (12229228)", "Director 2019-2022", "Nessun bilancio mai depositato; compulsory strike-off 01/02/2022"],
                  ["Nar Akron doo — Belgrado (RS)", "Executive Managing Director", "Fonte LinkedIn; giurisdizione extra-UE rilevante nello screening"]],
                 [135, 115, 210], redrow=3))
    S.append(Spacer(1, 6)); S.append(C(timeline()))
    S.append(Paragraph("Fig. 4 — Storico cariche UK del titolare (2012-2026).", CAP))
    S.append(Spacer(1, 6))
    S.append(Paragraph("Lo screening su sanzioni, watchlist e adverse media da fonti aperte <b>non ha prodotto alcun match</b>: "
                       "il profilo di rischio e di natura strutturale e documentale, non reputazionale-criminale. Cio rende il quadro "
                       "pienamente rimediabile con interventi societari e documentali.", BODY))
    S.append(PageBreak())

    # 5 controparte
    S.append(Paragraph("5. La controparte: Andaria Financial Services", H1))
    S.append(tbl([["Elemento", "Dettaglio"],
                  ["Entita", "Andaria Financial Services Ltd (Malta, C97170) + Andaria Financial Services UK Limited"],
                  ["Licenze", "MFSA — Financial Institutions Act art. 5 (e-money) · FCA UK"],
                  ["Modello", "E-Money/Payment Accounts (vIBAN), prevalentemente B2B"],
                  ["Interlocutori", "Kearan Hunt (onboarding); Leon Muscat in cc"],
                  ["Comunicazione", "Rifiuto 11/06/2026 12:13 — formula standard risk appetite, nessun dettaglio (no tipping-off)"]],
                 [105, 355]))
    S.append(Spacer(1, 6))
    S.append(Paragraph("Il rifiuto e una <b>decisione commerciale discrezionale non appellabile</b>: un EMI non e tenuto a motivare "
                       "ne a riesaminare. Richieste di riesame ad Andaria sono sconsigliate; l'effort va indirizzato sulla rimozione "
                       "delle cause e su istituti con appetite compatibile.", BODY))
    S.append(PageBreak())

    # 6 remediation
    S.append(Paragraph("6. Piano di remediation — cosa puo fare Thanatos", H1))
    steps = [("1. Ristrutturazione societaria", "SIC coerente con l'attivita reale (es. 64205/70100 se holding); sede con substance reale; adeguamento capitale; completamento identity verification del direttore."),
             ("2. Dossier banking-ready", "Business plan, source of funds/wealth documentata, struttura del gruppo trasparente (inclusa Nar Akron doo), KYB pack pronto per onboarding."),
             ("3. Selezione EMI compatibili", "Shortlist di istituti con risk appetite adatto a NewCo italiana/UK; preparazione e presentazione application; gestione Q&amp;A compliance."),
             ("4. Perimetro regolatorio", "Se l'attivita prevista e intermediazione finanziaria: percorso autorizzativo FCA o ridefinizione del modello per uscire dal perimetro."),
             ("5. Monitoraggio continuo", "Sorveglianza mensile su societa e titolare per prevenire nuovi rifiuti e segnalazioni.")]
    S.append(tbl([["Step", "Azione"]] + [[a, b] for a, b in steps], [150, 310]))
    S.append(Spacer(1, 8))
    S.append(Paragraph("<b>Avvertenza:</b> senza remediation, ogni nuova application presso EMI o banche ricadra negli stessi criteri "
                       "di esclusione qui documentati. Con la Fase 2 completata il profilo diventa presentabile a istituti compatibili.", BODY))
    S.append(Spacer(1, 12))
    S.append(Paragraph("Documento riservato al committente. Dati da Companies House (profilo, officers, PSC, filing history), registri "
                       "MFSA/FCA, ICIJ Offshore Leaks e fonti OSINT alla data di emissione. La trascrizione della comunicazione di rifiuto "
                       "e conservata come evidenza con impronta SHA-256 nel fascicolo del caso.",
                       ParagraphStyle("disc", parent=ss["Normal"], fontName="Times-Italic", fontSize=8, textColor=grey,
                                      borderColor=gold, borderWidth=0.5, borderPadding=8, backColor=colors.HexColor("#F8F6F0"))))

    doc.build(S, onFirstPage=hf, onLaterPages=hf)
    pdf = buf.getvalue(); sha = hashlib.sha256(pdf).hexdigest()
    fname = "%s - Dossier Illustrato - %s.pdf" % (client, case_name)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1, "content": pdf,
                        "attached_to_doctype": "Investigation Case", "attached_to_name": case_name})
    f.save(ignore_permissions=True)
    try:
        from thanatos_intel.reporting.case_reports import _put_in_drive
        _put_in_drive(case_name, fname, pdf, "application/pdf", client)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "dossier_narakron drive")
    frappe.db.commit()
    return {"file_url": f.file_url, "sha256": sha, "filename": fname}
