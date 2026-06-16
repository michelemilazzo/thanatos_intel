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
            "status": "Pending",
        })


def identity_satisfied(case):
    """(ok, missing) — verifica che il Vault del cliente copra il tier richiesto."""
    tier = case.get("identity_tier_required") or "Base"
    need = _TIER_DOC.get(tier)
    if not need or not case.client:
        return True, []
    has = frappe.db.exists("Client Vault Item", {
        "client": case.client, "doc_kind": need, "status": "Valido",
    })
    return bool(has), ([] if has else [need])


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


def start(case_name):
    case = frappe.get_doc("Investigation Case", case_name)
    setup_from_blueprint(case)
    case.workflow_active = 1
    case.current_step_seq = 0
    case.save(ignore_permissions=True)
    return advance(case_name)


def advance(case_name):
    """Esegue gli step AUTO finche' non incontra uno step che richiede attesa
    (GATE non completato, oppure AUTO che attende un evento esterno)."""
    case = frappe.get_doc("Investigation Case", case_name)
    if not case.get("workflow_active"):
        return {"status": "inactive"}

    for step in sorted(case.case_steps, key=lambda s: s.seq):
        if _step_done(step):
            continue

        case.current_step_seq = step.seq

        if step.status == "Pending":
            if step.mode == "GATE":
                step.status = "In Progress"
                _open_todo(case, step)
                msg = f"Pratica in attesa: «{step.step_label}»."
                case.save(ignore_permissions=True)
                notify.dispatch(case_name, msg, subject="Aggiornamento pratica",
                                client_visible=bool(step.client_visible))
                return {"status": "gated", "step": step.seq, "label": step.step_label,
                        "assignee": step.assignee}
            else:
                # AUTO: gli step ad azione esterna (firma/pagamento/upload del
                # cliente) attendono l'evento; gli altri li chiude il chiamante.
                if step.action_type in ("sign", "pay", "upload", "ai_question"):
                    step.status = "Awaiting Client"
                    case.save(ignore_permissions=True)
                    notify.dispatch(case_name,
                                    f"Azione richiesta: «{step.step_label}».",
                                    subject="Azione richiesta sulla pratica",
                                    event=_STEP_EVENT.get(step.action_type),
                                    client_visible=bool(step.client_visible))
                    return {"status": "awaiting", "step": step.seq, "label": step.step_label}
                # azioni di sistema (notify/work auto/deliver auto): segna in corso
                step.status = "In Progress"
                case.save(ignore_permissions=True)
                return {"status": "running", "step": step.seq, "label": step.step_label}

        # gia' In Progress / Awaiting Client -> resta fermo qui
        case.save(ignore_permissions=True)
        return {"status": "waiting", "step": step.seq, "label": step.step_label,
                "step_status": step.status}

    # nessuno step pendente -> pratica completata
    case.workflow_active = 0
    case.save(ignore_permissions=True)
    notify.dispatch(case_name, "Pratica completata. Tutti gli step sono chiusi.",
                    subject="Pratica completata", event="report_ready")
    return {"status": "done"}


@frappe.whitelist()
def complete_step(case_name, seq, note=None):
    """Chiude lo step indicato e fa proseguire la pratica."""
    case = frappe.get_doc("Investigation Case", case_name)
    seq = int(seq)
    for step in case.case_steps:
        if step.seq == seq:
            step.status = "Done"
            step.completed_on = now_datetime()
            if note:
                step.note = note
            break
    else:
        frappe.throw(f"Step {seq} non trovato nella pratica {case_name}")
    case.save(ignore_permissions=True)
    # chiudi eventuale ToDo aperto
    for td in frappe.get_all("ToDo", filters={
        "reference_type": "Investigation Case", "reference_name": case_name,
        "status": "Open", "description": ["like", f"%[step {seq}]%"]}, pluck="name"):
        frappe.db.set_value("ToDo", td, "status", "Closed")
    notify.dispatch(case_name, f"Step «{step.step_label}» completato.",
                    subject="Aggiornamento pratica",
                    client_visible=bool(step.client_visible))
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
