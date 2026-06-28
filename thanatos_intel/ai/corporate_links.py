"""Analisi collegamenti societari (network/gruppo) tra le parti del caso.

Dai documenti già analizzati ricostruisce, per ciascuna società, amministratori,
soci, sede, PEC, P.IVA; poi individua i COLLEGAMENTI (amministratori/cognomi/sedi/
PEC comuni, intermediari ricorrenti) e valuta se dietro c'è un GRUPPO o una regìa
unica. È il controllo che smaschera i 'gruppi' dietro le frodi su cessione crediti.
"""
import json
import re
import frappe
from frappe.utils import now_datetime

from thanatos_intel.ai import doc_ingest as DI
from thanatos_intel.ai.case_architect import _resp_text

_SYS = (
    "Sei un analista di intelligence societaria di Thanatos. Ricevi le sintesi dei documenti "
    "di un caso (cessione di crediti d'imposta) e l'elenco delle parti. Ricostruisci la rete "
    "societaria e i collegamenti. Rispondi SOLO con JSON valido: "
    '{"societa": [{"nome":"","piva":"","amministratori":[""],"soci":[""],"sede":"","pec":""}], '
    '"persone_chiave": [{"nome":"","ruolo":"","societa_collegate":[""]}], '
    '"collegamenti": [{"tra":["A","B"],"tipo":"amministratore comune|cognome/famiglia|sede comune|PEC comune|intermediario comune|catena cessione","evidenza":""}], '
    '"gruppo": {"esiste":true|false,"descrizione":"","società_coinvolte":[""]}, '
    '"red_flag": [""]}. '
    "Presta attenzione a cognomi/famiglie ricorrenti tra amministratori (es. stessa famiglia "
    "che controlla più società cessionarie), sedi/domiciliazioni condivise, stessi intermediari/"
    "asseveratori su più operazioni. Italiano."
)


def _format(parsed):
    lines = ["🕸️ ANALISI COLLEGAMENTI SOCIETARI"]
    g = parsed.get("gruppo") or {}
    if g:
        lines.append(("GRUPPO: " + ("SÌ — " if g.get("esiste") else "non evidente — ")
                      + (g.get("descrizione") or ""))[:300])
        if g.get("società_coinvolte") or g.get("societa_coinvolte"):
            lines.append("Coinvolte: " + ", ".join(g.get("società_coinvolte") or g.get("societa_coinvolte") or []))
    for c in (parsed.get("collegamenti") or [])[:12]:
        tra = " ↔ ".join(c.get("tra") or [])
        lines.append(f"• [{c.get('tipo')}] {tra}: {c.get('evidenza','')}"[:240])
    if parsed.get("red_flag"):
        lines.append("RED FLAG: " + "; ".join(parsed["red_flag"])[:400])
    return "\n".join(lines)


@frappe.whitelist()
def analizza_collegamenti(case):
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=["evidence_name", "notes"], order_by="creation asc", limit=0)
    sint = []
    for e in evs:
        for ln in (e.notes or "").split("\n"):
            ln = ln.strip()
            if ln and not ln.startswith(("—", "Autenticità", "Red flag", "Campi", "OCR provider", "Verifica camerale")):
                sint.append(f"- {ln[:300]}")
                break
    parti = []
    c = frappe.get_doc("Investigation Case", case)
    for ce in (c.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity, ["full_name", "entity_type"], as_dict=True)
        if et:
            parti.append(f"{et.full_name} ({et.entity_type})")

    msg = ("Sintesi documenti:\n" + "\n".join(sint[:40]) + "\n\nParti note:\n- "
           + "\n- ".join(sorted(set(parti))[:40]) + "\n\nProduci l'analisi dei collegamenti. Solo JSON.")
    resp = DI._gateway(msg, system=_SYS, task_type="chat")
    parsed = DI._extract_json(_resp_text(resp)) or {}
    text = _format(parsed)
    try:
        c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "OSINT",
                 "description": text[:1800], "operator": frappe.session.user})
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "analizza_collegamenti")
    return {"ok": True, "text": text, "parsed": parsed}
