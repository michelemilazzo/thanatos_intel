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


@frappe.whitelist()
def costruisci_cluster(case):
    """Costruisce/aggiorna un Corporate Group (cluster stile Arkham) dal caso:
    membri = entità del caso, collegamenti = dall'analisi. Riusabile cross-caso."""
    r = analizza_collegamenti(case)
    parsed = r.get("parsed") or {}
    g = parsed.get("gruppo") or {}
    gstr = json.dumps(g, ensure_ascii=False).lower()
    grp = "Gruppo HU/Zhao" if ("zhao" in gstr or "hu " in gstr) else f"Gruppo caso {case}"
    if frappe.db.exists("Corporate Group", grp):
        doc = frappe.get_doc("Corporate Group", grp)
        doc.set("members", [])
        doc.set("links", [])
    else:
        doc = frappe.new_doc("Corporate Group")
        doc.group_name = grp
    doc.group_kind = "Gruppo familiare" if "famil" in gstr else "Rete/Cluster"
    doc.risk_level = "Alto"
    doc.summary = (g.get("descrizione") or r.get("text") or "")[:1000]
    c = frappe.get_doc("Investigation Case", case)
    seen = set()
    for ce in (c.get("case_entities") or []):
        if ce.entity in seen:
            continue
        seen.add(ce.entity)
        doc.append("members", {"entity": ce.entity, "ruolo": (ce.notes or ce.role_in_case or "")[:140]})
    for l in (parsed.get("collegamenti") or [])[:30]:
        tra = l.get("tra") or []
        doc.append("links", {"da": (tra[0] if tra else "")[:140],
                             "a": (tra[1] if len(tra) > 1 else "")[:140],
                             "tipo": (l.get("tipo") or "")[:60],
                             "evidenza": (l.get("evidenza") or "")[:140]})
    # Arricchimento certificato: soci + titolari effettivi (UBO) reali da openapi
    doc._ownership = _arricchisci_ownership(doc, c)
    cur = set(x.strip() for x in (doc.related_cases or "").split(",") if x.strip())
    cur.add(case)
    doc.related_cases = ", ".join(sorted(cur))
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "gruppo": doc.name, "membri": len(doc.members),
            "links": len(doc.links), "ownership": getattr(doc, "_ownership", 0)}


def _arricchisci_ownership(doc, case_doc):
    """Per ogni società del caso con P.IVA nota, aggiunge al cluster i collegamenti
    di proprietà reali (socio→società con quota, UBO→società) da openapi.it.
    In sandbox usa i dati sample; in produzione le quote effettive."""
    try:
        from thanatos_intel.osint import openapi_client as oc
    except Exception:
        return 0
    added = 0
    for ce in (case_doc.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity,
                                 ["full_name", "entity_type", "primary_identifier"], as_dict=True)
        if not et or et.entity_type != "Company":
            continue
        piva = "".join(ch for ch in (et.primary_identifier or "") if ch.isdigit())
        if len(piva) != 11:
            continue
        try:
            r = oc.soci_titolari(piva)
        except Exception:
            continue
        soc = et.full_name or piva
        for s in r.get("soci") or []:
            q = f" {s['quota']}%" if s.get("quota") is not None else ""
            doc.append("links", {"da": (s.get("nome") or "")[:140], "a": soc[:140],
                                 "tipo": f"socio{q}"[:60], "evidenza": (s.get("cf") or "openapi")[:140]})
            added += 1
        for u in r.get("ubo") or []:
            doc.append("links", {"da": (u.get("nome") or "")[:140], "a": soc[:140],
                                 "tipo": "titolare effettivo (UBO)", "evidenza": (u.get("cf") or "openapi")[:140]})
            added += 1
    return added
