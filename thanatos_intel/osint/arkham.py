"""Arkham Intelligence — attribution on-chain (entita / label) per indirizzi.

Chiavi in site_config: arkham_api_key (obbligatoria), arkham_api_base
(default https://api.arkm.com). Etichetta gli indirizzi con l'entita nota
(exchange/CEX, scam, mixer, sanzionati...), aggiorna le Investigation Entity di
tipo Wallet e produce un report di attribuzione sui case collegati.

Esposto dal bottone "Arricchisci con Arkham" su Investigation Case e usato
opportunisticamente da osint/blockchain.py per nominare gli hub scoperti.
"""
import json
import time

import frappe
import requests
from frappe.utils import now_datetime

DEFAULT_BASE = "https://api.arkm.com"

# tipi/entita Arkham che indicano un endpoint di cash-out (VASP/exchange)
CASHOUT_TYPES = {"cex", "exchange"}
# spie testuali (tipo/service/note/label) di attivita illecita
ILLICIT_HINTS = ("scam", "fraud", "phish", "ponzi", "mixer", "tumbler", "sanction",
                 "ofac", "hack", "exploit", "theft", "stolen", "darknet", "ransom")


def _key():
    k = frappe.conf.get("arkham_api_key")
    if not k:
        frappe.throw("arkham_api_key non configurata in site_config.")
    return k


def _base():
    return (frappe.conf.get("arkham_api_base") or DEFAULT_BASE).rstrip("/")


