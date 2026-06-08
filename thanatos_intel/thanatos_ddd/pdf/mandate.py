"""Genera PDF Agency Mandate via ReportLab — disclaimer compliance-first."""
import io
import frappe
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                Table, TableStyle, PageBreak)
from reportlab.lib import colors

DISCLAIMER = ("Thanatos performs investigative, due diligence, compliance and "
              "eligibility assessment services only. Thanatos does NOT issue, sell, "
              "broker or guarantee diplomatic, consular, governmental or identity "
              "documents. Any decision or issuance is exclusively subject to "
              "competent public authorities and applicable law.")


def _style():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("Disc", parent=s["BodyText"], fontSize=8,
                         textColor=colors.HexColor("#7a1c1c"), leading=10))
    s.add(ParagraphStyle("Gold", parent=s["Heading1"],
                         textColor=colors.HexColor("#c8a96e"), fontSize=18))
    s.add(ParagraphStyle("H2g", parent=s["Heading2"],
                         textColor=colors.HexColor("#0A0E1A"), fontSize=12))
    return s


@frappe.whitelist()
def generate(mandate_name: str) -> str:
    m = frappe.get_doc("Agency Mandate", mandate_name)
    case = frappe.get_doc("Diplomatic Eligibility Case", m.ddd_case) if m.ddd_case else None
    applicant = frappe.get_doc("Applicant Profile", m.applicant) if m.applicant else None

    # Entità di fatturazione (agenzia che emette/fattura le DD passaporti — config di piattaforma)
    from thanatos_intel.billing.billing_entity import get_ddd_billing_entity
    entity = None
    if m.get("billing_entity") and frappe.db.exists("Billing Entity", m.billing_entity):
        entity = frappe.get_doc("Billing Entity", m.billing_entity)
    else:
        entity = get_ddd_billing_entity()
    mandatario = (entity.legal_name or entity.entity_name) if entity else "Thanatos Intel — OneKey Co."
    # Cornice legale per-entità: ARES = legge italiana/autorizzazioni IT, Thanatos = legge rumena/autorizzazioni RO
    gov_law = (entity.governing_law if entity and entity.get("governing_law")
               else (m.get("governing_law") or "Legge italiana"))
    foro = entity.jurisdiction if entity and entity.get("jurisdiction") else "Foro di Roma"
    disclaimer = entity.legal_disclaimer if entity and entity.get("legal_disclaimer") else DISCLAIMER
    authz = ""
    if entity and (entity.get("license_authority") or entity.get("license_number")):
        authz = (entity.license_authority or "")
        if entity.get("license_number"):
            authz += f" — n. {entity.license_number}"
    steps = frappe.get_all("Mandate Service Step", filters={"mandate": mandate_name},
                           fields=["step_no", "title", "description", "fee", "vat_pct",
                                   "due_date", "status", "payment_status"],
                           order_by="step_no asc")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title=f"Agency Mandate {m.name}")
    s = _style()
    story = []
    story += [Paragraph("THANATOS INTEL", s["Gold"]),
              Paragraph("AGENCY MANDATE / MANDATO PROFESSIONALE", s["H2g"]),
              Spacer(1, 0.3*cm),
              Paragraph(f"<b>Ref:</b> {m.name} &nbsp;&nbsp; <b>Case:</b> {m.ddd_case}", s["BodyText"]),
              Spacer(1, 0.4*cm)]

    if applicant:
        story.append(Paragraph(f"<b>Mandante:</b> {applicant.full_legal_name}, "
                              f"nato il {applicant.dob} a {applicant.place_of_birth or '-'}, "
                              f"residente in {applicant.current_residence or '-'}.", s["BodyText"]))
    story += [Spacer(1, 0.3*cm),
              Paragraph(f"<b>Mandatario:</b> {mandatario}", s["BodyText"])]
    if entity and (entity.iban or entity.bank_name):
        story.append(Paragraph(
            f"<b>Coordinate per il pagamento:</b> {entity.bank_name or ''} — "
            f"Titolare: {entity.account_holder or mandatario}"
            + (f" — IBAN: {entity.iban}" if entity.iban else "")
            + (f" — BIC: {entity.bic_swift}" if entity.bic_swift else ""),
            s["BodyText"]))
    if authz:
        story.append(Paragraph(f"<b>Autorizzazioni:</b> {authz}", s["BodyText"]))
    story += [Spacer(1, 0.4*cm),
              Paragraph("<b>1. Oggetto</b>", s["H2g"]),
              Paragraph(m.subject_matter or "Due diligence, OSINT e preparazione dossier istituzionale.", s["BodyText"]),
              Spacer(1, 0.3*cm),
              Paragraph("<b>2. Ambito Territoriale</b>", s["H2g"]),
              Paragraph(m.territorial_scope or "International", s["BodyText"]),
              Spacer(1, 0.3*cm),
              Paragraph("<b>3. Attività Autorizzate</b>", s["H2g"]),
              Paragraph("• OSINT su fonti aperte<br/>"
                        "• Verifica documentale (KYC/KYB)<br/>"
                        "• Contatto con terzi previa autorizzazione scritta<br/>"
                        "• Preparazione dossier compliance / istituzionale", s["BodyText"]),
              Spacer(1, 0.3*cm),
              Paragraph("<b>4. Clausola di NON-Garanzia</b>", s["H2g"]),
              Paragraph(disclaimer, s["Disc"]),
              Spacer(1, 0.4*cm),
              Paragraph("<b>5. Compenso e Step di Pagamento</b>", s["H2g"])]

    rows = [["#", "Titolo", "Fee", "VAT %", "Scadenza", "Status", "Pagamento"]]
    for st in steps:
        rows.append([st.step_no or "", st.title, f"€ {st.fee or 0:.2f}",
                     f"{st.vat_pct or 0:g}", str(st.due_date or "-"),
                     st.status, st.payment_status])
    t = Table(rows, colWidths=[0.8*cm, 5.5*cm, 2.5*cm, 1.5*cm, 2.5*cm, 2*cm, 2*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0A0E1A")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#c8a96e")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story += [t, Spacer(1, 0.3*cm),
              Paragraph(f"<b>Totale Mandato:</b> € {m.fee_total or 0:.2f} ({m.currency or 'EUR'})", s["BodyText"]),
              Spacer(1, 0.4*cm),
              Paragraph("<b>6. Riservatezza e Privacy</b>", s["H2g"]),
              Paragraph("Le parti si obbligano alla massima riservatezza. Il trattamento dati "
                        "avviene secondo Reg. UE 2016/679 (GDPR).", s["BodyText"]),
              Spacer(1, 0.3*cm),
              Paragraph("<b>7. Legge Applicabile e Foro</b>", s["H2g"]),
              Paragraph(f"{gov_law} — Foro competente: {foro}.", s["BodyText"]),
              Spacer(1, 1*cm),
              Paragraph("Mandante __________________________ &nbsp;&nbsp;&nbsp; "
                        "Mandatario __________________________", s["BodyText"]),
              Spacer(1, 0.6*cm),
              Paragraph(disclaimer, s["Disc"])]
    doc.build(story)
    buf.seek(0)

    fdoc = frappe.get_doc({
        "doctype": "File", "file_name": f"{m.name}.pdf",
        "is_private": 1, "content": buf.getvalue(),
        "attached_to_doctype": "Agency Mandate", "attached_to_name": m.name,
    })
    fdoc.save(ignore_permissions=True)
    m.mandate_pdf = fdoc.file_url
    m.save(ignore_permissions=True)
    frappe.db.commit()
    return fdoc.file_url
