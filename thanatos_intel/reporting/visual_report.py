"""Dossier illustrato Thanatos (completo) — copertina, grafici, diagramma di
flusso, serialita/timeline, KYB, soggetti, recupero. PDF brandizzato + Drive.
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
def generate_visual_dossier(case_name):
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
    risk = case.risk_score_final or 0

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Times-Bold", fontSize=15, textColor=navy, spaceBefore=12, spaceAfter=6)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="Times-Bold", fontSize=11, textColor=colors.HexColor("#0A0E1A"), spaceBefore=8, spaceAfter=3)
    BODY = ParagraphStyle("B", parent=ss["Normal"], fontName="Times-Roman", fontSize=10, leading=14, alignment=TA_JUSTIFY)
    CAP = ParagraphStyle("C", parent=ss["Normal"], fontName="Helvetica-Oblique", fontSize=8, textColor=grey, alignment=TA_CENTER, spaceBefore=2)
    BUL = ParagraphStyle("bul", parent=BODY, leftIndent=14, spaceAfter=2)

    def bullets(items):
        return [Paragraph("<font color='%s'>&bull;</font>  %s" % (GOLD, x), BUL) for x in items]

    def tbl(rows, widths, redrow=None, head=True):
        t = Table(rows, colWidths=widths)
        sty = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.2), ("VALIGN", (0, 0), (-1, -1), "TOP"),
               ("BOX", (0, 0), (-1, -1), 0.5, gold), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F3EC")]),
               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
               ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
        if head:
            sty += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.4), ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 8.2),
                    ("TEXTCOLOR", (0, 1), (0, -1), navy)]
        if redrow is not None:
            sty.append(("TEXTCOLOR", (0, redrow), (-1, redrow), red))
        t.setStyle(TableStyle(sty)); return t

    # ---- charts ----
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
        # asse 2022..2026, barre attivita per wallet
        d = Drawing(460, 150)
        x0, x1, ya = 90, 440, 120
        years = [2022, 2023, 2024, 2025, 2026]
        def px(y, frac=0.0):
            t = (y - 2022 + frac) / 4.0
            return x0 + t * (x1 - x0)
        for y in years:
            d.add(Line(px(y), 18, px(y), ya + 8, strokeColor=colors.HexColor("#D8D2BE"), strokeWidth=0.5))
            d.add(String(px(y), 8, str(y), fontName="Helvetica", fontSize=7, fillColor=grey, textAnchor="middle"))
        bars = [("Hub 3", 2022.45, 2026.34, navy), ("Target 1F1LW5x", 2023.80, 2026.31, colors.HexColor("#3A4668")),
                ("Hub 1", 2023.13, 2026.11, navy), ("Hub 2", 2023.51, 2026.38, navy)]
        for i, (name, s, e, col) in enumerate(bars):
            yy = ya - i * 24
            d.add(String(82, yy - 3, name, fontName="Helvetica", fontSize=7, fillColor=navy, textAnchor="end"))
            d.add(Rect(px(int(s), s - int(s)), yy - 7, px(int(e), e - int(e)) - px(int(s), s - int(s)), 9,
                       fillColor=gold, strokeColor=col, strokeWidth=0.4))
        d.add(String((x0 + x1) / 2, 138, "Attivita continua 2022 - 2026 (4 anni)", fontName="Helvetica-Bold", fontSize=8, fillColor=red, textAnchor="middle"))
        return d

    def flow():
        d = Drawing(460, 250)
        def box(x, y, w, h, text, fill, tcol=colors.white, fs=8):
            d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=navy, strokeWidth=0.5, rx=4, ry=4))
            for i, line in enumerate(text.split("\n")):
                d.add(String(x + w / 2, y + h / 2 + 4 - i * 9, line, fontName="Helvetica-Bold", fontSize=fs, fillColor=tcol, textAnchor="middle"))
        import math
        def arrow(x1, y1, x2, y2):
            d.add(Line(x1, y1, x2, y2, strokeColor=gold, strokeWidth=1.2))
            a = math.atan2(y2 - y1, x2 - x1)
            d.add(Polygon([x2, y2, x2 - 6 * math.cos(a - 0.4), y2 - 6 * math.sin(a - 0.4), x2 - 6 * math.cos(a + 0.4), y2 - 6 * math.sin(a + 0.4)], fillColor=gold, strokeColor=gold))
        box(10, 200, 90, 34, "VITTIMA\nDarbesio", green)
        box(120, 200, 100, 34, "bitcoinbot.tech\n(piattaforma fake)", red)
        box(245, 200, 95, 34, "Wallet raccolta\n1F1LW5x", navy)
        box(360, 200, 90, 34, "Electrum\nwallet_1", colors.HexColor("#7A5C2E"))
        arrow(100, 217, 120, 217); arrow(220, 217, 245, 217); arrow(340, 217, 360, 217)
        box(150, 130, 160, 30, "3 HUB consolidamento (~58 BTC)", colors.HexColor("#3A4668"))
        arrow(292, 200, 250, 162)
        for i, (e, c) in enumerate(zip(["Kraken", "Binance", "Bitstamp", "MEXC", "hitbtc"], [navy, navy, navy, navy, red])):
            box(10 + i * 92, 60, 86, 28, e, c, fs=7); arrow(230, 130, 53 + i * 92, 88)
        d.add(String(230, 35, "CASH-OUT su exchange — recupero solo via richiesta legale (KYC)", fontName="Helvetica-Oblique", fontSize=8, fillColor=grey, textAnchor="middle"))
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
    S.append(Paragraph("<font color='%s'>Crypto Investment Scam</font>" % RED, ParagraphStyle("w", parent=ss["Normal"], fontSize=14, alignment=TA_CENTER, spaceAfter=22)))
    S.append(tbl([["Cliente", client], ["Ref. caso", case_name], ["Investigatore", case.assigned_investigator or "-"],
                  ["Data", nowdate()], ["Classificazione", "CONFIDENZIALE"]], [120, 250], head=False))
    S.append(Spacer(1, 14)); S.append(C(gauge(risk))); S.append(PageBreak())

    # 1 quadro + flow
    S.append(Paragraph("1. Quadro d'insieme", H1))
    S.append(Paragraph("Crypto investment scam su piattaforma fake (bitcoinbot.tech): la vittima deposita crypto reali e vede un saldo fittizio. I fondi sono transitati da un wallet di raccolta attraverso 3 hub di consolidamento fino al cash-out su exchange. Di seguito la mappa del flusso.", BODY))
    S.append(Spacer(1, 6)); S.append(C(flow()))
    S.append(Paragraph("Fig. 1 — Flusso dei fondi: vittima → piattaforma → wallet di raccolta → hub → exchange.", CAP))
    S.append(PageBreak())

    # 2 destinazione
    S.append(Paragraph("2. Destinazione finale dei fondi", H1))
    S.append(C(pie([42, 6, 52], ["Exchange/custodia", "Wallet fermi", "Peel/dust"], [navy, green, colors.HexColor("#B8AE90")])))
    S.append(Paragraph("Fig. 2 — Ripartizione del flusso tracciato (value-weighted).", CAP))
    S.append(Spacer(1, 6))
    S.append(Paragraph("<b>Il grosso dei fondi è confluito nella custodia di exchange centralizzati.</b> Non esiste un wallet che trattenga importi significativi: il sequestro on-chain non è praticabile, il recupero passa per la richiesta legale agli exchange (KYC dei titolari del cash-out).", BODY))
    S.append(Spacer(1, 6))
    S.append(tbl([["Exchange", "Ruolo", "Recupero"],
                  ["Kraken (5 indirizzi)", "Cash-out, regolamentato", "Subpoena/EIO — UK/IE/US"],
                  ["Binance", "Cash-out (16.905 BTC hot)", "EIO/MLAT"],
                  ["Bitstamp", "Cash-out, regolamentato", "EIO — UK/EU"],
                  ["MEXC", "Cash-out (8.999 BTC hot)", "Richiesta diretta/MLAT"],
                  ["hitbtc-unionchain.ai", "Exchange A RISCHIO (AML 60)", "Probabile non-cooperativo — segnalare"]],
                 [150, 175, 145], redrow=5))
    S.append(PageBreak())

    # 3 serialita
    S.append(Paragraph("3. Scala e serialità dell'operazione", H1))
    S.append(Paragraph("L'analisi a monte dei wallet di consolidamento dimostra un'<b>operazione seriale, organizzata e pluriennale</b>, non un episodio isolato.", BODY))
    S.append(Spacer(1, 4))
    S.append(C(vbar([25.9, 20.0, 12.0, 26.6], ["Hub 1", "Hub 2", "Hub 3", "Target"], navy, maxv=30, fmt="%.1f")))
    S.append(Paragraph("Fig. 3 — BTC totali raccolti per wallet (storico). I 3 hub: ~58 BTC complessivi.", CAP))
    S.append(Spacer(1, 4)); S.append(C(timeline()))
    S.append(Paragraph("Fig. 4 — Periodi di attività: raccolta continua su 4 anni (2022-2026).", CAP))
    S.append(Spacer(1, 6))
    S.extend(bullets([
        "<b>~58 BTC</b> raccolti dai 3 hub (oltre 3-4 milioni di euro).",
        "Da <b>centinaia di fonti distinte</b> (~640 mittenti campionati): ampia platea di vittime.",
        "Attività continua <b>2022-2026</b> (oltre 4 anni): struttura stabile e ricorrente.",
        "Il wallet del caso (26,6 BTC, 68 fonti) è <b>uno dei tanti</b> afflussi della stessa rete.",
    ]))
    S.append(PageBreak())

    # 4 rete + VT
    S.append(Paragraph("4. Rete di truffe collegata", H1))
    S.append(Paragraph("Il reverse-IP dell'hosting ha rivelato una rete coordinata: piattaforme fake, finte banche, finti regolatori (FCA, NCA, BCE, FIU) e truffe di recupero fondi. VirusTotal conferma i nodi operativi; i finti-istituzionali evadono gli AV.", BODY))
    S.append(Spacer(1, 6))
    S.append(C(vbar([9, 8, 7, 1, 1], ["digitalchainbank", "bitcoinbot", "msg-binance", "satoshiaibot", "finanzintel"], red, maxv=10)))
    S.append(Paragraph("Fig. 5 — Detection malevole VirusTotal per dominio (su ~90 motori AV).", CAP))
    S.append(Spacer(1, 6))
    S.append(Paragraph("<font color='%s'><b>Allerta:</b></font> la presenza di finti regolatori e di siti di \"recupero fondi\" (mymoneyrefund, auszahlungdepartment) indica il classico <b>secondo colpo</b>: dopo la truffa, le vittime vengono ricontattate da finte autorità che chiedono \"tasse di sblocco\". Il cliente non deve pagare nulla a nessun sedicente recuperatore." % RED, BODY))
    S.append(PageBreak())

    # 5 soggetti + KYB
    S.append(Paragraph("5. Struttura della frode crypto", H1))
    S.append(tbl([["Elemento", "Tipo", "Dettaglio"],
                  ["bitcoinbot.tech", "Piattaforma fake", "Saldo fittizio 69.739 BTC mostrato alla vittima; nessun fondo reale custodito"],
                  ["Rete (~15 domini)", "Infrastruttura", "Hostinger, stesso IP 185.224.138.165: bot fake, finte banche, finti regolatori, recovery scam"],
                  ["Silvia Darbesio", "Vittima", "Depositi reali poi tracciati on-chain fino agli exchange"],
                  ["Operatori", "Non identificati", "Registranti oscurati da privacy; proprieta da accertare via autorita"]],
                 [115, 100, 245]))
    S.append(Spacer(1, 6))
    S.append(Paragraph("La piattaforma <b>bitcoinbot.tech</b> non custodisce alcun fondo reale: il saldo mostrato alla vittima e fittizio (numeri nel database). I depositi reali sono confluiti nei wallet dei truffatori e da li agli exchange. L'identita degli operatori non e ricavabile dai dati pubblici.", BODY))
    S.append(PageBreak())

    # 6 recupero
    S.append(Paragraph("6. Metodologia di recupero", H1))
    steps = [("1. Denuncia", "Querela a Polizia Postale + GdF con dossier, report on-chain ed evidenze forensi (SHA-256)."),
             ("2. Preservation request", "Urgente agli exchange (Kraken/Bitstamp/Binance/MEXC): congelare gli account di destinazione."),
             ("3. EIO / MLAT", "Disclosure KYC dei titolari del cash-out via cooperazione giudiziaria internazionale."),
             ("4. Attribuzione", "Collegare i titolari KYC agli operatori o ai prestanome (dati registrar/host via autorita)."),
             ("5. Sequestro/restituzione", "Ordine di sequestro presso gli exchange e azione civile di restituzione."),
             ("6. Aggregazione vittime", "La rete è multi-vittima: coordinare più denunce eleva la priorità.")]
    S.append(tbl([["Step", "Azione"]] + [[a, b] for a, b in steps], [150, 310]))
    S.append(Spacer(1, 8))
    S.append(Paragraph("<b>Tempistica critica:</b> i punti 1-2 vanno eseguiti entro giorni — i fondi sono congelabili finché restano negli account exchange identificati. La rete è attiva (movimenti fino a maggio-giugno 2026).", BODY))
    S.append(Spacer(1, 12))
    S.append(Paragraph("Documento riservato al committente. Dati da Companies House, MistTrack, VirusTotal e fonti OSINT alla data di emissione. Attribuzioni euristiche di clustering da confermare con strumenti forensi (Chainalysis/Elliptic) prima dell'uso giudiziario.",
                       ParagraphStyle("disc", parent=ss["Normal"], fontName="Times-Italic", fontSize=8, textColor=grey, borderColor=gold, borderWidth=0.5, borderPadding=8, backColor=colors.HexColor("#F8F6F0"))))

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
        frappe.log_error(frappe.get_traceback(), "visual_report drive")
    frappe.db.commit()
    return {"file_url": f.file_url, "sha256": sha, "filename": fname}
