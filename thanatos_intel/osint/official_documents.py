"""Download documenti ufficiali openapi → reperto PDF nel fascicolo del caso.

Visure camerali (società capitale/persone, ditta individuale, ordinaria/storica),
bilancio ottico, certificati + catasto. Flusso async REALE:
  1) POST /{tipo} {cf_piva_id}  → {id, stato_richiesta}
  2) poll GET /{tipo}/{id}      → stato_richiesta = "Dati disponibili"/"Evasa"
  3) GET /{tipo}/{id}/allegati  → {file: base64 ZIP} → estrai PDF → Investigation Evidence

I documenti sono SOLO produzione (PDF reali a pagamento): usa il token prod
`registro_imprese_token_prod`. La richiesta è lenta → eseguita in background (enqueue).
"""
import base64
import io
import time
import zipfile
import frappe
from frappe.utils import now_datetime

_HOSTS = {"visure": "visurecamerali.openapi.it", "catasto": "catasto.openapi.it"}

# tipo logico → (servizio, path). Visure camerali ufficiali.
TIPI = {
    "ordinaria_capitale":   ("visure", "ordinaria-societa-capitale"),
    "storica_capitale":     ("visure", "storica-societa-capitale"),
    "ordinaria_persone":    ("visure", "ordinaria-societa-persone"),
    "storica_persone":      ("visure", "storica-societa-persone"),
    "ordinaria_individuale": ("visure", "ordinaria-impresa-individuale"),
    "storica_individuale":  ("visure", "storica-impresa-individuale"),
    "bilancio":             ("visure", "bilancio-ottico"),
    "certificato":          ("visure", "certificato-iscrizione"),
    "certificato_vigenza":  ("visure", "certificato-iscrizione-vigenza"),
}

_DE_BY_TIPO = {
    "ordinaria_capitale":    "663df75d19a52195e23e315c",
    "ordinaria_persone":     "6671a5549e6f0e447bc2659d",
    "ordinaria_individuale": "6671a5719e6f0e447bc2659e",
    "storica_capitale":      "6671a5a29e6f0e447bc2659f",
    "storica_persone":       "6671a5bf9e6f0e447bc265a0",
    "storica_individuale":   "6671a5d69e6f0e447bc265a1",
    "bilancio":              "667443c29e6f0e447bc265aa",
    "certificato":           "689c99942d09c0a9bcb946e8",
    "certificato_vigenza":   "689c99942d09c0a9bcb946e8",
}

_READY = {"dati disponibili", "evasa", "visura evasa", "completata", "completato"}


def _token():
    # documenti = produzione (PDF reali); fallback al token unico se prod non c'è
    return (frappe.conf.get("registro_imprese_token_prod")
            or frappe.conf.get("registro_imprese_token"))


def _hdr():
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _url(service, path):
    return f"https://{_HOSTS[service]}/{path}"


def _is_self_purchase(case):
    """Self mode = la richiesta arriva dal cliente stesso (utente portale) oppure
    il cliente ha gia pagato verifiche per questo caso (acquisto self-serve)."""
    cl = frappe.db.get_value("Investigation Case", case, "client")
    if not cl:
        return 0
    pu = frappe.db.get_value("Investigation Client", cl, "platform_user")
    if pu and pu == frappe.session.user:
        return 1
    if frappe.db.exists("AI Usage Log", {"reference": case, "model": "openapi:verifiche"}):
        return 1
    return 0


@frappe.whitelist()
def richiedi_documento(case, tipo, cf_piva, self_mode=None):
    """Visura/documento camerale ufficiale. Instradato su DocuEngine
    (docuengine.openapi.com): il vecchio host visurecamerali.openapi.it non
    e' piu' sottoscritto sul token e rispondeva 401 \"Wrong Token\"."""
    doc_id = _DE_BY_TIPO.get(tipo)
    if not doc_id:
        return {"error": f"tipo non valido: {tipo}", "tipi": list(_DE_BY_TIPO)}
    digits = "".join(c for c in (cf_piva or "") if c.isdigit())
    return richiedi_docuengine(case, doc_id, valori={"taxCode": digits}, self_mode=self_mode)


