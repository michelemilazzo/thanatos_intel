"""Acquisizione e riconciliazione FATTURE ELETTRONICHE (FatturaPA).

- parse_fatturapa: estrae i dati salienti da un XML FatturaPA (o .p7m firmato).
- ingest_case_invoices: parsa tutti gli XML/p7m allegati al caso → reperti.
- extract_declared_invoices: estrae (via AI) l'elenco delle fatture DICHIARATE da
  un documento del caso (es. "dichiarazione delle fatture" = 27 fatture BOMAX).
- reconcile_invoices: incrocia le fatture REALI (XML) con quelle DICHIARATE e
  segnala dichiarate-ma-inesistenti, importi divergenti, ecc.

Gli XML li elaboriamo noi; lo scarico dal cassetto richiede la delega del titolare.
"""
import base64
import os
import re
import xml.etree.ElementTree as ET

import frappe
from frappe.utils import now_datetime


def _local(tag):
    return tag.split("}")[-1]


def _children(el, name):
    return [c for c in list(el) if _local(c.tag) == name]


def _find(el, *path):
    cur = [el]
    for name in path:
        nxt = []
        for e in cur:
            nxt.extend(_children(e, name))
        if not nxt:
            return None
        cur = nxt
    return cur[0]


def _text(el, *path):
    e = _find(el, *path) if path else el
    return (e.text or "").strip() if e is not None and e.text else ""


def _extract_xml_bytes(content):
    """Da bytes di .xml o .p7m → bytes XML FatturaPA."""
    if b"FatturaElettronica" in content[:4000]:
        return content
    # p7m base64
    try:
        dec = base64.b64decode(content, validate=False)
        if b"FatturaElettronica" in dec:
            content = dec
    except Exception:
        pass
    for pat in (rb"<\?xml.*?</\w*:?FatturaElettronica>",
                rb"<\w*:?FatturaElettronica[ >].*?</\w*:?FatturaElettronica>"):
        m = re.search(pat, content, re.S)
        if m:
            return m.group(0)
    return content


def _num(x):
    try:
        return float(str(x).replace(".", "").replace(",", ".")) if ("," in str(x)) else float(x or 0)
    except Exception:
        try:
            return float(x)
        except Exception:
            return 0.0


def parse_fatturapa(content):
    """content: bytes. Ritorna dict con i dati salienti (o {'error':...})."""
    try:
        root = ET.fromstring(_extract_xml_bytes(content))
    except Exception as e:
        return {"error": f"XML non valido: {str(e)[:120]}"}
    header = _find(root, "FatturaElettronicaHeader")
    bodies = _children(root, "FatturaElettronicaBody")

    def party(node):
        if node is None:
            return {}
        den = _text(node, "DatiAnagrafici", "Anagrafica", "Denominazione")
        if not den:
            den = (_text(node, "DatiAnagrafici", "Anagrafica", "Nome") + " "
                   + _text(node, "DatiAnagrafici", "Anagrafica", "Cognome")).strip()
        return {"denominazione": den,
                "piva": _text(node, "DatiAnagrafici", "IdFiscaleIVA", "IdCodice"),
                "cf": _text(node, "DatiAnagrafici", "CodiceFiscale")}

    ced = party(_find(header, "CedentePrestatore")) if header is not None else {}
    ces = party(_find(header, "CessionarioCommittente")) if header is not None else {}

    docs = []
    for body in bodies:
        dgd = _find(body, "DatiGenerali", "DatiGeneraliDocumento")
        imp = imposta = ""
        rie = _find(body, "DatiBeniServizi", "DatiRiepilogo")
        if rie is not None:
            imp = _text(rie, "ImponibileImporto")
            imposta = _text(rie, "Imposta")
        docs.append({
            "tipo": _text(dgd, "TipoDocumento") if dgd is not None else "",
            "numero": _text(dgd, "Numero") if dgd is not None else "",
            "data": _text(dgd, "Data") if dgd is not None else "",
            "totale": _num(_text(dgd, "ImportoTotaleDocumento")) if dgd is not None else 0,
            "imponibile": _num(imp), "imposta": _num(imposta),
        })
    main = docs[0] if docs else {}
    return {"cedente": ced, "cessionario": ces, "documenti": docs, **main}


_INVOICE_EXT = (".xml", ".p7m")


def _read_file(file_url):
    path = frappe.get_site_path("private", "files", (file_url or "").split("/files/")[-1])
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


@frappe.whitelist()
def ingest_case_invoices(case):
    """Parsa tutti gli XML/p7m allegati al caso e crea un reperto per fattura."""
    files = frappe.get_all("File", filters={"attached_to_doctype": "Investigation Case",
                                            "attached_to_name": case},
                           fields=["file_name", "file_url"], limit=0)
    parsed, errs = [], 0
    for f in files:
        if not (f.file_name or "").lower().endswith(_INVOICE_EXT):
            continue
        content = _read_file(f.file_url)
        if not content:
            continue
        d = parse_fatturapa(content)
        if d.get("error"):
            errs += 1
            continue
        d["_file"] = f.file_name
        parsed.append(d)
        ced = (d.get("cedente") or {}).get("denominazione") or "?"
        ces = (d.get("cessionario") or {}).get("denominazione") or "?"
        note = (f"Fattura elettronica n. {d.get('numero')} del {d.get('data')}\n"
                f"Cedente: {ced} (P.IVA {(d.get('cedente') or {}).get('piva')})\n"
                f"Cessionario: {ces} (P.IVA {(d.get('cessionario') or {}).get('piva')})\n"
                f"Totale: {d.get('totale'):,.2f} € · Imponibile: {d.get('imponibile'):,.2f} · "
                f"Imposta: {d.get('imposta'):,.2f}")
        try:
            ev = frappe.get_doc({"doctype": "Investigation Evidence", "investigation_case": case,
                                 "evidence_name": f"Fattura {d.get('numero')} — {ced}"[:140],
                                 "evidence_type": "Document", "source": "FatturaPA (delega)",
                                 "acquisition_date": now_datetime(), "custody_status": "Received",
                                 "attached_file": f.file_url, "notes": note[:1000]})
            ev.flags.ignore_mandatory = True
            ev.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "fatturapa evidence")
    frappe.db.commit()
    return {"ok": True, "fatture": len(parsed), "errori": errs, "parsed": parsed}


