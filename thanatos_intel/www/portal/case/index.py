import frappe
from frappe import _

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal"
        raise frappe.Redirect

    case_id = frappe.form_dict.get("name") or _from_path()
    if not case_id:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    user = frappe.session.user
    from thanatos_intel.permissions import is_full_access, visible_case_names
    is_investigator = is_full_access(user)

    if not is_full_access(user):
        names = visible_case_names(user) or []
        if case_id not in names:
            frappe.throw(_("Accesso negato a questo caso."), frappe.PermissionError)

    case = frappe.get_doc("Investigation Case", case_id)
    evidences = frappe.get_all(
        "Investigation Evidence",
        filters={"investigation_case": case.name},
        fields=["name", "evidence_name", "evidence_type", "custody_status",
                "hash_value", "acquisition_date", "attached_file"],
        order_by="acquisition_date desc",
    )
    reports = frappe.get_all(
        "Investigation Report",
        filters={"investigation_case": case.name},
        fields=["name", "report_title", "report_status", "report_date",
                "pdf_file", "pdf_hash"],
        order_by="creation desc",
    )

    # Pipeline steps (solo per cliente: filtra step operator interni)
    from thanatos_intel.pipeline.pipeline import get_pipeline
    client_rec = frappe.db.get_value("Investigation Client",
        {"platform_user": user}, ["name", "client_type"], as_dict=1) if not is_investigator else None
    case_dict = case.as_dict()
    case_dict["case_status"] = case_dict.get("status", "")
    # Risolvi pipeline_key dal Case Type
    if case_dict.get("case_type"):
        pk = frappe.db.get_value("Case Type", case_dict["case_type"], "pipeline_key")
        case_dict["pipeline_key"] = pk or ""
    if client_rec:
        case_dict["client_type"] = client_rec.client_type
    all_steps = get_pipeline(case_dict)
    # Il cliente vede TUTTI gli step ma solo quelli actor=client hanno azione
    pipeline = all_steps

    # Tickets Helpdesk collegati al caso
    try:
        context.tickets = frappe.get_all(
            "HD Ticket",
            filters={"investigation_case": case.name},
            fields=["name", "subject", "status", "creation"],
            order_by="creation desc",
            limit=10,
        )
    except Exception:
        context.tickets = []

    try:
        context.osint_jobs = frappe.get_all(
            "OSINT Job",
            filters={"investigation_case": case.name},
            fields=["name", "target_type", "target_value", "status",
                    "risk_score", "risk_band", "creation"],
            order_by="creation desc", limit=20,
        )
    except Exception:
        context.osint_jobs = []

    context.case = case
    context.evidences = evidences
    context.reports = reports
    context.is_investigator = is_investigator
    context.pipeline = pipeline
    context.pipeline_done = sum(1 for s in pipeline if s["status"] == "done")
    context.pipeline_total = len(pipeline)
    context.pipeline_pct = int(context.pipeline_done / context.pipeline_total * 100) if pipeline else 0
    context.current_step = next((s for s in pipeline if s["status"] == "current"), None)

    # Motore Pratiche (Service Blueprint): se il caso ne ha uno, la board del
    # motore sostituisce la pipeline legacy + mostra bacheca e azioni.
    context.wf = None
    context.bacheca = []
    if case.get("blueprint"):
        try:
            from thanatos_intel.workflow.api import board
            context.wf = board(case.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "case page board")
        context.bacheca = sorted(
            case.get("case_activities") or [],
            key=lambda a: a.get("activity_date") or "", reverse=True)[:25]

    # Bozze legali come writer condivisi (Drive Document)
    context.legal_drafts = []
    try:
        from thanatos_intel.integrations.legal_drafts import list_legal_writers
        context.legal_drafts = list_legal_writers(case.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case page legal_drafts")

    # Tutti i documenti del caso dalla cartella Drive (vista unica), raggruppati
    context.case_documents = {}
    try:
        from thanatos_intel.integrations.legal_drafts import list_case_documents
        for d in list_case_documents(case.name):
            context.case_documents.setdefault(d["folder"], []).append(d)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case page case_documents")

    context.has_wallets = any(
        (ce.entity_type or "") == "Wallet" or
        frappe.db.get_value("Investigation Entity", ce.entity, "entity_type") == "Wallet"
        for ce in (case.get("case_entities") or []))
    try:
        context.spid_pending = frappe.db.count(
            "SPID Document Request", {"investigation_case": case.name, "status": "Richiesto"})
        context.spid_pending += frappe.db.count(
            "Agency Mandate", {"investigation_case": case.name, "status": "Pending Signature"})
    except Exception:
        context.spid_pending = 0
    context.title = f"{case.case_number or case.name} — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context


def _from_path():
    try:
        path = frappe.local.request.path.rstrip("/")
        parts = path.split("/")
        if len(parts) >= 4 and parts[-2] == "case":
            return parts[-1]
    except Exception:
        pass
    return None
