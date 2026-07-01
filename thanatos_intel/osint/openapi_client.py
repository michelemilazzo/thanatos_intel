"""Client unificato openapi.it — tutti gli strumenti investigativi a disposizione.

Un solo token Bearer (site_config: registro_imprese_token) dà accesso a tutte le
famiglie. Sandbox/prod si commuta con openapi_sandbox (site_config) → host test.*.

Due pattern:
  • SYNC  — GET/POST che ritorna subito il dato (company soci/ubo, KYC PEP/sanzioni).
  • ASYNC — POST crea una richiesta {id, status:PENDING} → si fa POLL su un endpoint
            risultato finché state ∈ (COMPLETED/completed/processed/DONE).

`strumenti()` ritorna il CATALOGO completo (per UI/console: cosa è disponibile,
sync/async, fascia di costo). Le funzioni investigative scrivono un reperto sul caso.
"""
import time
import frappe
from frappe.utils import now_datetime

# ── host per servizio (prod → sandbox test.*) ────────────────────────────────
_HOSTS = {
    "company":  "company.openapi.com",
    "imprese":  "imprese.openapi.it",
    "risk":     "risk.openapi.com",
    "trust":    "trust.openapi.com",
    "catasto":  "catasto.openapi.it",
    "visure":   "visurecamerali.openapi.it",
    "targa":    "targa.openapi.it",
    "auto":     "automotive.openapi.com",
    "rintraccio": "rintraccio.openapi.it",
    "geocoding": "geocoding.openapi.it",
}

# stati "finito" per l'async
_DONE = {"completed", "processed", "done", "ok", "evaso", "success"}
_FAIL = {"failed", "error", "rejected", "ko"}


def _token():
    # PROD usa registro_imprese_token_prod (token Produzione openapi); SANDBOX il token di test.
    if frappe.conf.get("openapi_sandbox"):
        return frappe.conf.get("registro_imprese_token") or frappe.conf.get("openapi_token")
    return (frappe.conf.get("registro_imprese_token_prod")
            or frappe.conf.get("registro_imprese_token") or frappe.conf.get("openapi_token"))


def _base(service):
    host = _HOSTS[service]
    return f"https://test.{host}" if frappe.conf.get("openapi_sandbox") else f"https://{host}"


def _hdr():
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _get(service, path, params=None):
    import requests
    r = requests.get(f"{_base(service)}{path}", headers=_hdr(), params=params or {}, timeout=40)
    return r.status_code, (r.json() if r.text else {})


def _post(service, path, body):
    import requests
    r = requests.post(f"{_base(service)}{path}", headers=_hdr(), json=body, timeout=60)
    return r.status_code, (r.json() if r.text else {})


def _async(service, post_path, body, result_path, max_wait=25):
    """POST richiesta → poll su result_path/{id} finché evasa. Ritorna (data, err)."""
    code, body_r = _post(service, post_path, body)
    if code not in (200, 201):
        return None, f"{service} HTTP {code}: {(body_r or {}).get('message') or ''}"
    data = body_r.get("data") or {}
    state = (data.get("state") or data.get("status") or "").lower()
    rid = data.get("id")
    # KYC e simili tornano già COMPLETED con entità inline
    if state in _DONE or data.get("entities") or data.get("esito") not in (None, "PENDING"):
        if state not in ("pending", "processing", "") or data.get("entities"):
            return data, None
    if not rid:
        return data, None
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(2)
        c2, b2 = _get(service, f"{result_path}/{rid}")
        d2 = (b2 or {}).get("data") or {}
        st = (d2.get("state") or d2.get("status") or "").lower()
        if st in _DONE or d2.get("esito") not in (None, "PENDING") or d2.get("evidences"):
            return d2, None
        if st in _FAIL:
            return d2, f"richiesta {st}"
    return {"id": rid, "status": "PENDING", "pending": True}, None


def _evidence(case, title, lines, source="openapi.it"):
    if not case:
        return None
    try:
        ev = frappe.get_doc({
            "doctype": "Investigation Evidence", "investigation_case": case,
            "evidence_name": title[:140], "evidence_type": "Document", "source": source,
            "acquisition_date": now_datetime(), "custody_status": "Received",
            "notes": "\n".join(str(x) for x in lines if x)[:1000]})
        ev.flags.ignore_mandatory = True
        ev.insert(ignore_permissions=True)
        frappe.db.commit()
        return ev.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "openapi_client evidence")
        return None


