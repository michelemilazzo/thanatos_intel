"""OSINT Job orchestrator.

Plan per target type:
- Email      → HIBP
- IP         → AbuseIPDB, IPinfo (+ VT/Shodan/Censys se Deep)
- Domain/Url → RDAP, urlscan (+ SecurityTrails/VT se Deep) + resolve IP
- Hash       → VirusTotal
- Company    → OpenCorporates
"""
import json
import time
from typing import Dict, List

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from thanatos_intel.osint import engine
from thanatos_intel.osint import free_sources as fs

# La ricerca è guidata dal REGISTRY: per ogni target si eseguono TUTTE le fonti
# operative adeguate (vedi _registry_extra). PLAN contiene solo i casi speciali
# che il registry non può chiamare genericamente (dispatch per-chain del wallet).
PLAN = {
    "Wallet": [("wallet", fs.lookup_wallet)],
}

# Allineamento chiavi registry → nome usato nel piano curato (per deduplicare).
_COVER_ALIAS = {
    "opensanctions_local": "opensanctions",
    "vessel_sanctions": "vessel",
}
# Explorer crypto coperti dal dispatcher 'wallet' (lookup_wallet): non eseguirli a parte.
_SKIP_IN_JOB = {"wallet_btc", "wallet_tron", "etherscan"}


def _registry_extra(ttype, covered):
    """Tutte le fonti del registry OPERATIVE per il target, non già nel piano.

    Restituisce [(nome, fn)]. Solo fonti eseguibili ora (gratis o con chiave
    configurata) → nessuno stub da chiave mancante.
    """
    from thanatos_intel.osint import source_registry as sr
    extra = []
    for s in sr.SOURCES:
        if ttype not in s.get("targets", []):
            continue
        if s["key"] in _SKIP_IN_JOB or not s.get("connector"):
            continue
        if not sr._operational(s):
            continue
        name = _COVER_ALIAS.get(s["key"], s["key"])
        if name in covered:
            continue
        try:
            fn = frappe.get_attr(s["connector"])
        except Exception:
            continue
        extra.append((name, fn))
        covered.add(name)
    return extra


class OSINTJob(Document):
    def before_insert(self):
        if not self.title:
            self.title = f"{self.target_type or '?'}: {self.target_value or self.entity or ''}"
        if not self.requested_by:
            self.requested_by = frappe.session.user

    @frappe.whitelist()
    def run(self):
        if self.status == "Running":
            frappe.throw("Job già in esecuzione")
        self.status = "Running"
        self.started_at = now_datetime()
        self.steps = []
        self.save(ignore_permissions=True)
        frappe.db.commit()

        target = (self.target_value or "").strip()
        ttype = self.target_type
        # Ricerca su TUTTE le fonti adeguate al target: piano curato
        # (parametrizzato) + ogni fonte del registry eseguibile ORA (gratis o con
        # chiave configurata) non già coperta. Niente stub di chiavi mancanti.
        plan: List = list(PLAN.get(ttype, []))
        plan += _registry_extra(ttype, {name for name, _ in plan})

        aggregated: Dict[str, dict] = {}
        score = 0
        notes = []

        for name, fn in plan:
            t0 = time.time()
            step = self.append("steps", {
                "connector": name, "status": "Running",
                "started": now_datetime(),
            })
            try:
                res = fn(target)
                step.elapsed_ms = int((time.time() - t0) * 1000)
                step.result_json = json.dumps(res, default=str)[:60000]
                if res.get("stub"):
                    step.status = "Stub"
                    step.note = res.get("message") or "no api key"
                elif res.get("error"):
                    step.status = "Error"
                    step.note = res.get("error")
                else:
                    step.status = "Ok"
                    d, n = _score_delta(name, res)
                    step.score_delta = d
                    score += d
                    if n:
                        step.note = n
                        notes.append(f"{name}: {n}")
                aggregated[name] = res
            except Exception as e:
                step.status = "Error"
                step.note = str(e)[:200]
                step.elapsed_ms = int((time.time() - t0) * 1000)
            self.save(ignore_permissions=True)
            frappe.db.commit()

        # Resolve domain → IP and chain IP lookups
        if ttype in ("Domain", "Url") and aggregated.get("rdap", {}).get("domain"):
            import socket
            try:
                ip = socket.gethostbyname(aggregated["rdap"]["domain"])
                aggregated["resolved_ip"] = ip
                ip_res = engine.lookup_ip(ip)
                aggregated["abuseipdb"] = ip_res
                d, n = _score_delta("abuseipdb", ip_res)
                score += d
                if n:
                    notes.append(f"resolved {ip}: {n}")
            except Exception:
                pass

        self.aggregated_json = json.dumps(aggregated, default=str)[:120000]
        self.risk_score = max(0, min(100, score))
        self.risk_band = _band(self.risk_score)
        self.summary = " · ".join(notes)[:280] or f"{len(plan)} connettori, nessun segnale forte"
        self.completed_at = now_datetime()
        self.status = "Completed"

        if self.entity:
            try:
                ent = frappe.get_doc("Entity", self.entity)
                ent.risk_score = max(ent.risk_score or 0, self.risk_score)
                ent.save(ignore_permissions=True)
            except Exception:
                pass

        self.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": self.status, "risk_score": self.risk_score,
                "risk_band": self.risk_band, "summary": self.summary}