_DECL_SYS = (
    "Sei un analista di Thanatos Intel. Dal testo di un documento che ELENCA fatture "
    "(es. dichiarazione di crediti/fatture impagate) estrai l'elenco delle fatture. "
    "Rispondi SOLO con JSON: {\"fatture\": [{\"numero\":\"\",\"data\":\"\",\"debitore\":\"\","
    "\"importo_eur\": 0}]}. Importi numeri puri. Se non è un elenco di fatture: {\"fatture\":[]}."
)


@frappe.whitelist()
def extract_declared_invoices(case):
    """Estrae (AI) l'elenco delle fatture dichiarate dai documenti del caso."""
    from thanatos_intel.ai.ocr_service import ocr_file
    from thanatos_intel.ai import doc_ingest as DI
    from thanatos_intel.ai.case_architect import _resp_text
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=["attached_file", "notes"], limit=0)
    declared = []
    for e in evs:
        notes = (e.notes or "").lower()
        if "fattur" not in notes and "dichiaraz" not in notes:
            continue
        if not e.attached_file or not e.attached_file.lower().endswith((".pdf", ".docx")):
            continue
        try:
            ocr = ocr_file(e.attached_file, "generic") or {}
        except Exception:
            ocr = {}
        text = (ocr.get("raw_text") or "").strip() or (DI._read_text_fallback(e.attached_file) or "").strip()
        if not text:
            continue
        ai = DI._gateway(f"Testo:\n{text[:12000]}", system=_DECL_SYS, task_type="extract")
        d = DI._extract_json(_resp_text(ai)) or {}
        for f in (d.get("fatture") or []):
            if f.get("numero") or f.get("importo_eur"):
                declared.append({"numero": str(f.get("numero") or "").strip(),
                                 "data": f.get("data") or "",
                                 "debitore": (f.get("debitore") or "").strip(),
                                 "importo": _num(f.get("importo_eur"))})
    return declared


@frappe.whitelist()
def reconcile_invoices(case):
    """Incrocia fatture REALI (XML) con quelle DICHIARATE; segnala discrepanze."""
    real = ingest_case_invoices(case)["parsed"]
    declared = extract_declared_invoices(case)

    def key_num(n):
        return re.sub(r"[^0-9a-z]", "", (n or "").lower())

    real_by_num = {}
    for r in real:
        real_by_num.setdefault(key_num(r.get("numero")), []).append(r)

    flags, matched = [], 0
    rows = []
    for d in declared:
        kn = key_num(d["numero"])
        cand = real_by_num.get(kn, [])
        status = "MANCANTE"
        if cand:
            r = cand[0]
            if abs(r.get("totale", 0) - d["importo"]) <= max(1.0, d["importo"] * 0.01):
                status = "OK"
                matched += 1
            else:
                status = f"IMPORTO DIVERSO (reale {r.get('totale'):,.0f} vs dichiarato {d['importo']:,.0f})"
                flags.append(f"Fattura {d['numero']}: {status}")
        else:
            flags.append(f"Fattura DICHIARATA n.{d['numero']} ({d['importo']:,.0f}€ a "
                         f"{d['debitore'] or '?'}) NON trovata tra le fatture elettroniche reali")
        rows.append({"numero": d["numero"], "dichiarato": d["importo"],
                     "debitore": d["debitore"], "status": status})

    tot_decl = sum(d["importo"] for d in declared)
    missing = sum(1 for r in rows if r["status"] == "MANCANTE")
    verdict = ("ALLARME" if (declared and not real) or missing else
               ("ATTENZIONE" if flags else "Coerente"))
    lines = [f"🧾 RICONCILIAZIONE FATTURE — {verdict}",
             f"Dichiarate: {len(declared)} ({tot_decl:,.0f}€) · Reali (XML): {len(real)} · "
             f"corrispondenti: {matched} · mancanti: {missing}"]
    if not real and declared:
        lines.append("Nessuna fattura elettronica reale disponibile: caricare gli XML "
                     "scaricati dal cassetto fiscale (via delega) per completare il riscontro.")
    lines.extend(flags[:25])
    try:
        c = frappe.get_doc("Investigation Case", case)
        c.append("case_activities", {"activity_date": now_datetime(),
                 "activity_type": "Document Analysis",
                 "description": "\n".join(lines)[:1000], "operator": frappe.session.user})
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "reconcile activity")
    return {"ok": True, "verdict": verdict, "declared": len(declared), "real": len(real),
            "matched": matched, "missing": missing, "flags": flags, "rows": rows}
