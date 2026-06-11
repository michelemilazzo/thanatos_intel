"""Dossier illustrato Thanatos — copertina, grafici (torta/barre/gauge) e
diagramma di flusso della rete. PDF brandizzato, in Drive con tag cliente.
"""
import hashlib
import io
import os

import frappe
from frappe.utils import now_datetime, nowdate

NAVY = "#0D1B3E"
GOLD = "#C8A96E"
RED = "#C0392B"
GREEN = "#2E7D52"
GREY = "#5A5A5A"
LOGO = "/home/frappe/bench-cli/benches/thanatos/apps/thanatos_intel/thanatos_intel/public/images/thanatos-logo-mark.png"


def _client_name(case):
    if case.client:
        return frappe.db.get_value("Investigation Client", case.client, "client_name") or case.client
    return "Cliente"


@frappe.whitelist()
def generate_visual_dossier(case_name):
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak,
                                    Table, TableStyle, Flowable)
    from reportlab.graphics.shapes import Drawing, Rect, String, PolyLine, Line, Polygon
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart

    navy, gold, red, green, grey = (colors.HexColor(x) for x in (NAVY, GOLD, RED, GREEN, GREY))
    case = frappe.get_doc("Investigation Case", case_name)
    client = _client_name(case)
    risk = case.risk_score_final or 0

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Times-Bold", fontSize=15, textColor=navy, spaceBefore=14, spaceAfter=6)
    BODY = ParagraphStyle("B", parent=ss["Normal"], fontName="Times-Roman", fontSize=10, leading=14, alignment=TA_JUSTIFY)
    CAP = ParagraphStyle("C", parent=ss["Normal"], fontName="Helvetica-Oblique", fontSize=8, textColor=grey, alignment=TA_CENTER, spaceBefore=2)

    # ---- chart helpers ----
    def pie_chart(data, labels, cols):
        d = Drawing(240, 150)
        p = Pie(); p.x = 60; p.y = 15; p.width = 120; p.height = 120
        p.data = data; p.labels = ["%s %d%%" % (l, v) for l, v in zip(labels, data)]
        p.slices.strokeWidth = 0.5; p.slices.strokeColor = colors.white
        for i, c in enumerate(cols):
            p.slices[i].fillColor = c
        p.sideLabels = True; p.simpleLabels = 0
        d.add(p)
        return d

    def bar_chart(values, cats, col, w=420, h=160, maxv=None):
        d = Drawing(w, h)
        bc = VerticalBarChart()
        bc.x = 30; bc.y = 30; bc.width = w - 50; bc.height = h - 55
        bc.data = [values]; bc.categoryAxis.categoryNames = cats
        bc.bars[0].fillColor = col
        bc.valueAxis.valueMin = 0
        if maxv: bc.valueAxis.valueMax = maxv
        bc.categoryAxis.labels.boxAnchor = "ne"; bc.categoryAxis.labels.angle = 30
        bc.categoryAxis.labels.fontName = "Helvetica"; bc.categoryAxis.labels.fontSize = 7
        bc.valueAxis.labels.fontName = "Helvetica"; bc.valueAxis.labels.fontSize = 7
        d.add(bc)
        return d

    def gauge(score):
        d = Drawing(240, 70)
        d.add(Rect(20, 30, 200, 16, fillColor=colors.HexColor("#E6E2D6"), strokeColor=None))
        col = red if score >= 61 else (gold if score >= 31 else green)
        d.add(Rect(20, 30, 2 * score, 16, fillColor=col, strokeColor=None))
        d.add(String(20, 52, "RISK SCORE", fontName="Helvetica-Bold", fontSize=8, fillColor=navy))
        d.add(String(220, 52, "%d/100" % score, fontName="Helvetica-Bold", fontSize=10, fillColor=col, textAnchor="end"))
        lab = "CRITICO" if score >= 86 else ("ALTO" if score >= 61 else ("MEDIO" if score >= 31 else "BASSO"))
        d.add(String(20, 14, lab, fontName="Helvetica", fontSize=8, fillColor=grey))
        return d

    def flow_diagram():
        d = Drawing(460, 250)
        def box(x, y, w, h, text, fill, tcol=colors.white, fs=8):
            d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=navy, strokeWidth=0.5, rx=4, ry=4))
            for i, line in enumerate(text.split("\n")):
                d.add(String(x + w / 2, y + h / 2 + 4 - i * 9, line, fontName="Helvetica-Bold",
                             fontSize=fs, fillColor=tcol, textAnchor="middle"))
        def arrow(x1, y1, x2, y2):
            d.add(Line(x1, y1, x2, y2, strokeColor=gold, strokeWidth=1.2))
            import math
            ang = math.atan2(y2 - y1, x2 - x1)
            d.add(Polygon([x2, y2, x2 - 6 * math.cos(ang - 0.4), y2 - 6 * math.sin(ang - 0.4),
                           x2 - 6 * math.cos(ang + 0.4), y2 - 6 * math.sin(ang + 0.4)], fillColor=gold, strokeColor=gold))
        box(10, 200, 90, 34, "VITTIMA\nDarbesio", green)
        box(120, 200, 100, 34, "bitcoinbot.tech\n(piattaforma fake)", red)
        box(245, 200, 95, 34, "Wallet raccolta\n1F1LW5x", navy)
        box(360, 200, 90, 34, "Electrum\nwallet_1", colors.HexColor("#7A5C2E"))
        arrow(100, 217, 120, 217); arrow(220, 217, 245, 217); arrow(340, 217, 360, 217)
        # hubs
        box(150, 130, 160, 30, "3 HUB di consolidamento (>50 BTC)", colors.HexColor("#3A4668"))
        arrow(292, 200, 250, 162)
        # exchanges
        exs = ["Kraken", "Binance", "Bitstamp", "MEXC", "hitbtc (risky)"]
        ex_cols = [navy, navy, navy, navy, red]
        for i, (e, c) in enumerate(zip(exs, ex_cols)):
            box(10 + i * 92, 60, 86, 28, e, c, fs=7)
            arrow(230, 130, 53 + i * 92, 88)
        d.add(String(230, 35, "CASH-OUT su exchange — recupero solo via richiesta legale (KYC)",
                     fontName="Helvetica-Oblique", fontSize=8, fillColor=grey, textAnchor="middle"))
        return d

    class Centered(Flowable):
        def __init__(self, drawing): self.d = drawing; self.width = drawing.width; self.height = drawing.height
        def draw(self):
            from reportlab.graphics import renderPDF
            renderPDF.draw(self.d, self.canv, (A4[0] - 2 * 22 * mm - self.width) / 2, 0)

    def hf(canv, doc):
        w, h = A4
        canv.saveState()
        canv.setStrokeColor(gold); canv.setLineWidth(0.8)
        canv.line(20 * mm, h - 16 * mm, w - 20 * mm, h - 16 * mm)
        canv.setFont("Times-Bold", 9); canv.setFillColor(navy)
        canv.drawString(20 * mm, h - 13 * mm, "THANATOS · INTEL")
        canv.setFont("Helvetica", 7); canv.setFillColor(grey)
        canv.drawRightString(w - 20 * mm, h - 13 * mm, "RISERVATO — " + case_name)
        canv.line(20 * mm, 14 * mm, w - 20 * mm, 14 * mm)
        canv.drawString(20 * mm, 9 * mm, "Cliente: " + client)
        canv.drawRightString(w - 20 * mm, 9 * mm, "Pag. %d" % doc.page)
        canv.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=22 * mm, bottomMargin=18 * mm, title="Dossier " + case_name)
    story = []
    # COVER
    story.append(Spacer(1, 40))
    if os.path.exists(LOGO):
        try:
            story.append(Image(LOGO, width=80, height=80, hAlign="CENTER"))
        except Exception:
            pass
    story.append(Spacer(1, 10))
    story.append(Paragraph("<font color='%s'><b>THANATOS INTEL</b></font>" % GOLD,
                           ParagraphStyle("x", parent=ss["Title"], fontName="Times-Bold", fontSize=26, alignment=TA_CENTER)))
    story.append(Paragraph("INVESTIGAZIONI · DUE DILIGENCE · INTELLIGENCE",
                           ParagraphStyle("y", parent=ss["Normal"], fontSize=9, textColor=grey, alignment=TA_CENTER, spaceAfter=30)))
    story.append(Paragraph("DOSSIER INVESTIGATIVO", ParagraphStyle("z", parent=ss["Title"], fontSize=22, textColor=navy, alignment=TA_CENTER)))
    story.append(Paragraph("<font color='%s'>Frode SBLC + Crypto Investment Scam</font>" % RED,
                           ParagraphStyle("w", parent=ss["Normal"], fontSize=14, alignment=TA_CENTER, spaceAfter=24)))
    cover = Table([["Cliente", client], ["Ref. caso", case_name], ["Investigatore", case.assigned_investigator or "-"],
                   ["Data", nowdate()], ["Classificazione", "CONFIDENZIALE"]], colWidths=[120, 250])
    cover.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                               ("TEXTCOLOR", (0, 0), (0, -1), navy), ("BOX", (0, 0), (-1, -1), 0.5, gold),
                               ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(cover)
    story.append(Spacer(1, 16))
    story.append(Centered(gauge(risk)))
    story.append(PageBreak())

    # 1 Sommario + flow
    story.append(Paragraph("1. Quadro d'insieme", H1))
    story.append(Paragraph(
        "Schema criminale doppio: frode SBLC (advance-fee, veicolo SG Finance &amp; Trading Ltd) e crypto investment scam "
        "(piattaforma fake bitcoinbot.tech). I fondi della vittima sono transitati da un wallet di raccolta attraverso 3 hub "
        "di consolidamento fino al cash-out su exchange. Di seguito la mappa del flusso.", BODY))
    story.append(Spacer(1, 6))
    story.append(Centered(flow_diagram()))
    story.append(Paragraph("Fig. 1 — Flusso dei fondi: vittima → piattaforma → wallet di raccolta → hub → exchange.", CAP))
    story.append(PageBreak())

    # 2 Destinazione fondi (pie)
    story.append(Paragraph("2. Destinazione finale dei fondi", H1))
    story.append(Centered(pie_chart([42, 6, 52], ["Exchange/custodia", "Wallet fermi", "Peel/dust"],
                                     [navy, green, colors.HexColor("#B8AE90")])))
    story.append(Paragraph("Fig. 2 — Ripartizione del flusso tracciato (value-weighted).", CAP))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<b>Il grosso dei fondi è confluito nella custodia di exchange centralizzati</b> — Kraken, Bitstamp, Binance, MEXC e "
        "l'exchange a rischio hitbtc-unionchain.ai. Non esiste un wallet che trattenga importi significativi: <b>il sequestro "
        "on-chain non è praticabile, il recupero passa per la richiesta legale agli exchange</b> (KYC dei titolari del cash-out).", BODY))
    story.append(Spacer(1, 6))
    ex_tbl = Table([["Exchange", "Ruolo", "Recupero"],
                    ["Kraken (5 indirizzi)", "Cash-out, regolamentato", "Subpoena/EIO — UK/IE/US"],
                    ["Binance", "Cash-out, regolamentato", "EIO/MLAT"],
                    ["Bitstamp", "Cash-out, regolamentato", "EIO — UK/EU"],
                    ["MEXC", "Cash-out (8.999 BTC hot)", "Richiesta diretta/MLAT"],
                    ["hitbtc-unionchain.ai", "Exchange A RISCHIO (AML 60)", "Probabile non-cooperativo — segnalare"]],
                   colWidths=[140, 170, 150])
    ex_tbl.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                                ("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F3EC")]),
                                ("TEXTCOLOR", (0, 5), (-1, 5), red), ("BOX", (0, 0), (-1, -1), 0.5, gold),
                                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(ex_tbl)
    story.append(PageBreak())

    # 3 Rete + VT bar
    story.append(Paragraph("3. Rete di truffe collegata", H1))
    story.append(Paragraph(
        "Il reverse-IP dell'hosting ha rivelato una rete coordinata: piattaforme fake, finte banche, finti regolatori "
        "(FCA, NCA, BCE, FIU) e truffe di recupero fondi. VirusTotal conferma i nodi operativi; i finti-istituzionali evadono gli AV.", BODY))
    story.append(Spacer(1, 6))
    story.append(Centered(bar_chart([9, 8, 7, 1, 1], ["digitalchainbank", "bitcoinbot", "msg-binance", "satoshiaibot", "finanzintel"],
                                     red, maxv=10)))
    story.append(Paragraph("Fig. 3 — Detection malevole VirusTotal per dominio (su ~90 motori AV).", CAP))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<font color='%s'><b>Allerta:</b></font> la presenza di finti regolatori e di siti di \"recupero fondi\" (mymoneyrefund, "
        "auszahlungdepartment) indica il classico <b>secondo colpo</b>: dopo la truffa, le vittime vengono ricontattate da finte "
        "autorità che chiedono \"tasse di sblocco\". Il cliente non deve pagare nulla a nessun sedicente recuperatore." % RED, BODY))
    story.append(PageBreak())

    # 4 KYB
    story.append(Paragraph("4. Struttura societaria (KYB)", H1))
    story.append(Paragraph(
        "Il veicolo SBLC <b>SG Finance &amp; Trading Ltd</b> (UK 15223522) è un guscio senza bilanci, sede mass-registration, "
        "controllato al 75-100% da <b>Gianluca Sampieri</b> (serial shell director, 4 società sciolte, residente Spagna). "
        "<b>Marco Valerini</b> entra come director pochi giorni prima dell'accordo SBLC e gestisce SG Group Finance Ltd: "
        "lo stesso duo replica lo schema su più società UK.", BODY))
    story.append(PageBreak())

    # 5 Recupero
    story.append(Paragraph("5. Metodologia di recupero", H1))
    steps = [
        ("1. Denuncia", "Querela a Polizia Postale + GdF con dossier, report on-chain ed evidenze forensi (SHA-256)."),
        ("2. Preservation request", "Urgente agli exchange (Kraken/Bitstamp/Binance/MEXC): congelare gli account di destinazione."),
        ("3. EIO / MLAT", "Disclosure KYC dei titolari del cash-out, via cooperazione giudiziaria internazionale."),
        ("4. Attribuzione", "Collegare i titolari KYC a Sampieri/Valerini o ai prestanome (incrocio KYB + domini)."),
        ("5. Sequestro/restituzione", "Ordine di sequestro presso gli exchange e azione civile di restituzione."),
        ("6. Aggregazione vittime", "La rete è multi-vittima: coordinare più denunce eleva la priorità."),
    ]
    rt = Table([["Step", "Azione"]] + [[s, t] for s, t in steps], colWidths=[150, 310])
    rt.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                            ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 8.5), ("BACKGROUND", (0, 0), (-1, 0), navy),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("TEXTCOLOR", (0, 1), (0, -1), navy),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F3EC")]),
                            ("BOX", (0, 0), (-1, -1), 0.5, gold), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(rt)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<b>Tempistica critica:</b> i punti 1-2 vanno eseguiti entro giorni — i fondi sono congelabili finché restano negli "
        "account exchange identificati. La rete è attiva (movimenti fino a maggio-giugno 2026).", BODY))
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Documento riservato al committente. Dati da Companies House, MistTrack, VirusTotal e fonti OSINT alla data di emissione. "
        "Attribuzioni euristiche di clustering da confermare con strumenti forensi prima dell'uso giudiziario.",
        ParagraphStyle("disc", parent=ss["Normal"], fontName="Times-Italic", fontSize=8, textColor=grey,
                       borderColor=gold, borderWidth=0.5, borderPadding=8, backColor=colors.HexColor("#F8F6F0"))))

    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    pdf = buf.getvalue()
    sha = hashlib.sha256(pdf).hexdigest()
    fname = "%s - Dossier Illustrato - %s.pdf" % (client, case_name)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1, "content": pdf,
                        "attached_to_doctype": "Investigation Case", "attached_to_name": case_name})
    f.save(ignore_permissions=True)
    try:
        from thanatos_intel.reporting.case_reports import _put_in_drive
        _put_in_drive(case_name, fname, pdf, "application/pdf", client)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "visual_report drive")
    frappe.db.commit()
    return {"file_url": f.file_url, "sha256": sha, "filename": fname}