def _band(s: int) -> str:
    if s >= 75:
        return "Critical"
    if s >= 50:
        return "High"
    if s >= 25:
        return "Medium"
    if s > 0:
        return "Low"
    return "Low"


def _score_delta(connector: str, res: dict):
    """Returns (delta, short_note)."""
    if not res or res.get("error") or res.get("stub"):
        return 0, ""
    if connector == "hibp":
        if res.get("found"):
            n = len(res.get("breaches") or [])
            return min(15 + n * 2, 35), f"{n} breach"
        return 0, ""
    if connector == "abuseipdb":
        s = res.get("score") or 0
        if s >= 75:
            return 30, f"abuse score {s}"
        if s >= 25:
            return 15, f"abuse score {s}"
        if s > 0:
            return 5, f"abuse score {s}"
        return 0, ""
    if connector == "virustotal":
        mal = res.get("malicious", 0) or 0
        sus = res.get("suspicious", 0) or 0
        if mal >= 5:
            return 35, f"VT malicious={mal}"
        if mal > 0:
            return 20, f"VT malicious={mal}"
        if sus > 0:
            return 10, f"VT suspicious={sus}"
        return 0, ""
    if connector == "urlscan":
        scans = res.get("scans") or []
        mal = sum(1 for s in scans if s.get("malicious"))
        if mal >= 2:
            return 15, f"{mal} scan malevole"
        if mal == 1:
            return 8, "1 scan malevola"
        return 0, ""
    if connector == "shodan":
        vulns = res.get("vulns") or []
        if len(vulns) >= 5:
            return 15, f"{len(vulns)} CVE esposte"
        if vulns:
            return 8, f"{len(vulns)} CVE"
        ports = res.get("ports") or []
        risky = {23, 21, 3389, 445, 1433, 3306, 5432, 6379, 9200, 27017}
        hit = [p for p in ports if p in risky]
        if hit:
            return 5, f"porte rischio: {hit[:5]}"
        return 0, ""
    if connector == "rdap":
        events = res.get("registered")
        try:
            from datetime import datetime
            reg = datetime.fromisoformat((events or "").replace("Z", "+00:00"))
            age_days = (datetime.utcnow().replace(tzinfo=reg.tzinfo) - reg).days
            if age_days < 30:
                return 12, f"dominio registrato {age_days}gg fa"
            if age_days < 180:
                return 5, f"dominio recente ({age_days}gg)"
        except Exception:
            pass
        return 0, ""
    if connector == "ipinfo":
        privacy = res.get("privacy") or {}
        if privacy.get("vpn") or privacy.get("tor") or privacy.get("proxy"):
            return 8, "VPN/proxy/Tor"
        return 0, ""
    if connector == "opencorporates":
        if (res.get("total") or 0) == 0:
            return 8, "nessun match registro"
        return 0, ""
    if connector == "opensanctions":
        if res.get("found"):
            m = res.get("matches") or []
            topics = {t for h in m for t in (h.get("topics") or [])}
            if "sanction" in topics or "crime" in topics:
                return 40, f"{len(m)} match sanzioni/crimine"
            if "role.pep" in topics or "poi" in topics:
                return 20, f"{len(m)} match PEP/POI"
            return 15, f"{len(m)} match liste"
        return 0, ""
    if connector == "wallet":
        if res.get("error"):
            return 0, ""
        rx = res.get("total_received_btc") or res.get("balance_eth") or 0
        n = res.get("tx_count") or 0
        return 0, f"{res.get('chain', '?')}: {n} tx"
    if connector == "username":
        p = res.get("profiles") or []
        if p:
            return 0, f"{len(p)} profili: " + ", ".join(x["site"] for x in p)
        return 0, ""
    if connector == "wayback":
        if res.get("archived"):
            return 0, f"primo snapshot {res.get('first_snapshot') or '?'}"
        return 0, ""
    if connector == "viewdns":
        c = res.get("count") or 0
        if c:
            return 0, f"{c} IP storici"
        return 0, ""
    if connector == "courtlistener":
        c = res.get("count") or 0
        if c:
            return 10, f"{c} procedimenti USA"
        return 0, ""
    if connector == "wikidata":
        e = res.get("entities") or []
        if e:
            return 0, f"{len(e)} entità Wikidata"
        return 0, ""
    if connector == "commoncrawl":
        c = res.get("count") or 0
        if c:
            return 0, f"{c} URL indicizzati"
        return 0, ""
    if connector == "greynoise":
        if res.get("classification") == "malicious":
            return 20, "GreyNoise malicious"
        if res.get("noise"):
            return 5, "GreyNoise noise"
        return 0, ""
    if connector == "otx":
        p = res.get("pulses") or 0
        if p >= 5:
            return 15, f"OTX {p} pulse"
        if p:
            return 8, f"OTX {p} pulse"
        return 0, ""
    if connector == "pulsedive":
        risk = (res.get("risk") or "").lower()
        if risk in ("high", "critical"):
            return 18, f"Pulsedive {risk}"
        if risk == "medium":
            return 8, "Pulsedive medium"
        return 0, ""
    if connector == "nominatim":
        if res.get("best"):
            return 0, "geocodificato"
        return 0, ""
    if connector == "holehe":
        s = res.get("services") or []
        if s:
            return 0, f"{len(s)} servizi (holehe)"
        return 0, ""
    if connector == "exiftool":
        if res.get("has_gps"):
            return 0, "GPS nei metadati"
        return 0, ""
    if connector == "mapillary":
        c = res.get("count") or 0
        if c:
            return 0, f"{c} foto street-level"
        return 0, ""
    return 0, ""


