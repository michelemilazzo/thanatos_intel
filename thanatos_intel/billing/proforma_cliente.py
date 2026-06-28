"""Proforma cliente + calcolo costi vivi con markup (>=50%).

compute_costs: voci di costo vivo (visure, banche dati, OCR/AI, ore, legale,
acquisizione fatture) → totale costi vivi × (1+markup) = prezzo minimo cost-plus.
genera_proforma: PDF proforma con onorario congruo a fasi + dettaglio costi vivi.
Tutto parametrico: per casi simili cambiano solo ore/soggetti.
"""
import io

import frappe
from frappe.utils import nowdate

NAVY = "#0D1B3E"; GOLD = "#C8A96E"; GREY = "#5A5A5A"

# tariffe orarie default (EUR)
RATE_SENIOR = 90
RATE_ANALYST = 55
# costi unitari banche dati (EUR)
COST_VISURA = 25
COST_BILANCIO = 8


def compute_costs(case, hours_senior=40, hours_analyst=30, n_visure=None,
                  legal_fee=1500, fatture_acq=600, markup=0.5):
    c = frappe.get_doc("Investigation Case", case)
    n_companies = sum(1 for ce in (c.get("case_entities") or [])
                      if frappe.db.get_value("Investigation Entity", ce.entity, "entity_type") == "Company")
    if n_visure is None:
        n_visure = max(8, n_companies)
    n_docs = frappe.db.count("Investigation Evidence", {"investigation_case": case})
    voci = [
        ("Visure camerali e bilanci", f"{n_visure} soggetti", n_visure * (COST_VISURA + COST_BILANCIO)),
        ("Banche dati OSINT / sanzioni / protesti", "accessi", 300),
        ("Elaborazione documentale OCR + AI", f"{n_docs} documenti", max(300, n_docs * 25)),
        ("Ore investigatore senior", f"{hours_senior} h × {RATE_SENIOR}€", hours_senior * RATE_SENIOR),
        ("Ore analista documentale", f"{hours_analyst} h × {RATE_ANALYST}€", hours_analyst * RATE_ANALYST),
        ("Parere legale-fiscale (consulente)", "forfait", legal_fee),
        ("Acquisizione fatture elettroniche / cassetto (via intermediario)", "forfait", fatture_acq),
    ]
    costi_vivi = sum(v[2] for v in voci)
    prezzo_min = round(costi_vivi * (1 + markup), -1)
    return {"voci": voci, "costi_vivi": costi_vivi, "markup": markup,
            "prezzo_min": prezzo_min, "n_docs": n_docs, "n_visure": n_visure}


# onorario a fasi (value-based) — congruo all'esposizione del cliente
FASI = [
    ("Fase 1 — Screening rapido e semaforo (esistenza credito, doppia cessione, asseveratori)", 4500),
    ("Fase 2 — Due diligence completa (cedente, catena cessionari, fatture, congruità)", 9000),
    ("Fase 3 — Acquisizione e riscontro cassetto/fatture via delega + riconciliazione + tracciamento bonifici", 5500),
    ("Fase 4 — Dossier probatorio + verdetto + supporto a denuncia/recupero (escussione RC)", 7000),
]


