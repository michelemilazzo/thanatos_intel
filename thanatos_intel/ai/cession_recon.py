"""Rilevatore doppia cessione di crediti d'imposta (controllo antifrode).

Estrae da ogni documento del caso le transazioni di cessione (cedente,
cessionario, codice tributo, importo nominale, prezzo) e le dichiarazioni di
credito (plafond totale). Aggrega per (cedente, credito) e segnala:
  - stesso credito ceduto a PIU' cessionari diversi;
  - somma delle cessioni > plafond dichiarato (sovra-allocazione);
  - stessa cessione documentata più volte;
  - incoerenze cedente/importi.
E' il controllo che smaschera la frode tipica sulle cessioni di crediti fiscali.
"""
import frappe
from frappe.utils import now_datetime

from thanatos_intel.ai.ocr_service import ocr_file
from thanatos_intel.ai import doc_ingest as DI
from thanatos_intel.ai.case_architect import _resp_text

_SYS = (
    "Sei un analista forense di Thanatos Intel specializzato in cessioni di crediti "
    "d'imposta. Ricevi il testo di UN documento. Rispondi SOLO con JSON valido: "
    '{"is_cession": true, "cedente": "", "cessionario": "", '
    '"credit_code": "codice tributo es. 6834", '
    '"credit_type": "es. DTA / Investimenti Mezzogiorno", '
    '"nominal_amount_eur": 0, "transfer_price_eur": 0, "discount_pct": 0, "date": "", '
    '"is_credit_declaration": false, "declared_total_eur": 0, "notes": ""}. '
    "Importi in EUR come numeri puri (es. 350000, niente punti/virgole/simboli). Campi "
    "assenti = vuoto/0. is_cession=true SOLO se il documento trasferisce un credito da un "
    "cedente a un cessionario (contratto/atto/verbale/escrow di cessione). "
    "is_credit_declaration=true se il documento dichiara l'ammontare TOTALE di un credito "
    "(es. dichiarazione del titolare del credito)."
)


def _num(x):
    try:
        if isinstance(x, str):
            x = x.replace(".", "").replace(",", ".").replace("€", "").replace(" ", "")
        return float(x or 0)
    except Exception:
        return 0.0


def _extract_one(text):
    ai = DI._gateway(f"Documento:\n\n{text[:12000]}", system=_SYS, task_type="extract")
    return DI._extract_json(_resp_text(ai)) or {}


@frappe.whitelist()
def detect_double_cession(case, wa_phone=None, sender=None, lead_name=None):
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=["attached_file"], limit=0)
    cessions, declarations = [], []
    for e in evs:
        fu = e.attached_file
        if not fu:
            continue
        try:
            ocr = ocr_file(fu, "generic") or {}
        except Exception:
            ocr = {}
        text = (ocr.get("raw_text") or "").strip() or (DI._read_text_fallback(fu) or "").strip()
        if not text:
            continue
        d = _extract_one(text)
        fn = fu.split("/files/")[-1]
        if d.get("is_cession") and (_num(d.get("nominal_amount_eur")) or d.get("cessionario")):
            cessions.append({
                "file": fn, "cedente": (d.get("cedente") or "").strip(),
                "cessionario": (d.get("cessionario") or "").strip(),
                "code": str(d.get("credit_code") or "").strip(),
                "type": (d.get("credit_type") or "").strip(),
                "nominal": _num(d.get("nominal_amount_eur")),
                "price": _num(d.get("transfer_price_eur")), "date": d.get("date") or ""})
        if d.get("is_credit_declaration") and _num(d.get("declared_total_eur")):
            declarations.append({
                "file": fn, "code": str(d.get("credit_code") or "").strip(),
                "type": (d.get("credit_type") or "").strip(),
                "total": _num(d.get("declared_total_eur"))})

    flags, groups = [], {}
    for c in cessions:
        key = (c["cedente"].lower(), (c["code"] or c["type"]).lower())
        groups.setdefault(key, []).append(c)

    findings = []
    for key, lst in groups.items():
        total_ceded = sum(x["nominal"] for x in lst)
        cessionari = sorted({x["cessionario"] for x in lst if x["cessionario"]})
        plaf_candidates = [d["total"] for d in declarations
                           if (d["code"] and d["code"] == key[1])
                           or (d["type"] and d["type"].lower() == key[1])]
        plaf = max(plaf_candidates) if plaf_candidates else 0
        findings.append({"cedente": lst[0]["cedente"], "credito": key[1],
                         "n_cessioni": len(lst), "cessionari": cessionari,
                         "total_ceded": total_ceded, "plafond": plaf})
        if len(cessionari) > 1:
            flags.append(f"⚠️ Stesso credito «{key[1]}» di {lst[0]['cedente']} ceduto a "
                         f"{len(cessionari)} cessionari diversi: {', '.join(cessionari)}")
        if plaf and total_ceded > plaf * 1.001:
            flags.append(f"⛔ Cessioni totali ({total_ceded:,.0f}€) SUPERANO il plafond "
                         f"dichiarato ({plaf:,.0f}€) per «{key[1]}»")
        seen = {}
        for x in lst:
            k2 = (x["cessionario"].lower(), round(x["nominal"]))
            seen.setdefault(k2, []).append(x["file"])
        for k2, files in seen.items():
            if len(files) > 1 and k2[1]:
                flags.append(f"❓ Stessa cessione ({k2[1]:,.0f}€ a {k2[0]}) documentata in "
                             f"piu' file: {', '.join(files)}")

    verdict = "ALLARME" if any(f.startswith("⛔") for f in flags) else (
        "ATTENZIONE" if flags else "Nessuna anomalia evidente")

    # registra come attività del caso
    lines = [f"🔁 RILEVATORE DOPPIA CESSIONE — {verdict}",
             f"Cessioni rilevate: {len(cessions)} · dichiarazioni credito: {len(declarations)}"]
    for g in findings:
        plf = f" / plafond {g['plafond']:,.0f}€" if g["plafond"] else ""
        lines.append(f"• {g['cedente']} «{g['credito']}»: {g['n_cessioni']} cessioni, "
                     f"ceduto {g['total_ceded']:,.0f}€{plf}; cessionari: "
                     f"{', '.join(g['cessionari']) or 'n/d'}")
    if flags:
        lines.append("FLAG:")
        lines.extend(flags)
    try:
        c = frappe.get_doc("Investigation Case", case)
        c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "Report",
                                     "description": "\n".join(lines)[:1000],
                                     "operator": frappe.session.user})
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "cession_recon activity")

    if wa_phone and sender and lead_name:
        try:
            from thanatos_intel.ingest.operator_console import _reply
            _reply(wa_phone, sender, lead_name, "\n".join(lines)[:3500])
        except Exception:
            pass

    return {"ok": True, "verdict": verdict, "cessions": cessions,
            "declarations": declarations, "findings": findings, "flags": flags}