def _digits(s):
    return "".join(c for c in (s or "") if c.isdigit())


# ── SOCI + TITOLARI EFFETTIVI (UBO) — sync ──────────────────────────────────
@frappe.whitelist()
def soci_titolari(piva, investigation_case=None):
    """Compagine sociale (quote) + titolari effettivi (UBO, persona fisica)."""
    p = _digits(piva)
    out = {"piva": p, "soci": [], "ubo": []}
    if len(p) != 11:
        out["error"] = "P.IVA non valida"
        return out
    c, b = _get("company", f"/IT-shareholders/{p}")
    if c == 200:
        for s in (b.get("data") or []):
            nome = s.get("companyName") or " ".join(x for x in [s.get("name"), s.get("surname")] if x)
            out["soci"].append({"nome": nome, "cf": s.get("taxCode"), "quota": s.get("percentShare")})
    c, b = _get("company", f"/IT-ubo/{p}")
    if c == 200:
        for u in (b.get("data") or []):
            out["ubo"].append({"nome": " ".join(x for x in [u.get("name"), u.get("surname")] if x),
                               "cf": u.get("taxCode"), "nascita": u.get("birthDate"),
                               "luogo": u.get("birthTown")})
    lines = [f"Compagine e titolari effettivi — P.IVA {p}", ""]
    lines.append("SOCI: " + ("; ".join(f"{s['nome']} ({s['quota']}%)" for s in out["soci"]) or "—"))
    lines.append("UBO (titolari effettivi): " +
                 ("; ".join(f"{u['nome']} [{u['cf']}]" for u in out["ubo"]) or "—"))
    out["evidence"] = _evidence(investigation_case, f"Soci+UBO — P.IVA {p}", lines)
    return out


# ── SCREENING KYC: PEP / sanzioni / adverse media — sync ─────────────────────
@frappe.whitelist()
def screening_kyc(query, mode="pep", investigation_case=None, birth_date=None, entity_type=None):
    """mode ∈ pep | sanction_list | adverse_media | full. query = nome soggetto."""
    paths = {"pep": "/WW-kyc-pep", "sanction_list": "/WW-kyc-sanction_list",
             "adverse_media": "/WW-kyc-adverse_media", "full": "/WW-kyc-full"}
    q = {"name": query}
    if birth_date:
        q["birthDate"] = birth_date
    if entity_type:
        q["entityType"] = entity_type
    data, err = _async("risk", paths.get(mode, "/WW-kyc-pep"), {"query": q}, "/WW-kyc-full")
    if err:
        return {"error": err, "query": query, "mode": mode}
    ents = data.get("entities") or []
    hits = []
    for e in ents:
        nm = (e.get("names") or [{}])[0]
        hits.append({"nome": nm.get("full_name") or nm.get("last_name"),
                     "tipo": e.get("entity_type"), "id": e.get("id")})
    lines = [f"Screening {mode.upper()} — «{query}»", f"Match: {len(hits)}"]
    lines += [f"• {h['nome']} ({h['tipo']})" for h in hits[:15]]
    out = {"query": query, "mode": mode, "match": len(hits), "hits": hits,
           "state": data.get("state")}
    out["evidence"] = _evidence(investigation_case,
                                f"Screening {mode} — {query}", lines, source="openapi risk KYC")
    return out


# ── NEGATIVITÀ persona/impresa (protesti, pregiudizievoli) — async ──────────
@frappe.whitelist()
def negativita(cf_piva, investigation_case=None, max_wait=25):
    data, err = _async("risk", "/IT-negativita", {"cf_piva": cf_piva}, "/IT-richiesta", max_wait=int(max_wait))
    if err:
        return {"error": err, "cf_piva": cf_piva}
    out = {"cf_piva": cf_piva, "status": data.get("status") or data.get("state"),
           "esito": data.get("esito"), "pending": data.get("pending")}
    lines = [f"Negatività — {cf_piva}", f"Esito: {out['esito'] or out['status']}"]
    out["evidence"] = _evidence(investigation_case, f"Negatività — {cf_piva}", lines,
                                source="openapi risk")
    return out


