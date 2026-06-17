"""Report di case: split per tema, PDF brandizzato, push in Drive con tag cliente,
conversione PDF e invio a DocuSeal per la firma.

Bottoni sul form Investigation Case (menu Report).
"""
import hashlib
import io
import os
import re
import shutil
from html import unescape

import frappe
from frappe.utils import format_datetime, get_datetime, now_datetime

NAVY = "#0D1B3E"
GOLD = "#C8A96E"

# kind -> sottostringhe (case-insensitive) dei titoli di sezione da includere
KIND_KEYWORDS = {
    "kyb": ["kyb", "sblc", "soggetti", "sg finance"],
    "blockchain": ["blockchain", "tracciamento", "attribuzione", "dove sono finiti", "kyt", "endpoint"],
    "osint": ["rete truffa", "reputazione", "virustotal", "osint", "scamadviser"],
    "recovery": ["recupero", "azioni", "preservazione", "modelli", "pacchetto"],
    "full": [],
}
KIND_LABEL = {"kyb": "KYB Due Diligence", "blockchain": "Tracciamento Blockchain",
              "osint": "OSINT & Reputazione", "recovery": "Piano di Recupero", "full": "Dossier Completo"}


def _client_name(case_doc):
    if case_doc.client:
        return frappe.db.get_value("Investigation Client", case_doc.client, "client_name") or case_doc.client
    return "Cliente"


def _sections(case_doc, kind):
    """Estrae (titolo, testo) dalle sezioni <h2> della descrizione del case."""
    html = case_doc.description or ""
    parts = re.split(r"<h2[^>]*>(.*?)</h2>", html, flags=re.I | re.S)
    out = []
    # parts[0] = preamble; poi coppie (titolo, corpo)
    for i in range(1, len(parts), 2):
        title = _strip(parts[i])
        body = parts[i + 1] if i + 1 < len(parts) else ""
        out.append((title, body))
    kws = KIND_KEYWORDS.get(kind, [])
    if kws:
        out = [(t, b) for (t, b) in out if any(k in t.lower() for k in kws)]
    return out


def _strip(value):
    if not value:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    s = re.sub(r"</tr\s*>", "\n", s, flags=re.I)
    s = re.sub(r"</td\s*>|</th\s*>", " | ", s, flags=re.I)
    s = re.sub(r"</li\s*>", "\n", s, flags=re.I)
    s = re.sub(r"</p\s*>|</h3\s*>|</h4\s*>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"[ \t]*\|[ \t]*\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _render_pdf(title, client_name, case_name, sections, language="it"):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfgen import canvas

    navy, gold, grey = colors.HexColor(NAVY), colors.HexColor(GOLD), colors.HexColor("#4A4A4A")
    ss = getSampleStyleSheet()
    st_title = ParagraphStyle("t", parent=ss["Title"], fontName="Times-Bold", fontSize=20,
                              textColor=navy, alignment=TA_CENTER, spaceAfter=2)
    st_sub = ParagraphStyle("s", parent=ss["Normal"], fontName="Times-Italic", fontSize=10,
                            textColor=gold, alignment=TA_CENTER, spaceAfter=16)
    st_h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Times-Bold", fontSize=13,
                           textColor=navy, spaceBefore=14, spaceAfter=6)
    st_body = ParagraphStyle("b", parent=ss["Normal"], fontName="Times-Roman", fontSize=10,
                             leading=14, alignment=TA_JUSTIFY)
    st_disc = ParagraphStyle("d", parent=ss["Normal"], fontName="Times-Italic", fontSize=8,
                             leading=11, textColor=grey, alignment=TA_JUSTIFY,
                             borderColor=gold, borderWidth=0.5, borderPadding=8,
                             backColor=colors.HexColor("#F8F6F0"))

    def hf(canv, doc):
        w, h = A4
        canv.saveState()
        canv.setStrokeColor(gold); canv.setLineWidth(0.8)
        canv.line(20 * mm, h - 18 * mm, w - 20 * mm, h - 18 * mm)
        canv.setFont("Times-Bold", 9); canv.setFillColor(navy)
        canv.drawString(20 * mm, h - 14 * mm, "THANATOS · INTEL")
        canv.setFont("Helvetica", 7); canv.setFillColor(grey)
        canv.drawRightString(w - 20 * mm, h - 14 * mm, "RISERVATO — " + case_name)
        canv.line(20 * mm, 15 * mm, w - 20 * mm, 15 * mm)
        canv.drawString(20 * mm, 10 * mm, "Cliente: " + client_name)
        canv.drawCentredString(w / 2, 10 * mm, "thanatos.agency")
        canv.drawRightString(w - 20 * mm, 10 * mm, "Pag. %d" % doc.page)
        canv.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=24 * mm, bottomMargin=20 * mm, title=title, author="Thanatos Intel")
    story = [Paragraph(title, st_title),
             Paragraph("Cliente: %s &nbsp;·&nbsp; %s &nbsp;·&nbsp; %s"
                       % (client_name, case_name, format_datetime(now_datetime(), "dd/MM/yyyy")), st_sub)]
    from xml.sax.saxutils import escape as _xesc
    for stitle, body in sections:
        story.append(Paragraph(_xesc(stitle), st_h1))
        for para in _strip(body).split("\n\n"):
            para = _xesc(para.strip()).replace("\n", "<br/>")
            if para:
                story.append(Paragraph(para, st_body)); story.append(Spacer(1, 4))
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Documento riservato al committente. Dati da Companies House e fonti OSINT alla data di emissione; "
        "attribuzioni euristiche da confermare con strumenti forensi prima dell'uso giudiziario. "
        "Thanatos Intel fornisce supporto tecnico-investigativo.", st_disc))
    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    data = buf.getvalue()
    return data, hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

