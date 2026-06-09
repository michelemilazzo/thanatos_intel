"""Motore pipeline per casi Thanatos.

Ogni tipo di servizio ha una lista ordinata di step.
Lo stato corrente è calcolato dinamicamente dai documenti esistenti sul caso.
"""
import frappe
from frappe.utils import flt

# ---------------------------------------------------------------------------
# Definizioni pipeline per tipo
# ---------------------------------------------------------------------------

PIPELINES = {
    "DDD": [
        {
            "key": "kyb_kyc",
            "label": "Verifica identità (KYB/KYC)",
            "actor": "operator",
            "description": "Verifica documenti del richiedente prima di procedere.",
            "desk_url": lambda c: f"/app/kyc-check?client={c.get('client','')}" if c.get('client_type') == 'Individual' else f"/app/kyb-check?client={c.get('client','')}",
            "check": lambda c: _check_kyb_kyc(c),
        },
        {
            "key": "mandate",
            "label": "Mandato d'incarico",
            "actor": "operator",
            "description": "Genera il PDF del mandato e invialo al cliente per la firma.",
            "desk_url": lambda c: f"/app/agency-mandate?ddd_case={c['name']}",
            "check": lambda c: _check_mandate_created(c),
        },
        {
            "key": "mandate_signed",
            "label": "Firma mandato",
            "actor": "client",
            "description": "Il cliente firma il mandato tramite DocuSeal.",
            "portal_url": "/portal",
            "check": lambda c: _check_mandate_signed(c),
        },
        {
            "key": "proforma",
            "label": "Preventivo DDD",
            "actor": "operator",
            "description": "Emetti la proforma con l'importo del servizio.",
            "desk_url": lambda c: f"/app/diplomatic-proforma?ddd_case={c['name']}",
            "check": lambda c: _check_proforma(c),
        },
        {
            "key": "payment",
            "label": "Pagamento",
            "actor": "client",
            "description": "Il cliente salda la proforma.",
            "portal_url": "/portal/billing",
            "check": lambda c: _check_payment(c),
        },
        {
            "key": "passport_analysis",
            "label": "Analisi passaporto",
            "actor": "operator",
            "description": "Avvia l'analisi del documento di viaggio.",
            "desk_url": lambda c: f"/app/passport-analysis?ddd_case={c['name']}",
            "check": lambda c: _check_passport_analysis(c),
        },
        {
            "key": "sanctions",
            "label": "Verifica sanzioni",
            "actor": "operator",
            "description": "Esegui lo screening sanzioni sul soggetto.",
            "desk_url": lambda c: f"/app/sanctions-screening?ddd_case={c['name']}",
            "check": lambda c: _check_sanctions(c),
        },
        {
            "key": "report",
            "label": "Report finale",
            "actor": "operator",
            "description": "Genera il report di eligibilità e caricalo.",
            "desk_url": lambda c: f"/app/investigation-report?investigation_case={c['name']}",
            "check": lambda c: _check_report(c),
        },
        {
            "key": "completed",
            "label": "Pratica chiusa",
            "actor": "operator",
            "description": "Chiudi il caso e archivia i documenti.",
            "desk_url": lambda c: f"/app/diplomatic-eligibility-case/{c['name']}",
            "check": lambda c: _check_completed(c),
        },
    ],
    "Investigation": [
        {
            "key": "mandate",
            "label": "Mandato d'incarico",
            "actor": "operator",
            "description": "Genera e invia il mandato d'incarico.",
            "desk_url": lambda c: f"/app/agency-mandate?investigation_case={c['name']}",
            "check": lambda c: _check_mandate_created(c),
        },
        {
            "key": "mandate_signed",
            "label": "Firma mandato",
            "actor": "client",
            "description": "Il cliente firma il mandato.",
            "portal_url": "/portal",
            "check": lambda c: _check_mandate_signed(c),
        },
        {
            "key": "proforma",
            "label": "Preventivo",
            "actor": "operator",
            "description": "Emetti il preventivo.",
            "desk_url": lambda c: f"/app/quotation",
            "check": lambda c: _check_invoice_or_quotation(c),
        },
        {
            "key": "payment",
            "label": "Pagamento",
            "actor": "client",
            "description": "Il cliente effettua il pagamento.",
            "portal_url": "/portal/billing",
            "check": lambda c: _check_payment(c),
        },
        {
            "key": "evidence",
            "label": "Raccolta evidenze",
            "actor": "operator",
            "description": "Carica le evidenze raccolte (SHA-256).",
            "desk_url": lambda c: f"/app/investigation-evidence?investigation_case={c['name']}",
            "check": lambda c: _check_evidence(c),
        },
        {
            "key": "report",
            "label": "Report finale",
            "actor": "operator",
            "description": "Genera e consegna il report investigativo.",
            "desk_url": lambda c: f"/app/investigation-report?investigation_case={c['name']}",
            "check": lambda c: _check_report(c),
        },
        {
            "key": "completed",
            "label": "Pratica chiusa",
            "actor": "operator",
            "description": "Chiudi il caso.",
            "desk_url": lambda c: f"/app/investigation-case/{c['name']}",
            "check": lambda c: _check_completed(c),
        },
    ],
    "OSINT": [
        {
            "key": "mandate",
            "label": "Mandato d'incarico",
            "actor": "operator",
            "description": "Genera il mandato.",
            "desk_url": lambda c: f"/app/agency-mandate",
            "check": lambda c: _check_mandate_created(c),
        },
        {
            "key": "osint_job",
            "label": "OSINT / Lookup",
            "actor": "operator",
            "description": "Avvia la ricerca OSINT.",
            "desk_url": lambda c: f"/app/osint-job?investigation_case={c['name']}",
            "check": lambda c: _check_osint(c),
        },
        {
            "key": "report",
            "label": "Report",
            "actor": "operator",
            "description": "Genera il report OSINT.",
            "desk_url": lambda c: f"/app/investigation-report?investigation_case={c['name']}",
            "check": lambda c: _check_report(c),
        },
        {
            "key": "completed",
            "label": "Chiuso",
            "actor": "operator",
            "description": "Chiudi.",
            "check": lambda c: _check_completed(c),
        },
    ],
    "Antifrode": [
        {
            "key": "mandate",
            "label": "Mandato d'incarico",
            "actor": "operator",
            "description": "Genera il mandato.",
            "desk_url": lambda c: f"/app/agency-mandate",
            "check": lambda c: _check_mandate_created(c),
        },
        {
            "key": "fraud_analysis",
            "label": "Analisi antifrode",
            "actor": "operator",
            "description": "Avvia l'analisi delle transazioni/soggetti.",
            "desk_url": lambda c: f"/app/fraud-alert?investigation_case={c['name']}",
            "check": lambda c: _check_fraud_alert(c),
        },
        {
            "key": "blacklist",
            "label": "Verifica blacklist",
            "actor": "operator",
            "description": "Controlla il soggetto in blacklist.",
            "desk_url": lambda c: f"/app/blacklist-entry",
            "check": lambda c: _check_blacklist(c),
        },
        {
            "key": "report",
            "label": "Report",
            "actor": "operator",
            "description": "Genera il report.",
            "desk_url": lambda c: f"/app/investigation-report?investigation_case={c['name']}",
            "check": lambda c: _check_report(c),
        },
        {
            "key": "completed",
            "label": "Chiuso",
            "actor": "operator",
            "description": "Chiudi.",
            "check": lambda c: _check_completed(c),
        },
    ],
}