def _scarica_bg(case, service, path, req_id, tipo, cf_piva, self_mode=0, max_wait=480):
    """Poll finché evasa, scarica gli allegati (ZIP base64), salva i PDF come reperti."""
    import requests
    deadline = time.time() + max_wait
    stato = None
    while time.time() < deadline:
        time.sleep(8)
        g = requests.get(f"{_url(service, path)}/{req_id}", headers=_hdr(), timeout=40)
        d = (g.json() or {}).get("data") or {}
        if isinstance(d, list):
            d = d[0] if d else {}
        stato = (d.get("stato_richiesta") or d.get("state") or "").lower()
        if stato in _READY and (d.get("allegati") or d.get("file")):
            break
        if stato in ("errore", "error", "rifiutata", "failed"):
            _log(case, tipo, cf_piva, f"richiesta {stato}")
            return
    # scarica gli allegati (file = ZIP base64)
    a = requests.get(f"{_url(service, path)}/{req_id}/allegati", headers=_hdr(), timeout=60)
    ad = (a.json() or {}).get("data") or {}
    if isinstance(ad, list):
        ad = ad[0] if ad else {}
    b64 = ad.get("file")
    if not b64:
        _log(case, tipo, cf_piva, f"allegati non pronti (stato {stato})")
        return
    raw = base64.b64decode(b64)
    pdfs = []
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        for nm in z.namelist():
            pdfs.append((nm, z.read(nm)))
    except Exception:
        pdfs.append((f"{tipo}_{cf_piva}.pdf", raw))  # non-zip: PDF diretto
    for nm, content in pdfs:
        _salva_reperto(case, tipo, cf_piva, nm, content, self_mode)
    # addebito: documento ufficiale prodotto (cliente=rivendita, MMOS=ingrosso)
    try:
        client = frappe.db.get_value("Investigation Case", case, "client")
        if client and pdfs:
            from thanatos_intel.osint.tool_catalog import tool_price, tool_base_price
            from thanatos_intel.billing.credits import charge
            from thanatos_intel.billing.mmos_wallet import mmos_charge
            _ref = "%s-doc-%s-%s" % (case, tipo, frappe.generate_hash(length=8))
            charge(client, tool_price(case, "visura"), "documento ufficiale %s" % tipo,
                   ref_dt="Investigation Case", ref_name=_ref)
            mmos_charge(tool_base_price(case, "visura"), ref_name=_ref,
                        notes="documento ufficiale %s (caso %s)" % (tipo, case))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "official_documents charge")
    frappe.db.commit()


def _salva_reperto(case, tipo, cf_piva, filename, content, self_mode=0):
    """Crea Investigation Evidence con il PDF allegato sul caso."""
    label = f"{TIPI.get(tipo, (None, tipo))[1]} — {cf_piva}"
    ev = frappe.get_doc({
        "doctype": "Investigation Evidence", "investigation_case": case,
        "evidence_name": f"Documento ufficiale — {label}"[:140],
        "evidence_type": "Document", "source": "openapi documento ufficiale",
        "acquisition_date": now_datetime(), "custody_status": "Received",
        "notes": f"Documento ufficiale {tipo} per {cf_piva} (openapi)."})
    ev.flags.ignore_mandatory = True
    ev.insert(ignore_permissions=True)
    fname = filename if filename.lower().endswith(".pdf") else f"{filename}.pdf"
    f = frappe.get_doc({
        "doctype": "File", "file_name": fname, "is_private": 1,
        "attached_to_doctype": "Investigation Evidence", "attached_to_name": ev.name,
        "content": content})
    f.insert(ignore_permissions=True)
    try:
        ev.db_set("attached_file", f.file_url)
    except Exception:
        pass
    # consegna file originale: cartella Drive del caso + (self mode) portale cliente + email
    try:
        from thanatos_intel.reporting.case_file_delivery import deliver_case_file
        deliver_case_file(case, f.file_url, file_name=fname, doc_kind="Altro", self_mode=self_mode)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "official_documents deliver")


def _log(case, tipo, cf_piva, msg):
    try:
        c = frappe.get_doc("Investigation Case", case)
        c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "Report",
                 "description": f"📄 Documento ufficiale {tipo} {cf_piva}: {msg}"[:500],
                 "operator": frappe.session.user})
        c.flags.ignore_mandatory = True
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "official_documents log")


@frappe.whitelist()
def tipi_documenti():
    """Elenco tipi documento ufficiale disponibili (per la UI)."""
    return [{"id": k, "label": v[1]} for k, v in TIPI.items()]


