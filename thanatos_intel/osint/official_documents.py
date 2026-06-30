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
    """Avvia la richiesta del documento ufficiale e la elabora in background."""
    if tipo not in TIPI:
        return {"error": f"tipo non valido: {tipo}", "tipi": list(TIPI)}
    digits = "".join(c for c in (cf_piva or "") if c.isdigit())
    if self_mode is None:
        self_mode = _is_self_purchase(case)
    # pre-pagamento: documenti ufficiali sono a pagamento → blocca se credito insufficiente
    client = frappe.db.get_value("Investigation Case", case, "client")
    if client:
        from thanatos_intel.osint.tool_catalog import tool_price, tool_base_price
        from thanatos_intel.billing.credits import ensure_credit
        from thanatos_intel.billing.mmos_wallet import mmos_ensure
        ensure_credit(client, tool_price(case, "visura"), "documento ufficiale")
        mmos_ensure(tool_base_price(case, "visura"), label="documento ufficiale")
    service, path = TIPI[tipo]
    import requests
    r = requests.post(_url(service, path), headers=_hdr(),
                      json={"cf_piva_id": digits}, timeout=40)
    if r.status_code not in (200, 201):
        return {"error": f"HTTP {r.status_code}: {(r.text or '')[:160]}"}
    data = (r.json() or {}).get("data") or {}
    req_id = data.get("id")
    if not req_id:
        return {"error": "nessun id richiesta", "raw": str(data)[:200]}
    frappe.enqueue("thanatos_intel.osint.official_documents._scarica_bg",
                   queue="long", timeout=600, case=case, service=service,
                   path=path, req_id=req_id, tipo=tipo, cf_piva=digits,
                   self_mode=int(self_mode or 0))
    return {"ok": True, "id": req_id, "tipo": tipo,
            "message": "Richiesta avviata; il documento arriverà nei reperti del caso tra qualche minuto."}


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