# Alias comuni
PIPELINES["Due Diligence"] = PIPELINES["DDD"]
PIPELINES["Cyber"] = PIPELINES["OSINT"]
PIPELINES["Fraud"] = PIPELINES["Antifrode"]
PIPELINES["Corporate"] = PIPELINES["Investigation"]
PIPELINES["Generic"] = PIPELINES["Investigation"]


# ---------------------------------------------------------------------------
# Check functions — ognuna verifica se lo step è completato
# ---------------------------------------------------------------------------

def _check_kyb_kyc(case):
    client = case.get("client")
    if not client:
        return False
    doc = frappe.db.get_value("Investigation Client", client,
                               ["kyc_status", "kyb_status", "client_type"], as_dict=1)
    if not doc:
        return False
    if doc.client_type == "Individual":
        return doc.kyc_status in ("Verified", "Approved")
    return doc.kyb_status in ("Verified", "Approved")


def _check_mandate_created(case):
    name = case.get("name")
    return bool(frappe.db.exists("Agency Mandate",
                                  [["ddd_case", "=", name], ["status", "!=", ""]]))


def _check_mandate_signed(case):
    name = case.get("name")
    return bool(frappe.db.exists("Agency Mandate",
                                  [["ddd_case", "=", name], ["status", "in", ("Signed", "Active", "Completed")]]))


