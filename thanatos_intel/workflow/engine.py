"""Motore Pratiche Thanatos.

Una pratica (Investigation Case) collegata a un Service Blueprint scorre i suoi
step:
- AUTO  -> il sistema/cliente esegue, poi si avanza appena l'evento e' arrivato.
- GATE  -> si crea un ToDo per il ruolo di turno e ci si ferma finche' non e'
           completato (operatore/investigatore/avvocato...).

API principali:
- setup_from_blueprint(case)  : materializza gli step dal blueprint
- start(case_name)            : attiva il motore e valuta il primo step
- advance(case_name)          : porta la pratica al primo step che richiede attesa
- complete_step(case_name, seq, note) : chiude uno step GATE e prosegue

Vedi docs/CASE_WORKFLOW_ENGINE.md.
"""
import frappe
from frappe.utils import now_datetime
from thanatos_intel.workflow import notify

# Tier identita': cosa serve nel Client Vault (item Valido) per ogni livello.
_TIER_DOC = {"Base": None, "KYC": "KYC", "KYB": "KYB", "KIT": "KIT"}

# Eventi notifica mappati ai template WABA (gli altri usano solo email+bacheca).
_STEP_EVENT = {"sign": "mandate_ready", "pay": "payment_request", "deliver": "report_ready"}


def setup_from_blueprint(case):
    """Copia gli step del blueprint nel caso (idempotente)."""
    if not case.blueprint:
        return
    if case.get("case_steps"):
        return
    bp = frappe.get_doc("Service Blueprint", case.blueprint)
    case.identity_tier_required = bp.identity_tier
    for i, s in enumerate(bp.steps, start=1):
        case.append("case_steps", {
            "seq": i,
            "step_label": s.step_label,
            "actor_role": s.actor_role,
            "mode": s.mode,
            "action_type": s.action_type,
            "client_visible": s.client_visible,
            "service_code": s.get("service_code"),
            "price": s.get("price") or 0,
            "status": "Pending",
        })


def identity_satisfied(case):
    """(ok, missing) — il cliente soddisfa il tier identità richiesto?
    Integra stato onboarding (kyc/kyb) + Vault (vedi workflow.vault)."""
    from thanatos_intel.workflow import vault
    tier = case.get("identity_tier_required") or "Base"
    if tier == "Base" or not case.client:
        return True, []
    ok = vault.tier_satisfied(case.client, tier)
    return ok, ([] if ok else [tier])


def _role_users(role_name):
    cr = frappe.db.get_value("Case Role", role_name, ["frappe_role", "is_client"], as_dict=True)
    if not cr:
        return [], False
    if cr.is_client:
        return [], True
    if not cr.frappe_role:
        return [], False
    users = frappe.get_all("Has Role", filters={"role": cr.frappe_role, "parenttype": "User"},
                           pluck="parent")
    return [u for u in users if u not in ("Administrator", "Guest")], False


def _resolve_assignee(case, step):
    """User a cui assegnare lo step (best-effort)."""
    if not step.actor_role:
        return None
    users, is_client = _role_users(step.actor_role)
    if is_client and case.client:
        pu = frappe.db.get_value("Investigation Client", case.client, "platform_user")
        if pu and frappe.db.exists("User", pu):
            return pu
        email = frappe.db.get_value("Investigation Client", case.client, "email")
        if email and frappe.db.exists("User", email):
            return email
        return None
    # investigatore: preferisci quello gia' assegnato al caso
    if case.get("assigned_investigator"):
        inv_user = frappe.db.get_value("Investigator", case.assigned_investigator, "platform_user")
        if inv_user:
            return inv_user
    return users[0] if users else None


def _open_todo(case, step):
    assignee = _resolve_assignee(case, step)
    step.assignee = assignee
    if not assignee:
        return
    if frappe.db.exists("ToDo", {"reference_type": "Investigation Case",
                                 "reference_name": case.name, "status": "Open",
                                 "description": ["like", f"%[step {step.seq}]%"]}):
        return
    frappe.get_doc({
        "doctype": "ToDo",
        "allocated_to": assignee,
        "reference_type": "Investigation Case",
        "reference_name": case.name,
        "date": step.get("due"),
        "description": f"[step {step.seq}] {step.step_label} — {case.name}",
        "priority": "Medium",
    }).insert(ignore_permissions=True)


def _step_done(step):
    return step.status in ("Done", "Skipped")


@frappe.whitelist()
def start(case_name):
    case = frappe.get_doc("Investigation Case", case_name)
    if not case.has_permission("write"):
        frappe.throw(frappe._("Permessi insufficienti per avviare la pratica."), frappe.PermissionError)
    setup_from_blueprint(case)
    case.workflow_active = 1
    case.current_step_seq = 0
    case.save(ignore_permissions=True)
    return advance(case_name)


