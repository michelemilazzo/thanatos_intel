"""Analisi collegamenti societari (network/gruppo) tra le parti del caso.

Dai documenti già analizzati ricostruisce, per ciascuna società, amministratori,
soci, sede, PEC, P.IVA; poi individua i COLLEGAMENTI (amministratori/cognomi/sedi/
PEC comuni, intermediari ricorrenti) e valuta se dietro c'è un GRUPPO o una regìa
unica. È il controllo che smaschera i 'gruppi' dietro le frodi su cessione crediti.
"""
import json
import re
import frappe
import math
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


@frappe.whitelist()
def graph(group):
    """Rende il cluster come grafo SVG (societa'=rettangoli, persone=cerchi, archi etichettati
    col tipo di legame/quota) — vista 'stile Arkham' del Corporate Group."""
    if not group or not frappe.db.exists("Corporate Group", group):
        return ""
    doc = frappe.get_doc("Corporate Group", group)
    types = {}
    for m in (doc.members or []):
        nm = (m.entity_name or m.entity or "").strip()
        if nm:
            types[nm] = (m.entity_type or "").lower()
    edges = []
    for l in (doc.links or []):
        a = (l.da or "").strip(); b = (l.a or "").strip()
        if a and b:
            edges.append((a, b, (l.tipo or "").strip()))
            types.setdefault(a, ""); types.setdefault(b, "")
    names = list(types.keys())
    if not names:
        return "<div style='color:#888'>Nessun membro/collegamento nel cluster.</div>"

    W, Hh, cx, cy = 640, 460, 320, 220
    R = 165 if len(names) > 1 else 0
    pos = {}
    for i, nm in enumerate(names):
        ang = 2 * math.pi * i / max(len(names), 1) - math.pi / 2
        pos[nm] = (cx + R * math.cos(ang), cy + R * math.sin(ang))

    def is_company(t):
        return "compan" in t or "societ" in t or "srl" in t or "spa" in t

    out = ["<svg viewBox='0 0 %d %d' style='width:100%%;max-width:680px;border:1px solid #eee;border-radius:8px;background:#0d1117'>" % (W, Hh)]
    # archi
    for a, b, tipo in edges:
        x1, y1 = pos[a]; x2, y2 = pos[b]
        out.append("<line x1='%.0f' y1='%.0f' x2='%.0f' y2='%.0f' stroke='#3b4453' stroke-width='1.5'/>" % (x1, y1, x2, y2))
        if tipo:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            out.append("<text x='%.0f' y='%.0f' fill='#9aa4b2' font-size='10' text-anchor='middle'>%s</text>" % (mx, my, frappe.utils.escape_html(tipo)[:24]))
    # nodi
    for nm in names:
        x, y = pos[nm]
        comp = is_company(types.get(nm, ""))
        label = frappe.utils.escape_html(nm)[:26]
        if comp:
            out.append("<rect x='%.0f' y='%.0f' width='124' height='34' rx='5' fill='#1f6feb' stroke='#388bfd'/>" % (x - 62, y - 17))
            out.append("<text x='%.0f' y='%.0f' fill='#fff' font-size='11' font-weight='600' text-anchor='middle'>%s</text>" % (x, y + 4, label))
        else:
            out.append("<circle cx='%.0f' cy='%.0f' r='24' fill='#238636' stroke='#2ea043'/>" % (x, y))
            out.append("<text x='%.0f' y='%.0f' fill='#fff' font-size='10' text-anchor='middle'>%s</text>" % (x, y + 40, label))
    # legenda
    out.append("<rect x='10' y='%d' width='13' height='13' rx='3' fill='#1f6feb'/><text x='28' y='%d' fill='#9aa4b2' font-size='11'>Societa'</text>" % (Hh - 24, Hh - 14))
    out.append("<circle cx='100' cy='%d' r='7' fill='#238636'/><text x='112' y='%d' fill='#9aa4b2' font-size='11'>Persona</text>" % (Hh - 17, Hh - 14))
    out.append("</svg>")
    return "".join(out)