@frappe.whitelist()
def create_and_run(target_type: str, target_value: str,
                   mode: str = "Quick Scan",
                   investigation_case: str = None,
                   client: str = None) -> dict:
    """Crea un OSINT Job e lo esegue subito. Ritorna name + risultato."""
    if frappe.session.user == "Guest":
        frappe.throw("Accesso negato.", frappe.PermissionError)
    # mode elevati riservati a ruoli operativi
    if mode in ("Deep Investigation", "Legal Review"):
        allowed = {"Investigator", "Investigation Manager", "Lawyer",
                   "Accountant", "System Manager"}
        if not (set(frappe.get_roles()) & allowed):
            frappe.throw("Modalità riservata: il tuo profilo può eseguire solo Quick Scan.",
                         frappe.PermissionError)
    from thanatos_intel.thanatos_osint.doctype.entity.entity import upsert
    entity = upsert(_entity_type(target_type), target_value)
    job = frappe.get_doc({
        "doctype": "OSINT Job",
        "target_type": target_type,
        "target_value": target_value,
        "mode": mode,
        "entity": entity,
        "investigation_case": investigation_case,
        "client": client,
    })
    job.insert(ignore_permissions=True)
    job.run()
    return {"name": job.name, "entity": entity,
            "risk_score": job.risk_score, "risk_band": job.risk_band,
            "summary": job.summary}


def _entity_type(target_type: str) -> str:
    return target_type if target_type in (
        "Email", "IP", "Domain", "Url", "Hash", "Phone",
        "Username", "Wallet", "Company", "Person", "File") else "Document"
