"""API del Motore Pratiche per il portale (wizard, bacheca, compiti).

Tutti i metodi sono whitelisted e applicano i confini: il cliente vede/agisce
solo sulle proprie pratiche; gli operatori (is_full_access) su tutte.
"""
import frappe
from frappe import _
from thanatos_intel.workflow import engine, notify

_PK_MAP = {"Indagine Investigativa": "Investigation", "OSINT Lookup": "OSINT"}


def _client_for_user(user=None):
    user = user or frappe.session.user
    return frappe.db.get_value(
        "Investigation Client", {"platform_user": user},
        ["name", "client_type"], as_dict=True)


def _is_operator(user=None):
    from thanatos_intel.permissions import is_full_access
    return is_full_access(user or frappe.session.user)


def _can_see_case(case_name, user=None):
    user = user or frappe.session.user
    if _is_operator(user):
        return True
    cl = _client_for_user(user)
    return bool(cl and frappe.db.get_value("Investigation Case", case_name, "client") == cl.name)


def _resolve_case_type(bp):
    if bp.case_type:
        return bp.case_type
    pk = _PK_MAP.get(bp.name)
    if pk:
        ct = frappe.db.get_value("Case Type", {"pipeline_key": pk}, "name")
        if ct:
            return ct
    return frappe.db.get_value("Case Type", {}, "name")


@frappe.whitelist()
def available_blueprints():
    """Servizi attivabili (blueprint attivi)."""
    return frappe.get_all(
        "Service Blueprint", filters={"is_active": 1},
        fields=["name", "blueprint_name", "category", "self_serve",
                "identity_tier", "description"],
        order_by="self_serve desc, blueprint_name")


@frappe.whitelist()
def open_practice(blueprint, case_title, subject=None, objective=None, jurisdiction=None):
    """Apre una pratica dal wizard cliente: crea il caso, materializza gli step
    (after_insert) e avvia il motore."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Devi accedere."), frappe.PermissionError)
    cl = _client_for_user(user)
    if not cl and not _is_operator(user):
        frappe.throw(_("Nessun profilo cliente associato all'utente."))
    bp = frappe.get_doc("Service Blueprint", blueprint)

    desc_parts = []
    if subject:
        desc_parts.append(f"<p><b>Soggetto / obiettivo:</b> {frappe.utils.escape_html(subject)}</p>")
    if objective:
        desc_parts.append(f"<p>{frappe.utils.escape_html(objective)}</p>")
    if jurisdiction:
        desc_parts.append(f"<p><b>Giurisdizione:</b> {frappe.utils.escape_html(jurisdiction)}</p>")

    case = frappe.get_doc({
        "doctype": "Investigation Case",
        "case_title": case_title,
        "case_type": _resolve_case_type(bp),
        "client": cl.name if cl else None,
        "blueprint": bp.name,
        "status": "Open",
        "summary": (subject or "")[:140],
        "description": "".join(desc_parts),
    })
    case.flags.ignore_mandatory = True
    case.insert(ignore_permissions=True)

    ok, missing = engine.identity_satisfied(case)
    state = engine.start(case.name)
    return {"case": case.name, "identity_ok": ok, "identity_missing": missing,
            "state": state, "url": f"/portal/case/{case.name}"}


def _step_rows(case):
    """Step del motore nel formato atteso dalla case page (label/status/actor/...)."""
    rows = []
    cur = case.get("current_step_seq") or 0
    for s in sorted(case.case_steps, key=lambda s: s.seq):
        if s.status in ("Done", "Skipped"):
            ui = "done"
        elif s.status in ("In Progress", "Awaiting Client"):
            ui = "current"
        else:
            ui = "todo"
        role = frappe.db.get_value("Case Role", s.actor_role, "is_client") if s.actor_role else 0
        rows.append({
            "seq": s.seq, "label": s.step_label, "status": ui, "raw_status": s.status,
            "actor": "client" if role else "operator", "role": s.actor_role,
            "mode": s.mode, "action_type": s.action_type, "assignee": s.assignee,
            "client_visible": s.client_visible,
        })
    return rows


@frappe.whitelist()
def board(case_name):
    """Stato pratica per la case page: step motore + azione cliente corrente."""
    if not _can_see_case(case_name):
        frappe.throw(_("Accesso negato."), frappe.PermissionError)
    case = frappe.get_doc("Investigation Case", case_name)
    if not case.get("blueprint"):
        return {"has_workflow": False}
    steps = _step_rows(case)
    done = sum(1 for s in steps if s["status"] == "done")
    # azione cliente corrente (step Awaiting Client visibile)
    client_action = next((s for s in steps if s["raw_status"] == "Awaiting Client"
                          and s["actor"] == "client" and s["client_visible"]), None)
    return {
        "has_workflow": True, "active": bool(case.get("workflow_active")),
        "blueprint": case.blueprint, "steps": steps,
        "done": done, "total": len(steps),
        "pct": int(done * 100 / len(steps)) if steps else 0,
        "client_action": client_action,
        "is_operator": _is_operator(),
    }


@frappe.whitelist()
def client_act(case_name, seq):
    """Il cliente completa la propria azione corrente (firma/pagamento/upload).

    F2: registra il completamento e avanza. L'aggancio reale a DocuSeal/Stripe/
    upload sara' agganciato in F2.x/F4 sostituendo questo completamento manuale."""
    if not _can_see_case(case_name):
        frappe.throw(_("Accesso negato."), frappe.PermissionError)
    return engine.complete_step(case_name, int(seq), note="Completato dal cliente")