# ── PATRIMONIALE persona (beni intestati) — async ───────────────────────────
@frappe.whitelist()
def patrimoniale(name, surname, tax_code, investigation_case=None, max_wait=25):
    data, err = _async("risk", "/IT-patrimoniale-persona",
                       {"name": name, "surname": surname, "taxCode": tax_code}, "/IT-richiesta", max_wait=int(max_wait))
    if err:
        return {"error": err, "tax_code": tax_code}
    out = {"tax_code": tax_code, "soggetto": f"{name} {surname}",
           "status": data.get("status") or data.get("state"), "pending": data.get("pending"),
           "esito": data.get("esito")}
    lines = [f"Patrimoniale — {name} {surname} [{tax_code}]",
             f"Stato: {out['status']}" + (" (in elaborazione)" if out["pending"] else "")]
    out["evidence"] = _evidence(investigation_case, f"Patrimoniale — {name} {surname}", lines,
                                source="openapi risk")
    return out


# ── VERIFICA IBAN (titolare, banca, validità) — trust ───────────────────────
@frappe.whitelist()
def verifica_iban(iban, investigation_case=None):
    code, b = _post("trust", "/iban-advanced", {"iban": iban})
    if code not in (200, 201):
        return {"error": f"trust HTTP {code}: {(b or {}).get('message') or ''}", "iban": iban}
    d = (b or {}).get("data") or {}
    out = {"iban": iban, "valido": d.get("valid"), "banca": d.get("bank") or d.get("bankName"),
           "titolare": d.get("owner") or d.get("holder"), "paese": d.get("country")}
    lines = [f"Verifica IBAN {iban}", f"Valido: {out['valido']} · Banca: {out['banca'] or '—'}",
             f"Titolare: {out['titolare'] or '—'}"]
    out["evidence"] = _evidence(investigation_case, f"Verifica IBAN — {iban}", lines,
                                source="openapi trust")
    return out


# ── VEICOLO per targa (proprietario, assicurazione) — automotive ────────────
@frappe.whitelist()
def veicolo(targa, investigation_case=None):
    code, b = _get("targa", "/auto", {"targa": targa})
    if code != 200:
        return {"error": f"targa HTTP {code}: {(b or {}).get('message') or ''}", "targa": targa}
    d = (b or {}).get("data") or {}
    out = {"targa": targa, "dati": d}
    lines = [f"Veicolo targa {targa}", str(d)[:400]]
    out["evidence"] = _evidence(investigation_case, f"Veicolo — {targa}", lines, source="openapi targa")
    return out


# ── CATALOGO STRUMENTI — la mappa di tutto ciò che è a disposizione ─────────
CATALOGO = [
    {"famiglia": "Company / Imprese", "servizio": "company.openapi.com · imprese.openapi.it",
     "pattern": "sync", "fascia": "€",
     "strumenti": ["Visura sintetica (IT-advanced/full)", "Soci e quote (IT-shareholders)",
                   "Titolari effettivi UBO (IT-ubo)", "AML company (IT-aml)", "PEC (IT-pec)",
                   "Stakeholders", "Cross-border EU/GB/DE/FR/ES/CH (+WW)"],
     "uso": "Compagine, controllo, gruppo societario, mappa beneficiari effettivi"},
    {"famiglia": "Risk — Due diligence", "servizio": "risk.openapi.com",
     "pattern": "async", "fascia": "€€",
     "strumenti": ["KYC PEP", "KYC Sanction list", "KYC Adverse media", "Negatività (protesti/pregiudizievoli)",
                   "Patrimoniale persona (beni)", "Credit score", "Report azienda/persona", "Eredi"],
     "uso": "Reputazione, esposizione, capacità patrimoniale, screening compliance"},
    {"famiglia": "Trust — Digital footprint", "servizio": "trust.openapi.com",
     "pattern": "sync/async", "fascia": "€",
     "strumenti": ["Verifica IBAN", "Verifica email", "Verifica telefono/mobile", "IP", "URL/phishing",
                   "Identity verification (IDV)"],
     "uso": "Antifrode pagamenti, validazione contatti, footprint digitale soggetto"},
    {"famiglia": "Catasto & Ipoteche", "servizio": "catasto.openapi.it",
     "pattern": "async", "fascia": "€€",
     "strumenti": ["Visura catastale", "Ispezione ipotecaria nazionale", "Elenco/dettaglio note",
                   "Estratto di mappa", "Elaborato planimetrico", "Ricerca per indirizzo"],
     "uso": "Beni immobili intestati, ipoteche, pignoramenti, garanzie reali"},
    {"famiglia": "Visure camerali ufficiali", "servizio": "visurecamerali.openapi.it",
     "pattern": "async (PDF)", "fascia": "€€",
     "strumenti": ["Ordinaria/storica società capitale/persone", "Soci attivi", "Bilancio ottico",
                   "Certificato iscrizione/vigenza"],
     "uso": "Documenti probatori da fascicolo (PDF ufficiale Registro Imprese)"},
    {"famiglia": "Rintraccio anagrafico", "servizio": "rintraccio.openapi.it",
     "pattern": "async", "fascia": "€€",
     "strumenti": ["Anagrafica completa", "Telefoni associati", "Verifica CF", "Negatività"],
     "uso": "Localizzazione soggetto, recapiti, identità"},
    {"famiglia": "Veicoli", "servizio": "targa.openapi.it · automotive.openapi.com",
     "pattern": "sync", "fascia": "€",
     "strumenti": ["Targa→auto/moto (IT)", "Assicurazione", "Cross-border DE/ES/FR/PT/UK"],
     "uso": "Veicoli intestati, copertura assicurativa, asset mobili"},
    {"famiglia": "Geo & Anagrafiche", "servizio": "geocoding · cap · comuni · europeanvat",
     "pattern": "sync", "fascia": "free/€",
     "strumenti": ["Geocode/reverse", "CAP/comuni/province/ISTAT", "VIES VAT EU"],
     "uso": "Normalizzazione indirizzi, validazione partite IVA UE"},
    {"famiglia": "Notifiche & Documenti", "servizio": "ufficiopostale · pec · firmadigitale · esignature · pdf",
     "pattern": "varie", "fascia": "€-€€",
     "strumenti": ["Raccomandata/atti giudiziari", "PEC", "Firma elettronica/QES", "Marche temporali", "PDF"],
     "uso": "Notifiche legali tracciate, firma e timestamp probatorio"},
]