def _drive_subfolder_for(name):
    """Sottocartella Drive in base al nome/tipo del file."""
    n = (name or "").lower()
    if n.endswith((".pdf", ".docx")):
        return "05 Report"
    if n.startswith("forensic"):
        return "02 Evidenze"
    if n.startswith(("bozza_", "modello_", "nota_eio")):
        return "07 Legale"
    if n.startswith(("trace_", "btc_trace", "upstream", "inbound", "attrib")) or "fundflow" in n:
        return "04 Blockchain"
    if n.startswith(("kyb_", "recon_", "virustotal", "scamadviser", "free_osint", "strumenti")):
        return "03 OSINT"
    if n.endswith(".zip"):
        return None  # root del case
    return "03 OSINT"


def _put_in_drive(case_name, filename, content, mime, client_name, subfolder="05 Report"):
    """Mette il file nella cartella Drive del case (sotto subfolder) con tag cliente. Idempotente."""
    case = frappe.get_doc("Investigation Case", case_name)
    case_folder = case.drive_folder
    if not case_folder or not frappe.db.exists("Drive File", case_folder):
        return None
    team = frappe.db.get_value("Drive File", case_folder, "team")

    prev = frappe.session.user
    frappe.set_user("Administrator")
    try:
        from drive.utils import get_home_folder, create_drive_file
        from drive.api.files import create_folder
        from drive.utils.files import FileManager

        home = get_home_folder(team)
        if subfolder:
            rep = frappe.db.get_value("Drive File", {"title": subfolder, "parent_entity": case_folder,
                                                     "is_group": 1, "team": team, "is_active": 1}, "name")
            if not rep:
                rep = create_folder(team, subfolder, case_folder).name
        else:
            rep = case_folder

        # idempotenza: se gia presente nella cartella, non duplicare
        existing = frappe.db.get_value("Drive File", {"title": filename, "parent_entity": rep,
                                                      "team": team, "is_active": 1}, "name")
        if existing:
            return existing

        # scrivi su file temporaneo
        tmp = frappe.get_site_path("private", "files", "_tmp_" + filename)
        with open(tmp, "wb") as f:
            f.write(content)
        size = os.path.getsize(tmp)

        manager = FileManager()
        df = create_drive_file(team, filename, rep, mime,
                               lambda e: manager.get_disk_path(e, home), size)  # noqa
        dst = manager.site_folder / df.path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp, str(dst))
        os.remove(tmp)

        # tag col nome cliente
        tag = frappe.db.get_value("Drive Tag", {"title": client_name}, "name")
        if not tag:
            tag = frappe.get_doc({"doctype": "Drive Tag", "title": client_name, "color": GOLD}).insert(ignore_permissions=True).name
        dfd = frappe.get_doc("Drive File", df.name)
        if not any(t.tag == tag for t in (dfd.tags or [])):
            dfd.append("tags", {"tag": tag})
            dfd.save(ignore_permissions=True)
        frappe.db.commit()
        return df.name
    finally:
        frappe.set_user(prev)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def generate_case_report(case_name, kind="full", language="it", to_drive=1):
    """Genera un report PDF (per tema) del case, lo allega, lo mette in Drive con tag cliente."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    case = frappe.get_doc("Investigation Case", case_name)
    client = _client_name(case)
    secs = _sections(case, kind)
    if not secs:
        frappe.throw("Nessuna sezione trovata per il tipo di report '%s'." % kind)
    title = "%s — %s" % (KIND_LABEL.get(kind, kind), client)
    pdf, sha = _render_pdf(title, client, case_name, secs, language)

    filename = "%s - %s - %s.pdf" % (client, KIND_LABEL.get(kind, kind), case_name)
    f = frappe.get_doc({"doctype": "File", "file_name": filename, "is_private": 1, "content": pdf,
                        "attached_to_doctype": "Investigation Case", "attached_to_name": case_name})
    f.save(ignore_permissions=True)

    drive_id = None
    if int(to_drive):
        try:
            drive_id = _put_in_drive(case_name, filename, pdf, "application/pdf", client)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "case_reports drive push")

    case.append("case_activities", {"activity_type": "Report", "activity_date": now_datetime(),
                "description": "Report '%s' generato (SHA-256 %s…)%s." % (
                    KIND_LABEL.get(kind, kind), sha[:12], " + Drive" if drive_id else ""),
                "operator": frappe.session.user})
    case.save(ignore_permissions=True)
    frappe.db.commit()
    return {"file_url": f.file_url, "sha256": sha, "filename": filename,
            "drive": bool(drive_id), "sections": len(secs)}


@frappe.whitelist()
def convert_to_pdf(file_url):
    """Converte un allegato (docx/odt/html) in PDF via LibreOffice, allega + Drive."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    fdoc = frappe.get_doc("File", {"file_url": file_url})
    src = frappe.get_site_path("private" if fdoc.is_private else "public", "files",
                               file_url.split("/files/")[-1])
    if not os.path.exists(src):
        frappe.throw("File non trovato: " + src)
    import subprocess, tempfile
    outdir = tempfile.mkdtemp()
    soffice = next((p for p in ("/usr/bin/soffice", "/usr/bin/libreoffice",
                                "/opt/libreoffice/program/soffice") if os.path.exists(p)), None)
    if not soffice:
        frappe.throw("LibreOffice non installato sul server (richiesto per la conversione PDF).")
    r = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, src],
                       capture_output=True, text=True, timeout=120)
    pdfs = [x for x in os.listdir(outdir) if x.endswith(".pdf")]
    if not pdfs:
        frappe.throw("Conversione fallita: " + (r.stderr or r.stdout)[:200])
    pdf_path = os.path.join(outdir, pdfs[0])
    content = open(pdf_path, "rb").read()
    fname = pdfs[0]
    nf = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1, "content": content,
                         "attached_to_doctype": fdoc.attached_to_doctype, "attached_to_name": fdoc.attached_to_name})
    nf.save(ignore_permissions=True)
    drive = False
    if fdoc.attached_to_doctype == "Investigation Case":
        client = _client_name(frappe.get_doc("Investigation Case", fdoc.attached_to_name))
        try:
            drive = bool(_put_in_drive(fdoc.attached_to_name, fname, content, "application/pdf", client))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "convert_to_pdf drive")
    frappe.db.commit()
    return {"file_url": nf.file_url, "filename": fname, "drive": drive}


