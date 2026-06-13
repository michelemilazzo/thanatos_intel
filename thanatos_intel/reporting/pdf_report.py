"""
Investigation Report PDF generator.

Brand: Thanatos Intel (NAVY #0D1B3E, GOLD #C8A96E, serif Georgia)
Custody: SHA-256 hash del PDF salvato sul Report + custody log su Case
Disclaimer: art. 234-bis c.p.p. + GDPR art. 6
"""
import io
import hashlib
import frappe
from frappe.utils import get_datetime, format_datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)
from reportlab.pdfgen import canvas

NAVY = colors.HexColor("#0D1B3E")
GOLD = colors.HexColor("#C8A96E")
DARK = colors.HexColor("#0A0E1A")
GREY = colors.HexColor("#4A4A4A")

DISCLAIMERS = {
    "it": (
        "Il presente report è redatto ai sensi dell'art. 234-bis c.p.p. (acquisizione di dati informatici). "
        "La catena di custodia delle prove digitali è garantita da hash crittografico SHA-256 e log di accesso. "
        "I dati personali sono trattati ex art. 6 GDPR per legittimo interesse investigativo. "
        "Il documento contiene informazioni riservate; la divulgazione non autorizzata è vietata."
    ),
    "en": (
        "This report is issued pursuant to art. 234-bis of the Italian Code of Criminal Procedure. "
        "Digital evidence chain of custody is secured via SHA-256 cryptographic hashing and access log. "
        "Personal data is processed under GDPR art. 6 (legitimate interest). Confidential — unauthorized disclosure prohibited."
    ),
    "ro": (
        "Acest raport este emis conform art. 234-bis C.p.p. italian. "
        "Lanțul de custodie al probelor digitale este asigurat prin hash SHA-256 și jurnal de acces. "
        "Datele personale sunt prelucrate conform art. 6 GDPR. Confidențial — divulgarea neautorizată este interzisă."
    ),
}


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=ss["Title"], fontName="Times-Bold",
                                fontSize=22, textColor=NAVY, leading=26, alignment=TA_CENTER, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", parent=ss["Normal"], fontName="Times-Italic",
                                   fontSize=10, textColor=GOLD, alignment=TA_CENTER, spaceAfter=18, leading=12,
                                   tracking=2),
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Times-Bold",
                             fontSize=14, textColor=NAVY, spaceBefore=16, spaceAfter=8,
                             borderPadding=(0, 0, 4, 0), borderColor=GOLD, borderWidth=0),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Times-Bold",
                             fontSize=11, textColor=DARK, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontName="Times-Roman",
                               fontSize=10, leading=14, alignment=TA_JUSTIFY, textColor=DARK),
        "meta": ParagraphStyle("meta", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=8, leading=10, textColor=GREY),
        "disclaimer": ParagraphStyle("disclaimer", parent=ss["Normal"], fontName="Times-Italic",
                                     fontSize=8, leading=11, alignment=TA_JUSTIFY, textColor=GREY,
                                     borderColor=GOLD, borderWidth=0.5, borderPadding=8, backColor=colors.HexColor("#F8F6F0")),
    }


def _header_footer(canv: canvas.Canvas, doc, report_name: str, language: str = "it"):
    canv.saveState()
    w, h = A4
    canv.setStrokeColor(GOLD)
    canv.setLineWidth(0.8)
    canv.line(20 * mm, h - 18 * mm, w - 20 * mm, h - 18 * mm)
    canv.setFont("Times-Bold", 9)
    canv.setFillColor(NAVY)
    canv.drawString(20 * mm, h - 14 * mm, "THANATOS · INTEL")
    canv.setFont("Helvetica", 7)
    canv.setFillColor(GREY)
    canv.drawRightString(w - 20 * mm, h - 14 * mm, "RISERVATO — CATENA DI CUSTODIA")

    canv.setLineWidth(0.5)
    canv.line(20 * mm, 15 * mm, w - 20 * mm, 15 * mm)
    canv.setFont("Helvetica", 7)
    canv.setFillColor(GREY)
    canv.drawString(20 * mm, 10 * mm, f"Report: {report_name}")
    canv.drawCentredString(w / 2, 10 * mm, "thanatos.agency")
    canv.drawRightString(w - 20 * mm, 10 * mm, f"Pag. {doc.page}")
    canv.restoreState()