@frappe.whitelist()
def complete_gate(case_name, seq, note=None):
    """Operatore/assegnatario chiude uno step GATE e fa proseguire la pratica."""
    user = frappe.session.user
    case = frappe.get_doc("Investigation Case", case_name)
    step = next((s for s in case.case_steps if s.seq == int(seq)), None)
    if not step:
        frappe.throw(_("Step non trovato."))
    if not (_is_operator(user) or step.assignee == user):
        frappe.throw(_("Solo l'assegnatario o un operatore può completare questo step."),
                     frappe.PermissionError)
    return engine.complete_step(case_name, int(seq), note=note)


@frappe.whitelist()
def post_message(case_name, message):
    """Messaggio in bacheca (feed del caso). Cliente e operatori scrivono qui."""
    if not _can_see_case(case_name):
        frappe.throw(_("Accesso negato."), frappe.PermissionError)
    message = (message or "").strip()
    if not message:
        frappe.throw(_("Messaggio vuoto."))
    who = "Operatore" if _is_operator() else "Cliente"
    case = frappe.get_doc("Investigation Case", case_name)
    case.append("case_activities", {
        "activity_date": frappe.utils.now_datetime(),
        "activity_type": "Report",
        "description": f"💬 {who}: {message}",
        "operator": frappe.session.user,
    })
    case.save(ignore_permissions=True)
    return {"ok": True}


@frappe.whitelist()
def my_tasks():
    """Compiti aperti dell'utente: step GATE assegnati a lui (In Progress)."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Devi accedere."), frappe.PermissionError)
    op = _is_operator(user)
    # step in corso assegnati a me (o tutti, se operatore senza assignee risolto)
    rows = frappe.db.sql("""
        SELECT csi.parent AS case_name, csi.seq, csi.step_label, csi.actor_role,
               csi.assignee, ic.case_title, ic.status AS case_status
        FROM `tabCase Step Instance` csi
        JOIN `tabInvestigation Case` ic ON ic.name = csi.parent
        WHERE csi.status = 'In Progress'
          AND (csi.assignee = %(u)s {op_clause})
        ORDER BY ic.modified DESC
    """.format(op_clause="OR 1=1" if op else ""), {"u": user}, as_dict=True)
    return rows