@frappe.whitelist()
def send_report_to_docuseal(file_url, case_name, signer_email=None, signer_name=None):
    """Invia un PDF report a DocuSeal per la firma. Riusa l'integrazione esistente."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    import os
    import requests
    from thanatos_intel.integrations.docuseal import _conf, _headers, _create_template_from_pdf, _resolve_pdf_path

    conf = _conf()
    if not conf["base_url"] or not conf["api_key"]:
        frappe.throw("DocuSeal non configurato in site_config.")
    if not file_url.lower().endswith(".pdf"):
        frappe.throw("Inviare un PDF. Converti prima il file con 'Converti in PDF'.")

    case = frappe.get_doc("Investigation Case", case_name)
    if not signer_email:
        if case.client:
            signer_email = frappe.db.get_value("Investigation Client", case.client, "email")
            signer_name = signer_name or frappe.db.get_value("Investigation Client", case.client, "client_name")
    if not signer_email:
        frappe.throw("Email del firmatario mancante.")

    pdf_path = _resolve_pdf_path(file_url)
    if not os.path.exists(pdf_path):
        frappe.throw("PDF non trovato: " + pdf_path)

    ref = (case_name + "-" + os.path.basename(file_url))[:60]
    template_id = _create_template_from_pdf(ref, pdf_path)
    tmpl = requests.get(f"{conf['base_url']}/api/templates/{template_id}", headers=_headers(), timeout=10)
    role = "Prima parte"
    if tmpl.status_code == 200:
        roles = [s.get("name", "") for s in tmpl.json().get("submitters", [])]
        if roles:
            role = roles[0]
    payload = {"send_email": True, "submitters": [{"role": role, "email": signer_email, "name": signer_name or signer_email}],
               "metadata": {"case": case_name, "report": os.path.basename(file_url)}}
    resp = requests.post(f"{conf['base_url']}/api/templates/{template_id}/submissions",
                         headers=_headers(), json=payload, timeout=15)
    if resp.status_code not in (200, 201):
        requests.delete(f"{conf['base_url']}/api/templates/{template_id}", headers=_headers(), timeout=5)
        frappe.throw("DocuSeal error %s: %s" % (resp.status_code, resp.text[:200]))
    data = resp.json()
    subs = data if isinstance(data, list) else data.get("submitters", [])
    first = subs[0] if subs else {}
    slug = first.get("slug", "")
    url = f"{conf['base_url']}/s/{slug}" if slug else first.get("embed_src", "")

    case.append("case_activities", {"activity_type": "Report", "activity_date": now_datetime(),
                "description": "Report %s inviato a DocuSeal per firma (%s)." % (os.path.basename(file_url), signer_email),
                "operator": frappe.session.user})
    case.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "signing_url": url,
            "submission_id": first.get("submission_id") or first.get("id")}

@frappe.whitelist()
def send_report_to_mmos_sign(file_url, case_name, signer_email=None, signer_name=None):
    """Invia un PDF report a MMOS Sign (engine PAdES interno) per la firma.

    Gemella di :func:`send_report_to_docuseal` (WAVE 2, additiva): non sostituisce
    DocuSeal, lo affianca. Crea una Signature Request mmos_sign dal PDF gia'
    certificato e la invia in firma via mmos_sign.api.
    """
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    import os
    from mmos_sign import api as _ms

    if not file_url.lower().endswith(".pdf"):
        frappe.throw("Inviare un PDF. Converti prima il file con 'Converti in PDF'.")

    case = frappe.get_doc("Investigation Case", case_name)
    if not signer_email and case.client:
        signer_email = frappe.db.get_value("Investigation Client", case.client, "email")
        signer_name = signer_name or frappe.db.get_value("Investigation Client", case.client, "client_name")
    if not signer_email:
        frappe.throw("Email del firmatario mancante.")

    pdf_path = frappe.get_site_path(
        "private", "files", file_url.split("/private/files/")[-1]
    ) if "/private/files/" in file_url else frappe.get_site_path(
        "public", "files", file_url.split("/files/")[-1])
    if not os.path.exists(pdf_path):
        frappe.throw("PDF non trovato: " + pdf_path)
    with open(pdf_path, "rb") as fh:
        pdf_bytes = fh.read()

    req = frappe.new_doc("Signature Request")
    req.reference_doctype = "Investigation Case"
    req.reference_name = case_name
    req.signing_mode = "Single"
    req.signer_email = signer_email
    req.signer_name = signer_name or signer_email
    try:
        req.signing_plan = "Advanced (AdES)"
    except Exception:
        pass
    req.insert(ignore_permissions=True)
    fdoc = frappe.get_doc({
        "doctype": "File", "file_name": f"{req.name}_source.pdf",
        "attached_to_doctype": "Signature Request", "attached_to_name": req.name,
        "is_private": 1, "content": pdf_bytes,
    }).insert(ignore_permissions=True)
    req.db_set("source_pdf", fdoc.file_url, update_modified=False)
    frappe.db.commit()

    res = _ms.send_request(req.name)

    case.append("case_activities", {"activity_type": "Report", "activity_date": now_datetime(),
                "description": "Report %s inviato a MMOS Sign per firma (%s)." % (os.path.basename(file_url), signer_email),
                "operator": frappe.session.user})
    case.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "signing_url": res.get("url"), "signature_request": req.name}



# ---------------------------------------------------------------------------
# Organizzazione Drive (bottone + hook automatico)
# ---------------------------------------------------------------------------

def _push_file_to_drive(file_name_doc, case_name):
    """Spinge un singolo File del case nella sottocartella Drive giusta. Idempotente."""
    f = frappe.get_doc("File", file_name_doc)
    case = frappe.get_doc("Investigation Case", case_name)
    client = _client_name(case)
    sub = _drive_subfolder_for(f.file_name)
    src = frappe.get_site_path("private" if f.is_private else "public", "files",
                               (f.file_url or "").split("/files/")[-1])
    if not os.path.exists(src):
        return None
    mime = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "html": "text/html", "json": "application/json", "zip": "application/zip"}.get(
        f.file_name.rsplit(".", 1)[-1].lower(), "text/plain")
    drive_name = _put_in_drive(case_name, f.file_name, open(src, "rb").read(), mime, client, subfolder=sub)
    _dedup_flat_attachment(src, drive_name)
    return drive_name


def _dedup_flat_attachment(src, drive_file_name):
    """Sostituisce il file flat (allegato) con un symlink alla copia nel box
    (cartella Drive), eliminando il duplicato locale. Best-effort, idempotente."""
    try:
        if not drive_file_name or not src or os.path.islink(src) or not os.path.exists(src):
            return
        rel = frappe.db.get_value("Drive File", drive_file_name, "path")
        if not rel:
            return
        real = os.path.realpath(frappe.get_site_path("private", "files", rel))
        if not os.path.exists(real) or os.path.getsize(real) != os.path.getsize(src):
            return  # copia box non pronta/diversa: non toccare il flat
        os.remove(src)
        os.symlink(real, src)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case_reports._dedup_flat_attachment")


@frappe.whitelist()
def migrate_flat_attachments_to_box(case_name=None):
    """Migra gli allegati flat dei casi nel box: push in Drive + dedup del flat
    (symlink). Idempotente. Senza case_name processa tutti i casi."""
    frappe.only_for(("System Manager", "Investigation Manager"))
    cases = [case_name] if case_name else frappe.get_all(
        "Investigation Case", pluck="name")
    done = 0
    for cn in cases:
        files = frappe.get_all("File", filters={
            "attached_to_doctype": "Investigation Case", "attached_to_name": cn}, pluck="name")
        for fn in files:
            try:
                if _push_file_to_drive(fn, cn):
                    done += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(), "migrate_flat_attachments_to_box")
    return {"cases": len(cases), "deduped": done}


@frappe.whitelist()
def organize_case_files_to_drive(case_name):
    """Smista tutti gli allegati del case nelle sottocartelle Drive (non cancella nulla)."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    files = frappe.get_all("File", filters={"attached_to_doctype": "Investigation Case",
                                            "attached_to_name": case_name}, pluck="name")
    pushed = 0
    for fn in files:
        try:
            if _push_file_to_drive(fn, case_name):
                pushed += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "organize_case_files_to_drive")
    return {"total": len(files), "in_drive": pushed}


def on_file_after_insert(doc, method=None):
    """Hook: ogni allegato di un Investigation Case va automaticamente in Drive."""
    if doc.attached_to_doctype != "Investigation Case" or not doc.attached_to_name:
        return
    if (doc.file_name or "").startswith("_tmp_"):
        return
    frappe.enqueue("thanatos_intel.reporting.case_reports._push_file_to_drive", queue="short",
                   file_name_doc=doc.name, case_name=doc.attached_to_name, enqueue_after_commit=True)