def _strip_html(value: str) -> str:
    if not value:
        return ""
    from html import unescape
    import re
    s = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    s = re.sub(r"</p\s*>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return unescape(s).strip()


_SOURCE_CERT = {
    "it": ("Fonti OSINT verificate e certificate",
           "Le fonti elencate sono state interrogate da Thanatos alla data indicata; "
           "di ciascun risultato è conservato l'hash SHA-256, che ne attesta l'integrità e "
           "la non alterazione (catena di custodia digitale, art. 234-bis c.p.p.). "
           "Le evidenze sono verificate e riproducibili."),
    "en": ("Verified & certified OSINT sources",
           "The listed sources were queried by Thanatos on the stated date; for each result "
           "the SHA-256 hash is retained, attesting integrity and non-tampering (digital chain "
           "of custody). Evidence is verified and reproducible."),
}


def _source_labels():
    """Mappa nome connettore → (nome leggibile, url) dal registry OSINT."""
    try:
        from thanatos_intel.osint.source_registry import SOURCES
        m = {s["key"]: (s["name"], s.get("url") or "") for s in SOURCES}
        # alias: nomi usati negli step del job → chiave registry
        for alias, key in {"opensanctions": "opensanctions_local",
                           "vessel": "vessel_sanctions",
                           "wallet": "wallet_btc"}.items():
            if key in m:
                m[alias] = m[key]
        return m
    except Exception:
        return {}


def _append_sources_section(story, s, case_name, lang):
    """Sezione fonti OSINT certificate: hash SHA-256 + timestamp per ogni risultato.

    Deriva dai job OSINT del caso e dai loro step (connector + result_json).
    """
    jobs = frappe.get_all(
        "OSINT Job",
        filters={"investigation_case": case_name, "status": "Completed"},
        fields=["name", "target_type", "target_value"], limit=200,
    )
    if not jobs:
        return
    job_map = {j.name: j for j in jobs}
    steps = frappe.get_all(
        "OSINT Job Step",
        filters={"parent": ["in", list(job_map)], "status": "Ok"},
        fields=["parent", "connector", "result_json", "started"],
        order_by="started asc", limit=500,
    )
    if not steps:
        return
    labels = _source_labels()
    title, statement = _SOURCE_CERT.get(lang, _SOURCE_CERT["it"])
    story.append(Paragraph(title, s["h1"]))
    story.append(Paragraph(statement, s["body"]))
    story.append(Spacer(1, 4))

    seen = set()
    hashes = []
    data = [["#", "Fonte", "Target", "SHA-256 (risultato)", "Verificata il"]]
    i = 0
    for st in steps:
        sha = hashlib.sha256((st.result_json or "").encode("utf-8")).hexdigest()
        j = job_map.get(st.parent)
        tgt = f"{j.target_type}: {j.target_value}" if j else ""
        key = (st.connector, tgt, sha)
        if key in seen:
            continue
        seen.add(key)
        hashes.append(sha)
        i += 1
        label = (labels.get(st.connector) or (st.connector, ""))[0]
        data.append([
            str(i), (label or st.connector or "-")[:30], tgt[:34],
            sha[:24] + "…",
            format_datetime(st.started, "dd/MM/yy HH:mm") if st.started else "-",
        ])
    if i == 0:
        return
    t = Table(data, colWidths=[8 * mm, 40 * mm, 46 * mm, 50 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F6F0")]),
        ("BOX", (0, 0), (-1, -1), 0.5, GOLD),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    manifest = hashlib.sha256("\n".join(sorted(hashes)).encode("utf-8")).hexdigest()
    story.append(Paragraph(
        f"<b>Manifest fonti (SHA-256):</b> {manifest}", s["disclaimer"]))
    story.append(Spacer(1, 10))
    return {"count": i, "manifest": manifest}


def build_report_pdf(report_name: str) -> tuple[str, str]:
    """
    Render PDF, attach as private File to Investigation Report,
    append custody log entry to linked Case, return (file_url, sha256).
    """
    rep = frappe.get_doc("Investigation Report", report_name)
    case = frappe.get_doc("Investigation Case", rep.investigation_case)
    lang = (rep.language or "it").lower()
    s = _styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=24 * mm, bottomMargin=20 * mm,
        title=rep.report_title or report_name,
        author="Thanatos Intel",
    )

    story = []
    story.append(Paragraph(rep.report_title or "Investigation Report", s["title"]))
    story.append(Paragraph(f"{rep.report_type or 'Report'} &nbsp;·&nbsp; {report_name}", s["subtitle"]))

    meta_rows = [
        ["Case", case.case_number or case.name, "Case Type", getattr(case, "case_type", "") or "-"],
        ["Report Date", format_datetime(rep.report_date, "dd/MM/yyyy") if rep.report_date else "-",
         "Language", (lang or "it").upper()],
        ["Lead Investigator", rep.lead_investigator or "-", "Status", rep.report_status or "Draft"],
    ]
    t = Table(meta_rows, colWidths=[35 * mm, 60 * mm, 35 * mm, 36 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (2, 0), (2, -1), NAVY),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8F6F0")),
        ("BOX", (0, 0), (-1, -1), 0.5, GOLD),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    def section(title, body):
        if not body:
            return
        story.append(Paragraph(title, s["h1"]))
        for para in _strip_html(body).split("\n\n"):
            para = para.strip().replace("\n", "<br/>")
            if para:
                story.append(Paragraph(para, s["body"]))
                story.append(Spacer(1, 4))

    section("Executive Summary", rep.executive_summary)
    section("Methodology", rep.methodology)
    section("Findings", rep.report_content)
    section("Conclusions", rep.conclusions)

    evidences = frappe.get_all(
        "Investigation Evidence",
        filters={"investigation_case": case.name},
        fields=["name", "evidence_name", "hash_value", "evidence_type", "acquisition_date"],
        limit=200,
    )
    if evidences:
        story.append(Paragraph("Evidence Chain of Custody", s["h1"]))
        ev_rows = [["#", "Evidence", "Type", "SHA-256 (first 16)", "Acquired"]]
        for i, e in enumerate(evidences, 1):
            ev_rows.append([
                str(i),
                (e.evidence_name or e.name)[:38],
                e.evidence_type or "-",
                (e.hash_value or "")[:16] + "…" if e.hash_value else "-",
                format_datetime(e.acquisition_date, "dd/MM/yy HH:mm") if e.acquisition_date else "-",
            ])
        et = Table(ev_rows, colWidths=[10 * mm, 60 * mm, 28 * mm, 42 * mm, 26 * mm], repeatRows=1)
        et.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F6F0")]),
            ("BOX", (0, 0), (-1, -1), 0.5, GOLD),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0D7C0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(et)
        story.append(Spacer(1, 10))

    sources_manifest = _append_sources_section(story, s, case.name, lang)

    story.append(Spacer(1, 14))
    story.append(Paragraph(DISCLAIMERS.get(lang, DISCLAIMERS["it"]), s["disclaimer"]))

    story.append(Spacer(1, 18))
    sig_rows = [
        ["Signed by", rep.signed_by or frappe.session.user, "Generated", format_datetime(get_datetime(), "dd/MM/yyyy HH:mm")],
        ["Document hash", "(computed after rendering — see file metadata)", "", ""],
    ]
    sig = Table(sig_rows, colWidths=[30 * mm, 65 * mm, 28 * mm, 43 * mm])
    sig.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (2, 0), (2, -1), NAVY),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, GOLD),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, GOLD),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig)

    def on_page(c, d):
        _header_footer(c, d, report_name, lang)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)

    pdf_bytes = buf.getvalue()
    sha = hashlib.sha256(pdf_bytes).hexdigest()

    fname = f"{report_name}.pdf"
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": fname,
        "is_private": 1,
        "content": pdf_bytes,
        "attached_to_doctype": "Investigation Report",
        "attached_to_name": report_name,
        "attached_to_field": "pdf_file",
    })
    file_doc.save(ignore_permissions=True)

    try:
        case_doc = frappe.get_doc("Investigation Case", rep.investigation_case)
        case_doc.append("case_activities", {
            "activity_type": "Report",
            "activity_date": get_datetime(),
            "performed_by": frappe.session.user,
            "description": f"Report {report_name} generated — SHA-256: {sha[:16]}…",
        })
        if sources_manifest and sources_manifest.get("count"):
            case_doc.append("case_activities", {
                "activity_type": "Report",
                "activity_date": get_datetime(),
                "performed_by": frappe.session.user,
                "description": (f"{sources_manifest['count']} fonti OSINT verificate e "
                                f"certificate nel report {report_name} — manifest SHA-256: "
                                f"{sources_manifest['manifest'][:16]}…"),
            })
        case_doc.db_update()
        for row in case_doc.case_activities:
            if not row.name:
                row.db_insert()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Report custody log append failed")

    return file_doc.file_url, sha