def _get(path, params=None):
    r = requests.get(_base() + path, params=params or {},
                     headers={"API-Key": _key(), "User-Agent": "thanatos-intel"}, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _chain_for(addr):
    a = addr.strip()
    if a.startswith("0x") and len(a) == 42:
        return "ethereum"
    if a[:1] in ("1", "3") or a.lower().startswith("bc1"):
        return "bitcoin"
    return "bitcoin"


def attribute(address, chain=None):
    """Attribution normalizzata per un indirizzo (entita, tipo, service, flag)."""
    address = address.strip()
    chain = chain or _chain_for(address)
    data = _get("/intelligence/address/" + address, {"chain": chain})
    if not data:
        return {"address": address, "chain": chain, "found": False, "entity": None}
    ent = data.get("arkhamEntity") or {}
    lab = data.get("arkhamLabel") or {}
    name = ent.get("name") or lab.get("name")
    etype = (ent.get("type") or "").lower()
    service = ent.get("service") or ""
    blob = " ".join(filter(None, [name, etype, service, ent.get("note") or "",
                                  lab.get("name") or ""])).lower()
    return {
        "address": address, "chain": chain, "found": bool(name),
        "entity": name, "entity_id": ent.get("id"), "type": etype,
        "service": service, "label": lab.get("name"), "website": ent.get("website"),
        "is_user_address": data.get("isUserAddress", False),
        "is_cashout": etype in CASHOUT_TYPES or "exchange" in blob or bool(service),
        "is_illicit": any(h in blob for h in ILLICIT_HINTS),
        "raw": data,
    }


def _label_str(att):
    parts = [p for p in (att.get("entity"), att.get("label")) if p]
    return " — ".join(dict.fromkeys(parts)) or "(nessuna attribuzione)"


def enrich_entity(address, chain=None):
    """Attribuisce un indirizzo e aggiorna la Investigation Entity, se esiste."""
    att = attribute(address, chain)
    if not frappe.db.exists("Investigation Entity", address):
        return att
    ent = frappe.get_doc("Investigation Entity", address)
    ent.last_osint_run = now_datetime()

    raw = {}
    try:
        raw = json.loads(ent.osint_raw) if ent.osint_raw else {}
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {"_prev": str(raw)}
    raw["arkham"] = att.get("raw")
    ent.osint_raw = json.dumps(raw, default=str)[:130000]

    if att.get("found"):
        existing = {r.indicator_type for r in ent.risk_indicators}
        if att["is_illicit"] and "Arkham: entita illecita" not in existing:
            ent.append("risk_indicators", dict(indicator_type="Arkham: entita illecita",
                value=_label_str(att), source="Arkham Intelligence", points=80, verified=1))
            ent.status = "Blacklisted"
        elif att["is_cashout"] and "Arkham: exchange/VASP" not in existing:
            ent.append("risk_indicators", dict(indicator_type="Arkham: exchange/VASP",
                value=_label_str(att) + " — ENDPOINT cash-out: richiedere KYC via autorita",
                source="Arkham Intelligence", points=45, verified=1))
        elif "Arkham: attribuzione" not in existing:
            ent.append("risk_indicators", dict(indicator_type="Arkham: attribuzione",
                value=_label_str(att), source="Arkham Intelligence", points=20, verified=1))

        tag = "[Arkham] " + _label_str(att)
        if att.get("service"):
            tag += " · service: " + att["service"]
        if tag not in (ent.notes or ""):
            ent.notes = (tag + "\n" + (ent.notes or "")).strip()

    ent.save(ignore_permissions=True)
    return att


def _report_html(case_name, results):
    def row(r):
        if not r.get("found"):
            return ("<tr><td><code>%s</code></td>"
                    "<td colspan=4 style='color:#888'>nessuna attribuzione Arkham</td></tr>"
                    % r["address"])
        flags = []
        if r.get("is_illicit"):
            flags.append("<b style='color:#C0392B'>ILLECITO</b>")
        if r.get("is_cashout"):
            flags.append("<b style='color:#B8860B'>EXCHANGE/VASP</b>")
        return ("<tr><td><code>%s</code></td><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>"
                % (r["address"], r.get("entity") or "&mdash;", r.get("type") or "&mdash;",
                   r.get("service") or "&mdash;", " ".join(flags) or "&mdash;"))
    rows = "".join(row(r) for r in results)
    found = sum(1 for r in results if r.get("found"))
    cash = sum(1 for r in results if r.get("is_cashout") and r.get("found"))
    ill = sum(1 for r in results if r.get("is_illicit") and r.get("found"))
    return (
        "<h2>Arkham Intelligence &mdash; attribution indirizzi</h2>"
        "<p>Case <b>%s</b> &middot; generato %s &middot; %d indirizzi &middot; "
        "%d attribuiti &middot; %d exchange/VASP &middot; %d illeciti</p>"
        "<table border=1 cellpadding=4 style='border-collapse:collapse'>"
        "<tr><th>Indirizzo</th><th>Entita</th><th>Tipo</th><th>Service</th><th>Flag</th></tr>"
        "%s</table>"
        "<p style='font-size:11px;color:#666'>Fonte: Arkham Intelligence API. "
        "Le attribuzioni \"exchange/VASP\" sono punti di recupero: identificato il "
        "servizio, richiedere il KYC del titolare tramite autorita giudiziaria/EIO.</p>"
        % (case_name, frappe.utils.now(), len(results), found, cash, ill, rows))


@frappe.whitelist()
def enrich_case_with_arkham(case_name, max_addresses=80):
    """Etichetta con Arkham tutti i wallet del case, aggiorna le entita e allega
    un report di attribuzione. Idempotente sul nome file del report."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    max_addresses = int(max_addresses)
    case = frappe.get_doc("Investigation Case", case_name)

    seen, ordered = set(), []
    for ce in case.case_entities:
        if ce.entity in seen:
            continue
        if frappe.db.get_value("Investigation Entity", ce.entity, "entity_type") == "Wallet":
            seen.add(ce.entity)
            ordered.append(ce.entity)
    ordered = ordered[:max_addresses]

    if not ordered:
        frappe.throw("Nessun wallet collegato al case da attribuire.")

    results = []
    for a in ordered:
        try:
            results.append(enrich_entity(a))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "arkham enrich")
            results.append({"address": a, "found": False})
        time.sleep(0.2)

    found = [r for r in results if r.get("found")]
    cashout = [r for r in found if r.get("is_cashout")]
    illicit = [r for r in found if r.get("is_illicit")]

    html = _report_html(case_name, results)
    stamp = frappe.utils.nowdate().replace("-", "")
    fname = "arkham_attribution_%s.html" % stamp
    old = frappe.db.get_value("File", {"attached_to_doctype": "Investigation Case",
                                       "attached_to_name": case_name, "file_name": fname}, "name")
    if old:
        frappe.delete_doc("File", old, ignore_permissions=True, force=True)
    frappe.get_doc({"doctype": "File", "file_name": fname, "content": html, "is_private": 1,
                    "attached_to_doctype": "Investigation Case",
                    "attached_to_name": case_name}).insert(ignore_permissions=True)

    case.append("case_activities", dict(activity_date=now_datetime(), activity_type="OSINT",
        description=("Attribution Arkham su %d wallet: %d attribuiti, %d exchange/VASP, "
                     "%d entita illecite." % (len(ordered), len(found), len(cashout), len(illicit))),
        operator=frappe.session.user))
    case.save(ignore_permissions=True)
    frappe.db.commit()
    return {"checked": len(ordered), "attributed": len(found),
            "cashout": len(cashout), "illicit": len(illicit), "file": fname}