@frappe.whitelist()
def genera_proforma(case, hours_senior=40, hours_analyst=30, markup=0.5, sconto=0):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    hours_senior = int(hours_senior); hours_analyst = int(hours_analyst); markup = float(markup)
    c = frappe.get_doc("Investigation Case", case)
    client = (frappe.db.get_value("Investigation Client", c.client, "client_name") if c.client else None) or "Cliente"
    cc = compute_costs(case, hours_senior=hours_senior, hours_analyst=hours_analyst, markup=markup)

    onorario = sum(f[1] for f in FASI)
    imponibile = max(onorario, cc["prezzo_min"])
    imponibile = round(imponibile * (1 - float(sconto) / 100.0), -1)

    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, leading=11, textColor=colors.HexColor(GREY))
    hd = ParagraphStyle("h", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white)

    def tbl(rows, widths, money_cols=()):
        t = Table(rows, colWidths=widths)
        st = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F3EC")]),
              ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(GOLD)),
              ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        for mc in money_cols:
            st.append(("ALIGN", (mc, 0), (mc, -1), "RIGHT"))
        t.setStyle(TableStyle(st)); return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm)
    P = lambda t, s=body: Paragraph(t, s)
    S = [Paragraph(f"<font color='{GOLD}'><b>THANATOS INTEL</b></font>", ParagraphStyle("t", parent=ss["Title"], fontSize=20, alignment=TA_CENTER)),
         Paragraph("PREVENTIVO / PROFORMA", ParagraphStyle("s2", parent=ss["Title"], fontSize=14, textColor=colors.HexColor(NAVY), alignment=TA_CENTER)),
         Paragraph(f"Cliente: {client} · Caso {c.name} · {nowdate()}", ParagraphStyle("u", parent=ss["Normal"], fontSize=9, textColor=colors.HexColor(GREY), alignment=TA_CENTER, spaceAfter=10))]

    S.append(P("<b>Oggetto:</b> indagine e due diligence antifrode su cessione di crediti d'imposta, "
               "raccolta probatoria e supporto al recupero (esposizione cliente: € 800.000).", body))
    S.append(Spacer(1, 8))

    S.append(P("<b>A. Onorario professionale — a fasi</b>", body))
    rows = [[P("Fase", hd), P("Onorario €", hd)]]
    for label, amt in FASI:
        rows.append([P(label), P(f"{amt:,.0f}")])
    rows.append([P("<b>Totale onorario</b>"), P(f"<b>{onorario:,.0f}</b>")])
    S.append(tbl(rows, [400, 67], money_cols=(1,)))
    S.append(Spacer(1, 8))

    S.append(P("<b>B. Costi vivi (rendicontati) e prezzo minimo cost-plus</b>", body))
    rows = [[P("Voce", hd), P("Dettaglio", hd), P("€", hd)]]
    for label, det, amt in cc["voci"]:
        rows.append([P(label), P(det, small), P(f"{amt:,.0f}")])
    rows.append([P("<b>Totale costi vivi</b>"), P(""), P(f"<b>{cc['costi_vivi']:,.0f}</b>")])
    rows.append([P(f"Prezzo minimo (costi vivi + {int(markup*100)}% markup)"), P(""), P(f"<b>{cc['prezzo_min']:,.0f}</b>")])
    S.append(tbl(rows, [235, 165, 67], money_cols=(2,)))
    S.append(Spacer(1, 10))

    S.append(P(f"<b>Imponibile proposto: € {imponibile:,.0f}</b> (il maggiore tra onorario a fasi e prezzo minimo cost-plus"
               + (f", al netto di sconto {sconto}%" if float(sconto) else "") + "). IVA esclusa ove dovuta. "
               "Acconto 40% all'avvio, saldo alla consegna del dossier. Eventuali costi vivi eccedenti rendicontati a parte.",
               ParagraphStyle("tot", parent=body, fontSize=11, backColor=colors.HexColor("#F8F6F0"),
                              borderColor=colors.HexColor(GOLD), borderWidth=0.6, borderPadding=8)))
    S.append(Spacer(1, 8))
    S.append(P("Le Fasi 3-4 presuppongono la delega del cliente per l'accesso al cassetto fiscale e alle fatture "
               "elettroniche. Preventivo valido 30 giorni.", small))

    def hf(canv, dc):
        w, hh = A4; canv.saveState(); canv.setStrokeColor(colors.HexColor(GOLD)); canv.setLineWidth(0.8)
        canv.line(18 * mm, hh - 16 * mm, w - 18 * mm, hh - 16 * mm)
        canv.setFont("Times-Bold", 9); canv.setFillColor(colors.HexColor(NAVY)); canv.drawString(18 * mm, hh - 13 * mm, "THANATOS · INTEL")
        canv.setFont("Helvetica", 7); canv.setFillColor(colors.HexColor(GREY)); canv.drawRightString(w - 18 * mm, hh - 13 * mm, "PROFORMA — " + c.name)
        canv.restoreState()
    doc.build(S, onFirstPage=hf, onLaterPages=hf)
    content = buf.getvalue()

    fname = f"PROFORMA - {client} - {c.name}.pdf"
    old = frappe.db.get_value("File", {"attached_to_doctype": "Investigation Case", "attached_to_name": case, "file_name": fname}, "name")
    if old:
        frappe.delete_doc("File", old, ignore_permissions=True, force=True)
    f = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1, "content": content,
                        "attached_to_doctype": "Investigation Case", "attached_to_name": case})
    f.save(ignore_permissions=True)
    try:
        from thanatos_intel.reporting.case_reports import _put_in_drive
        _put_in_drive(case, fname, content, "application/pdf", client, subfolder="07 Legale")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "proforma drive")
    frappe.db.commit()
    return {"ok": True, "file_url": f.file_url, "imponibile": imponibile,
            "onorario": onorario, "costi_vivi": cc["costi_vivi"], "prezzo_min": cc["prezzo_min"]}