# ── DocuEngine (docuengine.openapi.com) — 53 documenti on-demand ─────────────
# Camerali (visure/bilanci/fascicoli/protesti/DURC), Catastali (mappa/planimetrie),
# Patronato (certificati anagrafici: residenza/stato famiglia/matrimonio, targa PRA).
# Flusso: GET /documents (catalogo+requestStructure) → POST /requests
# {documentId, search:{field0..N nell'ordine del requestStructure}} → poll
# GET /requests/{id} (WAIT→DONE, patronato ~2gg) → GET /requests/{id}/documents
# → downloadUrl (GCS, scade). GOTCHA: i campi vanno SEMPRE in "search" anche con
# hasSearch=false; date ISO YYYY-MM-DD; certificati esente-bollo richiedono
# exemptionReason+exemptionDocument (la versione "Con Marca Da Bollo" no).

_DE = "https://docuengine.openapi.com"
_DE_ERROR = {"ERROR", "FAILED", "REJECTED", "KO", "CANCELED", "CANCELLED"}
_DE_PENDING_KEY = "docuengine_pending"


def _de_get(path):
    import requests
    r = requests.get(_DE + path, headers=_hdr(), timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"message": (r.text or "")[:300]}


@frappe.whitelist()
def docuengine_catalog(case=None, force=0):
    """Catalogo DocuEngine (cache 24h): documenti + campi + prezzi (costo e cliente)."""
    docs = None if frappe.utils.cint(force) else frappe.cache().get_value("docuengine_catalog")
    if not docs:
        st, body = _de_get("/documents")
        if st != 200:
            return {"error": f"HTTP {st}: {body.get('message') or body}"}
        docs = []
        for x in body.get("data") or []:
            fields = (x.get("requestStructure") or {}).get("fields") or {}
            ordered = []
            for k in sorted(fields, key=lambda s: int(s[5:])):
                f = fields[k]
                ordered.append({"key": k, "name": f.get("name"), "label": f.get("nameIT") or f.get("name"),
                                "type": f.get("type"), "required": 1 if f.get("required") else 0,
                                "options": f.get("options"), "help": f.get("help")})
            opts = [{"name": o.get("name"), "price": float(o.get("price") or 0)}
                    for o in (x.get("options") or [])]
            docs.append({"id": x.get("id"), "name": x.get("name"), "category": x.get("category"),
                         "costo": float(x.get("totalPrice") or 0), "options": opts, "fields": ordered})
        frappe.cache().set_value("docuengine_catalog", docs, expires_in_sec=86400)
    # prezzo cliente = costo × markup del cliente del caso (marca da bollo pass-through)
    from thanatos_intel.billing.openapi_billing import _markup, prezzo_cliente
    client = frappe.db.get_value("Investigation Case", case, "client") if case else None
    mk = _markup(client)
    out = []
    for d in docs:
        opts = [dict(o, prezzo=round(o["price"] * mk, 2)) for o in d.get("options") or []]
        out.append(dict(d, options=opts,
                        prezzo=prezzo_cliente("de_" + d["id"], d["name"], d["costo"], mk)))
    return {"markup": mk, "documenti": out}


def _de_options_price(doc, options, markup=1.0):
    """Somma costo e prezzo cliente delle opzioni selezionate (urgenza/assistenza)."""
    sel = set(options or [])
    by = {o["name"]: o for o in doc.get("options") or []}
    cost = sum(by[n]["price"] for n in sel if n in by)
    return round(cost, 2), round(cost * markup, 2)


def _de_doc(document_id):
    for d in (docuengine_catalog().get("documenti") or []):
        if d["id"] == document_id:
            return d
    return None


# ── Esenzione bollo certificati anagrafici (residenza/AIRE/stato famiglia/storico) ──
# La variante esente richiede exemptionReason (lista chiusa openapi) + exemptionDocument
# (file di prova); quella "Con Marca Da Bollo" no. MAI dichiarare un'esenzione senza
# documento reale (evasione imposta di bollo): il titolo vive nel vault del cliente.
_BOLLO_SUFFIX = " Con Marca Da Bollo"
_ESENZIONE_VAULT = [("Nomina CTU", "CTU"), ("Tesserino Avvocato", None)]


