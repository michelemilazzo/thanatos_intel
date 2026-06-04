"""Genera PDF Final Dossier istituzionale (executive + legal + risk + evidence)."""
import io
import json
import frappe
from frappe.utils import now_datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                Table, TableStyle, PageBreak)
from reportlab.lib import colors

DISCLAIMER = ("Thanatos performs investigative, due diligence, compliance and "
              "eligibility assessment services only. Thanatos does NOT issue, sell, "
              "broker or guarantee diplomatic, consular, governmental or identity "
              "documents.")


@frappe.whitelist()
def generate(dossier_name: str) -> str:
    d = frappe.get_doc("Final Dossier", dossier_name)
    case = frappe.get_doc("Diplomatic Eligibility Case", d.ddd_case)
    applicant = frappe.get_doc("Applicant Profile", case.applicant) if case.applicant else None
    country = frappe.get_doc("Country Framework", case.country) if case.country else None

    s = getSampleStyleSheet()
    s.add(ParagraphStyle("Gold", parent=s["Heading1"],
                         textColor=colors.HexColor("#c8a96e"), fontSize=22))
    s.add(ParagraphStyle("H2g", parent=s["Heading2"],
                         textColor=colors.HexColor("#0A0E1A"), fontSize=13))
    s.add(ParagraphStyle("Disc", parent=s["BodyText"], fontSize=8,
                         textColor=colors.HexColor("#7a1c1c"), leading=10))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title=f"Dossier {d.name}")
    story = [
        Paragraph("THANATOS INTEL", s["Gold"]),
        Paragraph("CONFIDENTIAL INSTITUTIONAL DOSSIER", s["H2g"]),
        Spacer(1, 0.3*cm),
        Paragraph(f"<b>Dossier:</b> {d.name} v{d.version or 1}<br/>"
                  f"<b>Case:</b> {case.name} — {case.request_type}<br/>"
                  f"<b>Country:</b> {case.country}<br/>"
                  f"<b>Generated:</b> {now_datetime():%Y-%m-%d %H:%M}", s["BodyText"]),
        Spacer(1, 0.4*cm),
        Paragraph(DISCLAIMER, s["Disc"]),
        PageBreak(),
        Paragraph("1. Executive Summary", s["H2g"]),
        Paragraph(d.executive_summary or "—", s["BodyText"]),
        Spacer(1, 0.3*cm),
        Paragraph("2. Institutional Purpose", s["H2g"]),
        Paragraph(d.institutional_purpose or case.institutional_purpose or "—", s["BodyText"]),
        Spacer(1, 0.3*cm),
        Paragraph("3. Applicant Identity", s["H2g"]),
    ]
    if applicant:
        story.append(Paragraph(
            f"<b>{applicant.full_legal_name}</b><br/>"
            f"DOB: {applicant.dob} — POB: {applicant.place_of_birth or '-'}<br/>"
            f"Nationality: {applicant.nationality or '-'} (others: {applicant.additional_nationalities or '-'})<br/>"
            f"Tax residence: {applicant.tax_residence or '-'}<br/>"
            f"Occupation: {applicant.occupation or '-'} — {applicant.current_employer or '-'}<br/>"
            f"PEP: {'YES' if applicant.is_pep else 'no'}",
            s["BodyText"]))
    story += [Spacer(1, 0.3*cm),
              Paragraph("4. Legal Basis", s["H2g"]),
              Paragraph(d.legal_basis or (country.legal_basis if country else "") or "—", s["BodyText"]),
              Spacer(1, 0.3*cm),
              Paragraph("5. Country Framework", s["H2g"])]
    if country:
        story.append(Paragraph(
            f"<b>Authority:</b> {country.diplomatic_authority or '-'}<br/>"
            f"<b>Passport types:</b> {country.passport_types or '-'}<br/>"
            f"<b>Languages:</b> {country.official_languages or '-'}<br/>"
            f"<b>Risk indicators:</b> {country.risk_indicators or '-'}", s["BodyText"]))

    # Compliance
    story += [Spacer(1, 0.3*cm), Paragraph("6. Compliance Checks", s["H2g"])]
    checks = frappe.get_all("Compliance Check", filters={"ddd_case": case.name},
                            fields=["check_type", "outcome", "officer", "notes"])
    rows = [["Tipo", "Esito", "Officer", "Note"]] + [
        [c.check_type, c.outcome, c.officer or "-", (c.notes or "")[:60]] for c in checks
    ]
    if len(rows) > 1:
        t = Table(rows, colWidths=[3*cm, 2*cm, 3*cm, 8*cm])
        t.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.3, colors.grey),
                               ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0A0E1A")),
                               ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#c8a96e")),
                               ("FONTSIZE", (0,0), (-1,-1), 8)]))
        story.append(t)
    else:
        story.append(Paragraph("Nessun check registrato.", s["BodyText"]))

    # Screening
    story += [Spacer(1, 0.3*cm), Paragraph("7. Sanctions / PEP Screening", s["H2g"])]
    scr = frappe.get_all("Sanctions Screening", filters={"ddd_case": case.name},
                         fields=["screening_type", "matches_found", "outcome", "source", "screened_on"])
    if scr:
        rows = [["Tipo", "Source", "Matches", "Esito", "Quando"]] + [
            [r.screening_type, r.source, r.matches_found, r.outcome, str(r.screened_on)[:16]] for r in scr
        ]
        t = Table(rows, colWidths=[3*cm, 4*cm, 2*cm, 3*cm, 4*cm])
        t.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.3, colors.grey),
                               ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0A0E1A")),
                               ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#c8a96e")),
                               ("FONTSIZE", (0,0), (-1,-1), 8)]))
        story.append(t)

    # Risk
    story += [Spacer(1, 0.3*cm), Paragraph("8. Risk Assessment", s["H2g"]),
              Paragraph(f"<b>Score:</b> {case.risk_score or 0}/100 — <b>Band:</b> {case.risk_band or '-'}", s["BodyText"]),
              Paragraph(d.risk_summary or "—", s["BodyText"])]

    # Evidence Index
    story += [Spacer(1, 0.3*cm), Paragraph("9. Evidence Index", s["H2g"])]
    ev = frappe.get_all("Required Document", filters={"ddd_case": case.name},
                        fields=["document_type", "status", "evidence", "passport_analysis"])
    if ev:
        rows = [["Tipo Documento", "Stato", "Evidence", "Passport Analysis"]] + [
            [e.document_type, e.status, e.evidence or "-", e.passport_analysis or "-"] for e in ev
        ]
        t = Table(rows, colWidths=[4*cm, 3*cm, 5*cm, 5*cm])
        t.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.3, colors.grey),
                               ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0A0E1A")),
                               ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#c8a96e")),
                               ("FONTSIZE", (0,0), (-1,-1), 8)]))
        story.append(t)

    # Legal Opinion
    story += [Spacer(1, 0.3*cm), Paragraph("10. Legal Opinion", s["H2g"])]
    los = frappe.get_all("Legal Opinion", filters={"ddd_case": case.name},
                         fields=["name", "conclusion", "legal_officer", "issued_on", "reasoning"], limit=1)
    if los:
        lo = los[0]
        story.append(Paragraph(
            f"<b>Conclusione:</b> {lo.conclusion}<br/>"
            f"<b>Officer:</b> {lo.legal_officer} — <b>Issued:</b> {lo.issued_on}<br/>"
            f"{(lo.reasoning or '')[:1200]}", s["BodyText"]))

    # Decision
    story += [Spacer(1, 0.3*cm), Paragraph("11. Final Decision", s["H2g"]),
              Paragraph(f"<b>Decision:</b> {d.decision or case.final_decision or '-'}", s["BodyText"]),
              Spacer(1, 0.4*cm), Paragraph(DISCLAIMER, s["Disc"])]

    doc.build(story)
    buf.seek(0)
    fdoc = frappe.get_doc({
        "doctype": "File", "file_name": f"{d.name}.pdf", "is_private": 1,
        "content": buf.getvalue(),
        "attached_to_doctype": "Final Dossier", "attached_to_name": d.name,
    })
    fdoc.save(ignore_permissions=True)
    d.dossier_pdf = fdoc.file_url
    d.generated_on = now_datetime()
    d.save(ignore_permissions=True)
    frappe.db.commit()
    return fdoc.file_url
