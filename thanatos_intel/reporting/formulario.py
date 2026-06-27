"""Formulario Investigativo — playbook riusabile per FRODE SU CESSIONE CREDITI D'IMPOSTA.

Genera un documento operativo per l'investigatore con TRE sezioni:
  A) DOMANDE AL CLIENTE (cosa chiedere per ricostruire fatti e DANNO)
  B) SPUNTI NORMATIVI (riferimenti italiani da validare col legale)
  C) DIREZIONE / STRATEGIA (prove, penale, civile, recupero, difesa fiscale)
Tailored con le parti e gli importi del caso. Riusabile su casi analoghi.
NB: contenuto normativo = riferimenti di lavoro, NON consulenza legale; Thanatos
opera in RO, la qualificazione giuridica IT va confermata dal legale incaricato.
"""
import io

import frappe
from frappe.utils import nowdate

NAVY = "#0D1B3E"
GOLD = "#C8A96E"
GREY = "#5A5A5A"

DOMANDE = [
    ("Operazione", [
        "Quale/i credito/i hai acquistato? (codice tributo es. 6834 DTA / 6869 Investimenti Mezzogiorno, importo nominale, prezzo pagato, % sconto)",
        "Da chi (cedente) e con quale contratto/atto? Date di firma e di efficacia.",
        "Quante cessioni/tranche? Lo stesso credito ti è stato proposto da più soggetti?",
    ]),
    ("Pagamento e DANNO (€800.000)", [
        "Quanto hai versato in TOTALE? Confermare l'importo esatto (€800.000?).",
        "A CHI hai pagato esattamente: al cedente (BOMAX) o a terzi/advisor/escrow? Ragioni sociali e IBAN.",
        "Fornire TUTTI i bonifici (data, importo, ordinante, beneficiario, IBAN, causale) — è la base per quantificare e tracciare il danno.",
        "Hai pagato prima o dopo aver ricevuto le asseverazioni e l'accettazione sulla Piattaforma?",
    ]),
    ("Intermediari", [
        "Chi ti ha proposto l'affare? (broker/advisor, es. T. Venosa) Ruolo, compenso, rapporti col cedente.",
        "Esistono mandati/incarichi firmati con gli intermediari? Compensi pattuiti e pagati?",
    ]),
    ("Documentazione e promesse", [
        "Quali asseverazioni/visti hai ricevuto (Fattorelli, Grube, Conte) e QUANDO rispetto al pagamento?",
        "Cosa ti è stato garantito per iscritto (PEC, email, chat)? Conserva tutto.",
        "Hai i contratti firmati, le Autorizzazioni AdE (protocolli), le visure del cedente?",
    ]),
    ("Stato del credito e AdE", [
        "Il credito ti è stato ACCETTATO sulla Piattaforma Cessione Crediti? Screenshot/PDF dello stato.",
        "Hai già compensato in F24? Per quanto, con quali date? Hai ricevuto contestazioni/avvisi/PVC dall'AdE?",
        "Sei disposto a firmare la DELEGA (cassetto fiscale + fatture elettroniche) per la verifica autoritativa?",
    ]),
]

NORMATIVA = [
    ("Natura dei crediti", [
        "Credito Investimenti Mezzogiorno: art. 1, commi 98-108, L. 208/2015 (cod. tributo 6869). Richiede investimenti in beni strumentali nuovi in strutture produttive nel Mezzogiorno.",
        "Credito da trasformazione DTA (imposte anticipate): cod. 6834 — natura e presupposti DIVERSI dal 6869 (non confondere).",
    ]),
    ("Cessione e responsabilità del cessionario", [
        "Art. 121, co. 4-6, e art. 122-bis DL 34/2020 (conv. L. 77/2020): controlli AdE e responsabilità SOLIDALE del cessionario in caso di credito INESISTENTE con concorso/dolo/colpa grave.",
        "Crediti 'inesistenti' vs 'non spettanti': diverso regime sanzionatorio (art. 13 DLgs 471/97) e termini di accertamento.",
        "Tutela del TERZO cessionario in BUONA FEDE: l'acquirente diligente non risponde; la diligenza professionale esclude il concorso (cfr. la stessa relazione di conformità che cita Cass. n. 30720/2021, 28451/2021, 28246/2020).",
    ]),
    ("Profili penali (verso cedente, intermediari, asseveratori)", [
        "Art. 640-bis c.p. (truffa aggravata per conseguimento di erogazioni pubbliche) e art. 316-ter (indebita percezione).",
        "Art. 640 c.p. (truffa) verso l'acquirente; art. 483/482 c.p. (falso); art. 8 DLgs 74/2000 (emissione di fatture per operazioni inesistenti).",
        "Concorso ex art. 110 c.p. di intermediari e asseveratori che hanno avallato il credito.",
    ]),
    ("Responsabilità professionale e assicurativa", [
        "Responsabilità dell'asseveratore/intermediario (art. 1176, 2236 c.c.); escutibilità delle polizze RC professionali (es. Grube — DUAL; Fattorelli).",
        "Anomalie che incrinano l'asseverazione: clausole riferite ad altra società, conflazione di crediti diversi, conclusioni-disclaimer che ammettono l'impossibilità di verifica.",
    ]),
]