@frappe.whitelist()
# ── VISURA CAMERALE ORDINARIA (async, PDF ufficiale) ─────────────────────────
@frappe.whitelist()
def visura(piva, tipo="ordinaria", investigation_case=None, max_wait=90):
    """Visura camerale ufficiale (visurecamerali.openapi.it).
    tipo ∈ ordinaria | storica | soci | bilancio. Ritorna PDF id + evidence."""
    p = _digits(piva)
    if len(p) != 11:
        return {"error": "P.IVA non valida", "piva": piva}
    paths = {
        "ordinaria": "/IT-ordinaria",
        "storica":   "/IT-storica",
        "soci":      "/IT-soci",
        "bilancio":  "/IT-bilancio-ottico",
    }
    post_path = paths.get(tipo, "/IT-ordinaria")
    data, err = _async("visure", post_path, {"taxCode": p}, "/richiesta", max_wait=max_wait)
    if err:
        return {"error": err, "piva": p}
    out = {"piva": p, "tipo": tipo, "id": (data or {}).get("id"), "status": (data or {}).get("status") or (data or {}).get("state"), "dati": data or {}}
    lines = [f"Visura camerale {tipo} — P.IVA {p}",
             f"ID richiesta: {out['id']}", f"Status: {out['status']}"]
    out["evidence"] = _evidence(investigation_case, f"Visura {tipo} — {p}", lines,
                                source="openapi visurecamerali")
    return out


# ── CATASTO / IPOTECHE (async) ───────────────────────────────────────────────
@frappe.whitelist()
def catasto(subject, tipo="visura_soggetto", investigation_case=None, max_wait=90):
    """Catasto/ipoteche (catasto.openapi.it).
    tipo ∈ visura_soggetto | ispezione_ipotecaria | estratto_mappa.
    subject = CF/P.IVA per visura_soggetto/ipotecaria; per estratto_mappa e' un dict
    con foglio/particella/comune (passalo come JSON string)."""
    paths = {
        "visura_soggetto":      "/IT-visura-catastale-soggetto",
        "ispezione_ipotecaria": "/IT-ispezione-ipotecaria",
        "estratto_mappa":       "/IT-estratto-mappa",
    }
    post_path = paths.get(tipo, "/IT-visura-catastale-soggetto")
    if tipo == "estratto_mappa":
        import json as _json
        body = _json.loads(subject) if isinstance(subject, str) else (subject or {})
    else:
        s = _digits(subject)
        if len(s) not in (11, 16):
            return {"error": "CF/P.IVA non valido", "subject": subject}
        body = {"taxCode": s}
    data, err = _async("catasto", post_path, body, "/richiesta", max_wait=max_wait)
    if err:
        return {"error": err, "subject": subject}
    out = {"subject": subject, "tipo": tipo, "id": (data or {}).get("id"),
           "status": (data or {}).get("status") or (data or {}).get("state"), "dati": data or {}}
    lines = [f"Catasto {tipo} — {subject}",
             f"ID richiesta: {out['id']}", f"Status: {out['status']}"]
    out["evidence"] = _evidence(investigation_case, f"Catasto {tipo} — {subject}", lines,
                                source="openapi catasto")
    return out


