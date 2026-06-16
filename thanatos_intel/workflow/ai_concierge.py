"""AI concierge del caso (Fase 5): analizza lo stato della pratica e propone
il prossimo passo / cosa chiedere al cliente, pubblicandolo in bacheca.
Riusa il gateway MMOS AI (ai.doc_ingest._gateway → POST /chat)."""
import frappe
from frappe.utils import now_datetime

_SYS = ("Sei l'assistente investigativo di Thanatos Intel. Dato lo stato di una "
        "pratica, suggerisci in modo conciso (max 80 parole, in italiano) il "
        "prossimo passo operativo concreto e/o quali informazioni o documenti "
        "chiedere al cliente. Niente preamboli, vai al punto.")


def _resp_text(resp):
    if not resp:
        return None
    if isinstance(resp, str):
        return resp.strip()
    for k in ("response", "message", "content", "text", "reply", "answer"):
        v = resp.get(k) if isinstance(resp, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for kk in ("content", "text", "message"):
                if isinstance(v.get(kk), str) and v[kk].strip():
                    return v[kk].strip()
    return None


@frappe.whitelist()
def suggest_next(case_name):
    """Genera un suggerimento AI sul prossimo passo e lo posta in bacheca."""
    from thanatos_intel.workflow.api import _can_see_case
    if not _can_see_case(case_name):
        frappe.throw("Accesso negato.", frappe.PermissionError)
    from thanatos_intel.ai.doc_ingest import _gateway

    case = frappe.get_doc("Investigation Case", case_name)
    steps = sorted(case.get("case_steps") or [], key=lambda s: s.seq)
    cur = next((s for s in steps if s.status in ("In Progress", "Awaiting Client")), None)
    acts = [a.description for a in (case.get("case_activities") or [])][-8:]
    done = [s.step_label for s in steps if s.status == "Done"]
    msg = (f"Pratica: {case.get('case_title') or case.name}\n"
           f"Tipo: {case.get('case_type')}\n"
           f"Step corrente: {cur.step_label if cur else '—'} "
           f"(stato {cur.status if cur else '—'}, ruolo {cur.actor_role if cur else '—'})\n"
           f"Step completati: {', '.join(done) or '—'}\n"
           f"Ultime attività: {'; '.join(acts) or '—'}\n"
           f"Qual è il prossimo passo concreto?")
    resp = _gateway(msg, system=_SYS, task_type="chat")
    text = _resp_text(resp)
    if not text:
        return {"ok": False, "error": "AI non disponibile al momento."}

    case.append("case_activities", {
        "activity_date": now_datetime(), "activity_type": "Report",
        "description": ("🤖 AI: " + text)[:500], "operator": frappe.session.user})
    case.save(ignore_permissions=True)
    return {"ok": True, "suggestion": text}