STRATEGIA = [
    ("1. Prove (autoritative)", [
        "DELEGA del cliente → cassetto fiscale + Piattaforma Cessione Crediti: stato reale del credito (esistente/non spettante/bloccato) + Autorizzazioni AdE (verificare i protocolli, es. n. 24041147544011397-000001).",
        "Acquisizione XML fatture elettroniche → riconciliazione con le fatture dichiarate (rilevatore già attivo).",
        "Verifica camerale cedente/cessionari/intermediari (procedure concorsuali, patrimonio).",
    ]),
    ("2. Quantificazione del danno (€800.000)", [
        "Tracciare i bonifici: chi ha incassato (cedente? advisor?), importi, date → mappa del flusso del denaro (follow-the-money).",
        "Documentare il pregiudizio subìto dal cliente (versato vs ricevuto) per penale e civile.",
    ]),
    ("3. Azione penale", [
        "Denuncia/querela per truffa (640/640-bis), falso e fatture inesistenti verso cedente (BOMAX/Romano), intermediari e asseveratori (concorso).",
        "Allegare il dossier Thanatos (autenticità documenti, doppia cessione, anomalie asseverazioni) come notitia criminis.",
    ]),
    ("4. Azione civile e recupero", [
        "Risarcimento/restituzione verso cedente e intermediari; escussione delle polizze RC degli asseveratori.",
        "Misure cautelari (sequestro conservativo) su asset di cedente/intermediari individuati dalle visure.",
    ]),
    ("5. Difesa fiscale del cliente (cessionario)", [
        "Documentare la BUONA FEDE e la diligenza di Trading HU per neutralizzare il recupero AdE verso il cessionario; paradossalmente la relazione-disclaimer prova che la verifica era 'oggettivamente impossibile' per l'acquirente.",
    ]),
]


def _case_ctx(case):
    c = frappe.get_doc("Investigation Case", case)
    client = (frappe.db.get_value("Investigation Client", c.client, "client_name") if c.client else None) or "—"
    parti = []
    for ce in (c.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity, ["full_name", "entity_type"], as_dict=True)
        if et:
            parti.append(f"{et.full_name} ({et.entity_type})")
    return c, client, parti


@frappe.whitelist()
def genera_formulario(case):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem

    c, client, parti = _case_ctx(case)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13, alignment=TA_JUSTIFY)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=colors.HexColor(NAVY), spaceBefore=12, spaceAfter=4)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, textColor=colors.HexColor(GOLD), spaceBefore=8, spaceAfter=2)

    def section(title, blocks):
        out = [Paragraph(title, h2)]
        for sub, items in blocks:
            out.append(Paragraph(sub, h3))
            out.append(ListFlowable([ListItem(Paragraph(it, body), leftIndent=8) for it in items],
                                    bulletType="bullet", start="•", leftIndent=10))
        return out

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm)
    S = [Paragraph(f"<font color='{GOLD}'><b>THANATOS INTEL</b></font>", ParagraphStyle("t", parent=ss["Title"], fontSize=20, alignment=TA_CENTER)),
         Paragraph("FORMULARIO INVESTIGATIVO — Frode su cessione di crediti d'imposta", ParagraphStyle("s", parent=ss["Title"], fontSize=13, textColor=colors.HexColor(NAVY), alignment=TA_CENTER)),
         Paragraph(f"Caso {c.name} · Cliente: {client} · {nowdate()}", ParagraphStyle("u", parent=ss["Normal"], fontSize=9, textColor=colors.HexColor(GREY), alignment=TA_CENTER, spaceAfter=8))]
    S.append(Paragraph(f"<b>Danno lamentato dal cliente: € 800.000</b> (importo versato per crediti risultati non genuini — confermare l'esatto ammontare e i beneficiari).",
                       ParagraphStyle("dmg", parent=body, backColor=colors.HexColor("#FBEEE6"), borderColor=colors.HexColor("#C0392B"), borderWidth=0.6, borderPadding=6)))
    if parti:
        S.append(Spacer(1, 4))
        S.append(Paragraph("<b>Parti del caso:</b> " + "; ".join(parti[:20]), body))

    S += section("A) DOMANDE AL CLIENTE", DOMANDE)
    S += section("B) SPUNTI NORMATIVI (da validare col legale)", NORMATIVA)
    S += section("C) DIREZIONE / STRATEGIA", STRATEGIA)
    S.append(Spacer(1, 10))
    S.append(Paragraph("Documento operativo interno Thanatos Intel — riferimenti normativi di lavoro, non consulenza legale. "
                       "La qualificazione giuridica italiana va confermata dal legale incaricato.", ParagraphStyle("disc", parent=ss["Normal"], fontName="Times-Italic", fontSize=8, textColor=colors.HexColor(GREY), leading=11)))

    def hf(canv, dc):
        w, hh = A4
        canv.saveState()
        canv.setStrokeColor(colors.HexColor(GOLD)); canv.setLineWidth(0.8)
        canv.line(18 * mm, hh - 16 * mm, w - 18 * mm, hh - 16 * mm)
        canv.setFont("Times-Bold", 9); canv.setFillColor(colors.HexColor(NAVY)); canv.drawString(18 * mm, hh - 13 * mm, "THANATOS · INTEL")
        canv.setFont("Helvetica", 7); canv.setFillColor(colors.HexColor(GREY)); canv.drawRightString(w - 18 * mm, hh - 13 * mm, "FORMULARIO — " + c.name)
        canv.drawRightString(w - 18 * mm, 9 * mm, "pag. %d" % canv.getPageNumber())
        canv.restoreState()

    doc.build(S, onFirstPage=hf, onLaterPages=hf)
    content = buf.getvalue()

    fname = f"FORMULARIO INVESTIGATIVO - {c.name}.pdf"
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
        frappe.log_error(frappe.get_traceback(), "formulario drive")
    frappe.db.commit()
    return {"ok": True, "file_url": f.file_url}