def risolvi_piva(name):
    """Nome/ragione sociale → P.IVA (company IT-search → IT-start)."""
    code, b = _get("company", "/IT-search", {"companyName": name})
    if code != 200 or not (b.get("data")):
        return {"name": name, "piva": None, "error": (b or {}).get("message") or f"HTTP {code}"}
    rid = b["data"][0].get("id")
    code2, b2 = _get("company", f"/IT-start/{rid}")
    rec = ((b2.get("data") or [{}])[0] if isinstance(b2.get("data"), list) else b2.get("data")) or {}
    return {"name": name, "piva": rec.get("vatCode") or rec.get("taxCode"),
            "denominazione": rec.get("companyName")}


@frappe.whitelist()
def risolvi_pive_caso(case):
    """Per ogni società del caso senza P.IVA, la risolve da openapi e la scrive
    su Investigation Entity.primary_identifier. Accende i bottoni Visura/Soci/UBO."""
    c = frappe.get_doc("Investigation Case", case)
    done, skip = [], 0
    for ce in (c.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity,
                                 ["name", "full_name", "entity_type", "primary_identifier"], as_dict=True)
        if not et or et.entity_type != "Company":
            continue
        if len("".join(ch for ch in (et.primary_identifier or "") if ch.isdigit())) == 11:
            skip += 1
            continue
        r = risolvi_piva(et.full_name or ce.entity)
        if r.get("piva"):
            frappe.db.set_value("Investigation Entity", et.name, "primary_identifier", r["piva"])
            done.append({"nome": et.full_name, "piva": r["piva"]})
    frappe.db.commit()
    return {"risolte": done, "gia_presenti": skip, "tot": len(done)}


@frappe.whitelist()
def screening_free(query, investigation_case=None):
    """Screening sanzioni/PEP GRATUITO via OpenSanctions (cache locale 285k:
    aggrega OFAC/UN/EU/Interpol). Alternativa free a risk WW-kyc-*."""
    try:
        from thanatos_intel.osint import free_sources
        res = free_sources.screen_sanctions(query) or {}
    except Exception as e:
        return {"query": query, "error": str(e)[:160]}
    matches = res.get("matches") or res.get("results") or []
    n = res.get("total") if res.get("total") is not None else len(matches)
    hits = []
    for m in (matches if isinstance(matches, list) else [])[:15]:
        hits.append({"nome": m.get("name") or m.get("caption") or m.get("full_name"),
                     "tipo": m.get("schema") or m.get("type"), "score": m.get("score")})
    lines = [f"Screening sanzioni/PEP (OpenSanctions, free) — «{query}»", f"Match: {n}"]
    lines += [f"• {h['nome']} ({h.get('tipo')})" for h in hits]
    out = {"query": query, "match": n, "hits": hits, "fonte": "OpenSanctions (free)",
           "offline": res.get("offline"), "stub": res.get("stub")}
    out["evidence"] = _evidence(investigation_case, f"Screening free — {query}", lines,
                                source="OpenSanctions")
    return out


@frappe.whitelist()
def case_entities(case):
    """Entità del caso con identificativi normalizzati, per i bottoni per-entità."""
    import re
    out = []
    c = frappe.get_doc("Investigation Case", case)
    for i, ce in enumerate(c.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity,
                                 ["full_name", "entity_type", "primary_identifier"], as_dict=True)
        if not et:
            continue
        ident = et.primary_identifier or ""
        digits = "".join(ch for ch in ident if ch.isdigit())
        piva = digits if len(digits) == 11 else None
        cf = None
        m = re.search(r"\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b", ident.upper())
        if m:
            cf = m.group(1)
        out.append({"idx": i, "entity": ce.entity, "full_name": et.full_name or ce.entity,
                    "type": et.entity_type, "piva": piva, "cf": cf, "ident": ident})
    return {"entities": out}