@frappe.whitelist()
def esenzione_bollo(case):
    """Titolo di esenzione bollo del caso: Nomina CTU → CTU; Tesserino Avvocato →
    PROCESSUALE (DIVORZIO se il caso è Family). Richiede un documento reale nel vault."""
    client = frappe.db.get_value("Investigation Case", case, "client")
    if not client:
        return {"reason": None, "note": "Caso senza cliente: usare la variante Con Marca Da Bollo."}
    case_type = frappe.db.get_value("Investigation Case", case, "case_type") or ""

    def _vault(kind):
        it = frappe.get_all("Client Vault Item",
                            filters={"client": client, "doc_kind": kind,
                                     "status": ["in", ["Valido", "In verifica"]]},
                            fields=["name", "file", "title", "status"],
                            order_by="modified desc", limit=1)
        return it[0] if it and it[0].file else None

    delega = _vault("Delega Mandato")
    for kind, reason in _ESENZIONE_VAULT:
        it = _vault(kind)
        if it:
            r = reason or ("DIVORZIO" if case_type == "Family" else "PROCESSUALE")
            note = "Esenzione %s — %s dal vault del cliente (%s)." % (r, it.title or kind, it.status)
            if delega:
                note += " Delega mandato allegata (%s)." % (delega.title or "Delega Mandato")
            return {"reason": r, "document": it.file, "title": it.title or kind,
                    "vault_item": it.name, "vault_status": it.status,
                    "delegation": (delega.file if delega else None),
                    "delegation_title": (delega.title if delega else None),
                    "note": note}
    return {"reason": None,
            "note": "Nessun titolo di esenzione (Tesserino Avvocato / Nomina CTU) nel vault del cliente: si usa la variante Con Marca Da Bollo."}


@frappe.whitelist()
def scegli_variante_certificato(case, document_id):
    """Per i certificati anagrafici con doppia variante sceglie ESENTE vs CON MARCA
    DA BOLLO in base al mandato del caso e precompila i campi di esenzione."""
    cat = docuengine_catalog(case=case)
    docs = cat.get("documenti") or []
    d = next((x for x in docs if x["id"] == document_id), None)
    if not d:
        return {"error": f"documento non trovato: {document_id}"}
    by_name = {x["name"]: x for x in docs}
    base = d["name"].replace(_BOLLO_SUFFIX, "")
    esente, bollo = by_name.get(base), by_name.get(base + _BOLLO_SUFFIX)
    if not (esente and bollo) or not any(f["name"] == "exemptionReason" for f in esente["fields"]):
        return {"document": d}
    ex = esenzione_bollo(case)
    if ex.get("reason"):
        prefill = {"exemptionReason": ex["reason"], "exemptionDocument": ex["document"]}
        if ex.get("delegation"):
            for f in esente["fields"]:
                if "delegation" in (f["name"] or "").lower() or "delega" in (f["name"] or "").lower():
                    prefill[f["name"]] = ex["delegation"]
        return {"document": esente, "esenzione": ex, "prefill": prefill,
                "note": "%s Variante ESENTE € %.2f (con bollo sarebbe € %.2f)." % (ex["note"], esente["prezzo"], bollo["prezzo"])}
    return {"document": bollo, "esenzione": ex, "prefill": {},
            "note": "%s Variante CON MARCA DA BOLLO € %.2f." % (ex["note"], bollo["prezzo"])}


def _file_b64(value):
    """Campo DocuEngine type=file: da file_url Frappe (o base64 già pronto) a base64.
    Il documento DEVE esistere davvero — niente esenzioni dichiarate senza prova."""
    v = (value or "").strip()
    if v.startswith("/files/") or v.startswith("/private/files/"):
        fname = frappe.db.get_value("File", {"file_url": v}, "name")
        if not fname:
            frappe.throw(f"file non trovato sul sito: {v}")
        content = frappe.get_doc("File", fname).get_content()
        if isinstance(content, str):
            content = content.encode()
        return base64.b64encode(content).decode()
    if v.startswith("http"):
        frappe.throw("il documento di esenzione deve essere un file caricato sul sito (/files/… o /private/files/…)")
    return v  # già base64