def _check_proforma(case):
    name = case.get("name")
    return bool(frappe.db.exists("Diplomatic Proforma", {"ddd_case": name}))


def _check_invoice_or_quotation(case):
    name = case.get("name")
    return bool(frappe.db.exists("Quotation", {"investigation_case": name})) or \
           bool(frappe.db.exists("Sales Invoice", {"investigation_case": name}))


def _check_payment(case):
    name = case.get("name")
    pf = frappe.db.get_value("Diplomatic Proforma", {"ddd_case": name}, "payment_status")
    if pf in ("Paid", "Partially Paid"):
        return True
    inv = frappe.db.get_all("Sales Invoice",
                             filters={"investigation_case": name, "outstanding_amount": ["<=", 0]},
                             limit=1)
    return bool(inv)


def _check_passport_analysis(case):
    return bool(frappe.db.exists("Passport Analysis", {"ddd_case": case.get("name")}))


def _check_sanctions(case):
    return bool(frappe.db.exists("Sanctions Screening", {"ddd_case": case.get("name")}))


def _check_report(case):
    return bool(frappe.db.exists("Investigation Report", {"investigation_case": case.get("name")}))


def _check_evidence(case):
    return bool(frappe.db.exists("Investigation Evidence", {"investigation_case": case.get("name")}))


def _check_osint(case):
    return bool(frappe.db.exists("OSINT Job", {"investigation_case": case.get("name")}))


def _check_fraud_alert(case):
    return bool(frappe.db.exists("Fraud Alert", {"investigation_case": case.get("name")}))


def _check_blacklist(case):
    return True  # skip — blacklist è opzionale


def _check_completed(case):
    return case.get("case_status") in ("Completed", "Closed", "Archived")


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------

def get_pipeline(case_doc_or_dict) -> list[dict]:
    """Restituisce la lista step con status per un caso.

    Ogni step:
      key, label, actor, description, status (done|current|pending|blocked),
      desk_url, portal_url
    """
    if hasattr(case_doc_or_dict, "as_dict"):
        case = case_doc_or_dict.as_dict()
    else:
        case = case_doc_or_dict

    case_type = (case.get("case_type") or "Investigation").strip()
    # Se case_type è un Link a Case Type, leggi il pipeline_key
    pipeline_key = case.get("pipeline_key") or case_type
    steps = PIPELINES.get(pipeline_key) or PIPELINES.get(case_type) or PIPELINES.get("Investigation")

    result = []
    found_current = False
    for step in steps:
        check_fn = step.get("check")
        done = bool(check_fn(case)) if check_fn else False

        if done:
            status = "done"
        elif not found_current:
            status = "current"
            found_current = True
        else:
            status = "pending"

        desk_url_fn = step.get("desk_url")
        entry = {
            "key": step["key"],
            "label": step["label"],
            "actor": step.get("actor", "operator"),
            "description": step.get("description", ""),
            "status": status,
            "desk_url": desk_url_fn(case) if desk_url_fn and not done else "",
            "portal_url": step.get("portal_url", ""),
        }
        result.append(entry)
    return result


@frappe.whitelist()
def get_case_pipeline(case_name: str) -> list:
    case = frappe.db.get_value(
        "Investigation Case", case_name,
        ["name", "case_type", "status", "client"], as_dict=1,
    )
    if not case:
        return []
    case["case_status"] = case.get("status", "")
    # Risolvi pipeline_key dal doctype Case Type
    if case.get("case_type"):
        pk = frappe.db.get_value("Case Type", case["case_type"], "pipeline_key")
        case["pipeline_key"] = pk or ""
    # aggiungi client_type
    if case.get("client"):
        ct = frappe.db.get_value("Investigation Client", case["client"], "client_type")
        case["client_type"] = ct
    return get_pipeline(case)


@frappe.whitelist()
def get_ddd_pipeline(ddd_case_name: str) -> list:
    case = frappe.db.get_value(
        "Diplomatic Eligibility Case", ddd_case_name,
        ["name", "status", "client"], as_dict=1,
    )
    if not case:
        return []
    case["case_type"] = "DDD"
    case["case_status"] = case.get("status", "")
    case["pipeline_key"] = "DDD"
    if case.get("client"):
        ct = frappe.db.get_value("Investigation Client", case["client"], "client_type")
        case["client_type"] = ct
    return get_pipeline(case)