@frappe.whitelist()
def strumenti():
    """Catalogo di tutti gli strumenti openapi.it a disposizione + stato connessione."""
    return {
        "connesso": bool(_token()),
        "ambiente": "sandbox" if frappe.conf.get("openapi_sandbox") else "produzione",
        "famiglie": CATALOGO,
        "totale_servizi": len(_HOSTS),
    }


@frappe.whitelist()
def enqueue_lookup(kind, value=None, investigation_case=None, name=None, surname=None, tax_code=None, self_mode=0):
    """Esegue in background i servizi openapi lenti (async); il risultato (evidence)
    finisce sul caso. Evita timeout/503 nella richiesta web.
    Pre-pagamento: blocca se il wallet del cliente non copre il prezzo.
    self_mode=1 → consegna anche il risultato (file) al portale/email del cliente."""
    if investigation_case:
        client = frappe.db.get_value("Investigation Case", investigation_case, "client")
        if client:
            from thanatos_intel.osint.tool_catalog import tool_price, tool_base_price
            from thanatos_intel.billing.credits import ensure_credit
            from thanatos_intel.billing.mmos_wallet import mmos_ensure
            ensure_credit(client, tool_price(investigation_case, kind), kind)
            mmos_ensure(tool_base_price(investigation_case, kind), label=kind)
    frappe.enqueue("thanatos_intel.osint.openapi_client._run_lookup_bg", queue="long", timeout=240,
                   kind=kind, value=value, investigation_case=investigation_case,
                   name=name, surname=surname, tax_code=tax_code, self_mode=int(self_mode or 0))
    return {"queued": True}


def _deliver_lookup_result(case, res):
    """Copia il testo del referto (Evidence) in un file e lo consegna (portale+email)."""
    ev_name = res.get("evidence") if res else None
    if not ev_name or not case:
        return
    try:
        ev = frappe.get_doc("Investigation Evidence", ev_name)
        content = "%s\n\n%s" % (ev.evidence_name, ev.notes or "")
        from frappe.utils.file_manager import save_file
        f = save_file("%s.txt" % ev.evidence_name, content.encode("utf-8"),
                      "Investigation Case", case, is_private=1)
        from thanatos_intel.reporting.case_file_delivery import deliver_case_file
        deliver_case_file(case, f.file_url, file_name=ev.evidence_name, doc_kind="Altro", self_mode=1)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_deliver_lookup_result")


def _run_lookup_bg(kind, value=None, investigation_case=None, name=None, surname=None, tax_code=None, self_mode=0):
    try:
        res = None
        if kind == "negativita":
            res = negativita(value, investigation_case, max_wait=90)
        elif kind == "patrimoniale":
            res = patrimoniale(name, surname, tax_code, investigation_case, max_wait=90)
        elif kind == "soci":
            # value = P.IVA azienda target
            res = soci_titolari(value, investigation_case)
        elif kind == "veicolo":
            # value = targa
            res = veicolo(value, investigation_case)
        elif kind == "iban":
            # value = IBAN
            res = verifica_iban(value, investigation_case)
        elif kind == "visura":
            # value = P.IVA (default: visura ordinaria)
            res = visura(value, tipo="ordinaria", investigation_case=investigation_case, max_wait=90)
        elif kind == "catasto":
            # value = CF/P.IVA soggetto (default: visura catastale per soggetto)
            res = catasto(value, tipo="visura_soggetto", investigation_case=investigation_case, max_wait=90)
        # addebito al cliente solo se eseguito senza errore
        if res is not None and not res.get("error") and investigation_case:
            client = frappe.db.get_value("Investigation Case", investigation_case, "client")
            _ref = "%s-%s-%s" % (investigation_case, kind, frappe.generate_hash(length=8))
            from thanatos_intel.osint.tool_catalog import tool_price, tool_base_price
            from thanatos_intel.billing.mmos_wallet import mmos_charge
            # Thanatos paga MMOS il base/ingrosso (wallet su cloud.onekeyco.com)
            mmos_charge(tool_base_price(investigation_case, kind), ref_name=_ref,
                        notes="openapi %s (caso %s)" % (kind, investigation_case))
            if client:
                from thanatos_intel.billing.credits import charge
                charge(client, tool_price(investigation_case, kind),
                       "%s — %s" % (kind, value or tax_code or ""), ref_dt="Investigation Case",
                       ref_name=_ref)
            if int(self_mode or 0):
                _deliver_lookup_result(investigation_case, res)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "openapi enqueue_lookup")