@frappe.whitelist()
def richiedi_docuengine(case, document_id, valori=None, options=None, self_mode=None):
    """Ordina un documento DocuEngine. valori = JSON {nomeCampo: valore};
    viene rimappato in search:{field0..N} nell'ordine del requestStructure.
    options = JSON lista nomi opzione a pagamento (urgenza / assistenza_dedicata)."""
    import json as _json
    doc = _de_doc(document_id)
    if not doc:
        return {"error": f"documento non trovato: {document_id}"}
    if isinstance(valori, str):
        valori = _json.loads(valori or "{}")
    valori = valori or {}
    if isinstance(options, str):
        options = _json.loads(options or "[]")
    valid_opts = {o["name"] for o in doc.get("options") or []}
    options = [o for o in (options or []) if o in valid_opts]
    search, missing = {}, []
    try:
        for f in doc["fields"]:
            v = valori.get(f["name"])
            if v in (None, ""):
                if f["required"]:
                    missing.append(f["label"] or f["name"])
                continue
            search[f["key"]] = _file_b64(v) if f["type"] == "file" else v
    except frappe.ValidationError as e:
        return {"error": str(e)}
    if missing:
        hint = ""
        if any(m in ("motivo esenzione", "documento esenzione") for m in missing):
            hint = " — senza titolo di esenzione usare la variante Con Marca Da Bollo"
        return {"error": "campi obbligatori mancanti: " + ", ".join(missing) + hint}
    if valori.get("exemptionReason") and not valori.get("exemptionDocument"):
        return {"error": "esenzione bollo dichiarata senza documento di prova: vietato (imposta di bollo)"}
    if self_mode is None:
        self_mode = _is_self_purchase(case)
    client = frappe.db.get_value("Investigation Case", case, "client")
    if client:
        from thanatos_intel.billing.openapi_billing import _markup, _mmos_markup, prezzo_cliente
        from thanatos_intel.billing.credits import ensure_credit
        from thanatos_intel.billing.mmos_wallet import mmos_ensure
        _oc_cli, _op_cli = _de_options_price(doc, options, _markup(client))
        _oc_mm, _op_mm = _de_options_price(doc, options, _mmos_markup())
        ensure_credit(client, prezzo_cliente(document_id, doc["name"], doc["costo"], _markup(client)) + _op_cli,
                      f"DocuEngine {doc['name']}")
        mmos_ensure(prezzo_cliente(document_id, doc["name"], doc["costo"], _mmos_markup()) + _op_mm,
                    label=f"DocuEngine {doc['name']}")
    import requests
    payload = {"documentId": document_id, "search": search}
    if options:
        payload["selectedOptions"] = options
    r = requests.post(_DE + "/requests", headers=_hdr(), json=payload, timeout=60)
    if r.status_code not in (200, 201):
        try:
            msg = (r.json() or {}).get("message") or r.text
        except Exception:
            msg = r.text
        return {"error": f"HTTP {r.status_code}: {str(msg)[:300]}"}
    data = (r.json() or {}).get("data") or {}
    req_id = data.get("id")
    if not req_id:
        return {"error": "nessun id richiesta", "raw": str(data)[:200]}
    target = valori.get("taxCode") or valori.get("plate") or " ".join(
        str(valori.get(k) or "") for k in ("name", "surname")).strip() or "-"
    frappe.enqueue("thanatos_intel.osint.official_documents._docuengine_bg",
                   queue="long", timeout=700, case=case, req_id=req_id,
                   document_id=document_id, target=target, self_mode=int(self_mode or 0),
                   options=options)
    return {"ok": True, "id": req_id, "documento": doc["name"],
            "message": "Richiesta inviata; il documento arriverà nei reperti del caso "
                       "(certificati anagrafici richiedono ~2 giorni lavorativi, ritiro automatico)."}