def advance(case_name):
    """Esegue gli step AUTO finche' non incontra uno step che richiede attesa
    (GATE non completato, oppure AUTO che attende un evento esterno).

    Un solo save sul caso per chiamata; le notifiche esterne sono accodate e
    inviate dopo il save."""
    case = frappe.get_doc("Investigation Case", case_name)
    if not case.get("workflow_active"):
        return {"status": "inactive"}

    pending = []  # (message, subject, event, client_visible) da inviare post-save

    def _finish(result):
        case.save(ignore_permissions=True)
        for msg, subj, ev, cv, act in pending:
            notify.channels(case_name, msg, subject=subj, event=ev,
                            client_visible=cv, action_type=act)
        return result

    for step in sorted(case.case_steps, key=lambda s: s.seq):
        if _step_done(step):
            continue

        case.current_step_seq = step.seq

        if step.status in ("In Progress", "Awaiting Client"):
            # gia' fermo qui (gate/evento non ancora risolto)
            return _finish({"status": "waiting", "step": step.seq,
                            "label": step.step_label, "step_status": step.status})

        # status Pending
        if step.mode == "GATE":
            step.status = "In Progress"
            _open_todo(case, step)
            notify.append_activity(case, f"In attesa: «{step.step_label}» ({step.actor_role}).")
            pending.append((f"Pratica «{case_name}»: in lavorazione, fase «{step.step_label}».",
                            "Aggiornamento pratica", None, bool(step.client_visible), None))
            return _finish({"status": "gated", "step": step.seq,
                            "label": step.step_label, "assignee": step.assignee})

        # AUTO ad azione ESTERNA: attende l'evento del cliente
        if step.action_type in ("sign", "pay", "upload", "ai_question"):
            step.status = "Awaiting Client"
            notify.append_activity(case, f"Azione richiesta al cliente: «{step.step_label}».")
            pending.append((f"È richiesta un'azione sulla pratica «{case_name}»: {step.step_label}.",
                            "Azione richiesta sulla pratica",
                            _STEP_EVENT.get(step.action_type), bool(step.client_visible), step.action_type))
            return _finish({"status": "awaiting", "step": step.seq, "label": step.step_label})

        # AUTO di sistema (apertura, notify, work/deliver automatici): pass-through.
        # L'azione reale (genera mandato, consegna report...) si aggancera' qui in F2.
        # AUTO di sistema: dispatch azioni reali prima del pass-through Done.
        _run_auto_step(case, step)
        step.status = "Done"
        step.completed_on = now_datetime()
        notify.append_activity(case, f"«{step.step_label}» eseguito.")
        if step.client_visible:
            pending.append((f"Pratica «{case_name}»: {step.step_label}.",
                            "Aggiornamento pratica",
                            _STEP_EVENT.get(step.action_type), True, step.action_type))
        continue

    case.workflow_active = 0
    notify.append_activity(case, "Pratica completata.")
    pending.append(("La sua pratica è stata completata. Trova il report nel portale.",
                    "Pratica completata", "report_ready", True, "deliver"))
    return _finish({"status": "done"})




def _run_auto_step(case, step):
    try:
        label=(step.step_label or '').lower()
        at=step.action_type or ''
        if at=='work' and 'generazione mandato' in label:
            from thanatos_intel.workflow.engagement import prepare_mandate
            prepare_mandate(case.name)
        elif at=='deliver':
            _auto_deliver(case)
        elif at=='notify':
            _auto_notify_closure(case)
        elif at=='work' and 'conservazione' in label:
            _auto_set_retention(case)
    except Exception:
        frappe.log_error(frappe.get_traceback(),'auto_step '+str(step.step_label or ''))

def _auto_deliver(case):
    try:
        from thanatos_intel.workflow.notify import channels
        t=case.case_title or case.name
        channels(case.name,message='Il report di '+t+' e disponibile.',subject='Report disponibile',action_type='report_ready')
    except Exception:
        frappe.log_error(frappe.get_traceback(),'auto_deliver')

def _auto_notify_closure(case):
    try:
        from thanatos_intel.workflow.notify import channels
        t=case.case_title or case.name
        channels(case.name,message='Pratica '+t+' chiusa.',subject='Pratica chiusa',action_type='deliver')
    except Exception:pass

def _auto_set_retention(case):
    import datetime
    try:
        if not frappe.db.get_value('Investigation Case',case.name,'retention_until'):
            ret=frappe.utils.getdate()+datetime.timedelta(days=1825)
            frappe.db.set_value('Investigation Case',case.name,'retention_until',str(ret),update_modified=False)
    except Exception:pass


@frappe.whitelist()
def complete_step(case_name, seq, note=None):
    """Chiude lo step indicato (gate sbloccato) e fa proseguire la pratica."""
    case = frappe.get_doc("Investigation Case", case_name)
    seq = int(seq)
    label = None
    for step in case.case_steps:
        if step.seq == seq:
            step.status = "Done"
            step.completed_on = now_datetime()
            if note:
                step.note = note
            label = step.step_label
            break
    if label is None:
        frappe.throw(f"Step {seq} non trovato nella pratica {case_name}")
    import hashlib
    _evd = hashlib.sha256(
        f"{case_name}|{seq}|{label}|{frappe.session.user}|{now_datetime()}".encode("utf-8")
    ).hexdigest()
    notify.append_activity(case, f"Step «{label}» completato. · evidenza SHA-256 {_evd[:16]}…")
    case.save(ignore_permissions=True)
    try:
        frappe.get_doc({
            "doctype": "Chain Of Custody Event",
            "event_type": "Modified",
            "related_reference": case_name,
            "notes": f"Workflow: step «{label}» (#{seq}) completato da {frappe.session.user}. SHA-256: {_evd}",
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "step custody evidence")
    for td in frappe.get_all("ToDo", filters={
        "reference_type": "Investigation Case", "reference_name": case_name,
        "status": "Open", "description": ["like", f"%[step {seq}]%"]}, pluck="name"):
        frappe.db.set_value("ToDo", td, "status", "Closed")
    return advance(case_name)


@frappe.whitelist()
def case_state(case_name):
    """Riepilogo stato motore per UI/debug."""
    case = frappe.get_doc("Investigation Case", case_name)
    ok, missing = identity_satisfied(case)
    return {
        "blueprint": case.blueprint,
        "active": bool(case.get("workflow_active")),
        "current_step_seq": case.get("current_step_seq"),
        "identity_ok": ok,
        "identity_missing": missing,
        "steps": [{"seq": s.seq, "label": s.step_label, "role": s.actor_role,
                   "mode": s.mode, "status": s.status, "assignee": s.assignee}
                  for s in sorted(case.case_steps, key=lambda s: s.seq)],
    }