def _docuengine_bg(case, req_id, document_id, target, self_mode=0, max_wait=480, options=None):
    """Poll breve in background; se non pronta, passa al ritiro orario (scheduler)."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(15)
        st, body = _de_get(f"/requests/{req_id}")
        d = body.get("data") or {}
        if isinstance(d, list):
            d = d[0] if d else {}
        state = (d.get("state") or "").upper()
        if state == "DONE":
            _docuengine_scarica(case, req_id, document_id, target, self_mode, options)
            return
        if state in _DE_ERROR:
            doc = _de_doc(document_id) or {"name": document_id}
            _log(case, doc["name"], target, f"richiesta {state}")
            return
    _de_pending_add({"case": case, "req_id": req_id, "document_id": document_id,
                     "target": target, "self_mode": int(self_mode or 0), "options": options or []})
    doc = _de_doc(document_id) or {"name": document_id}
    _log(case, doc["name"], target,
         "in lavorazione (ritiro automatico orario; certificati anagrafici ~2 giorni)")


def _docuengine_scarica(case, req_id, document_id, target, self_mode=0, options=None):
    """Scarica i PDF pronti (downloadUrl) e li salva come reperti + addebita."""
    import requests
    doc = _de_doc(document_id) or {"name": document_id, "costo": 0.0}
    st, body = _de_get(f"/requests/{req_id}/documents")
    files = body.get("data") if isinstance(body, dict) else body
    if isinstance(files, dict):
        files = [files]
    saved = 0
    for i, f in enumerate(files or []):
        url = f.get("downloadUrl")
        if not url:
            continue
        r = requests.get(url, timeout=120)
        if r.status_code != 200:
            continue
        fname = f.get("fileName") or f"{frappe.scrub(doc['name'])}_{i}.pdf"
        _salva_reperto(case, doc["name"], target, fname, r.content, self_mode)
        saved += 1
    if not saved:
        _log(case, doc["name"], target, "DONE ma nessun file scaricabile")
        return
    try:
        client = frappe.db.get_value("Investigation Case", case, "client")
        if client:
            from thanatos_intel.billing.openapi_billing import _markup, _mmos_markup, prezzo_cliente
            from thanatos_intel.billing.credits import charge
            from thanatos_intel.billing.mmos_wallet import mmos_charge
            _ref = "%s-de-%s" % (case, req_id[-8:])
            _, _op_cli = _de_options_price(doc, options, _markup(client))
            _, _op_mm = _de_options_price(doc, options, _mmos_markup())
            charge(client, prezzo_cliente(document_id, doc["name"], doc.get("costo") or 0, _markup(client)) + _op_cli,
                   "DocuEngine %s" % doc["name"], ref_dt="Investigation Case", ref_name=_ref)
            mmos_charge(prezzo_cliente(document_id, doc["name"], doc.get("costo") or 0, _mmos_markup()) + _op_mm,
                        ref_name=_ref, notes="DocuEngine %s (caso %s)" % (doc["name"], case))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "docuengine charge")
    frappe.db.commit()


def _de_pending_load():
    import json as _json
    try:
        return _json.loads(frappe.db.get_default(_DE_PENDING_KEY) or "[]")
    except Exception:
        return []


def _de_pending_save(items):
    import json as _json
    frappe.db.set_default(_DE_PENDING_KEY, _json.dumps(items))
    frappe.db.commit()


def _de_pending_add(item):
    items = _de_pending_load()
    if not any(x.get("req_id") == item["req_id"] for x in items):
        items.append(item)
        _de_pending_save(items)


def docuengine_poll_pending():
    """Scheduler orario: ritira le richieste DocuEngine lente (patronato ~2gg)."""
    items = _de_pending_load()
    if not items:
        return
    still = []
    for it in items:
        try:
            st, body = _de_get(f"/requests/{it['req_id']}")
            d = body.get("data") or {}
            if isinstance(d, list):
                d = d[0] if d else {}
            state = (d.get("state") or "").upper()
            if state == "DONE":
                _docuengine_scarica(it["case"], it["req_id"], it["document_id"],
                                    it.get("target") or "-", it.get("self_mode") or 0,
                                    it.get("options") or [])
            elif state in _DE_ERROR:
                doc = _de_doc(it["document_id"]) or {"name": it["document_id"]}
                _log(it["case"], doc["name"], it.get("target") or "-", f"richiesta {state}")
            else:
                still.append(it)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "docuengine poll")
            still.append(it)
    if len(still) != len(items):
        _de_pending_save(still)


# ── Ordini DocuEngine "a pagamento ricevuto" (preventivo Stripe → auto-esecuzione) ──
# Il preventivo salva i valori dell'ordine in un DefaultValue keyed by uuid e mette
# l'uuid nei metadata del checkout; al webhook di pagamento settle() li esegue.
_DE_ORDER_KEY = "docuengine_order:"


def de_order_stage(case, document_id, valori, options=None):
    """Salva un ordine DocuEngine da eseguire al pagamento; ritorna l'order_id."""
    import json as _json
    oid = frappe.generate_hash(length=16)
    frappe.db.set_default(_DE_ORDER_KEY + oid, _json.dumps({
        "case": case, "document_id": document_id, "valori": valori or {},
        "options": options or []}))
    return oid


@frappe.whitelist()
def de_order_run(order_id, self_mode=1):
    """Esegue un ordine DocuEngine staged (chiamato dal webhook di pagamento)."""
    import json as _json
    raw = frappe.db.get_default(_DE_ORDER_KEY + order_id)
    if not raw:
        return {"error": "ordine non trovato o già eseguito: " + order_id}
    o = _json.loads(raw)
    frappe.db.set_default(_DE_ORDER_KEY + order_id, "")  # consuma (idempotente)
    res = richiedi_docuengine(o["case"], o["document_id"], valori=o.get("valori") or {},
                              options=o.get("options") or [], self_mode=int(self_mode or 0))
    if res.get("ok"):
        _log(o["case"], (_de_doc(o["document_id"]) or {}).get("name") or o["document_id"],
             (o.get("valori") or {}).get("taxCode") or "-", "ordine eseguito a pagamento ricevuto")
    return res
