"""Monitor casi bloccati (SLA/aging del motore pratiche).

A differenza di daily_operator_digest (che lista TUTTI i casi aperti ogni giorno),
questo segnala SOLO i casi il cui step corrente del motore (Case Step Instance in
"In Progress"/"Awaiting Client") è fermo da più di N giorni. Riduce il rumore e
mette il focus sugli stalli reali.

Segnale "fermo da":
- se lo step ha `due` valorizzato e passato -> giorni di ritardo dalla scadenza;
- altrimenti -> giorni dall'ultima modifica del caso (proxy ultima attività).

Alert: un digest per operatore assegnato + uno ad admin per i non assegnati.
Inoltre posta un nudge sulla board del caso (una volta per soglia superata).
"""
import frappe
from frappe.utils import now_datetime, get_datetime, get_url, date_diff, nowdate

# Soglie (giorni). Un gate/awaiting oltre questi giorni = "bloccato".
STUCK_DAYS_GATE = 3      # gate operatore fermo
STUCK_DAYS_CLIENT = 5    # awaiting client fermo (più tolleranza)


def _stuck_days(step, case_modified):
    """Giorni di blocco: dalla `due` se scaduta, altrimenti dall'ultima modifica."""
    due = step.get("due")
    if due:
        d = date_diff(nowdate(), str(get_datetime(due).date()))
        return max(0, d)
    return max(0, date_diff(nowdate(), str(get_datetime(case_modified).date())))


def _op_email(assignee):
    """Risolve l'assignee dello step in una email valida (o None)."""
    if not assignee:
        return None
    if "@" in assignee:
        return assignee
    email = frappe.db.get_value("User", assignee, "email")
    return email or None


def find_stuck_cases():
    """Ritorna la lista dei casi con step corrente fermo oltre soglia."""
    cases = frappe.get_all(
        "Investigation Case",
        filters={"workflow_active": 1},
        fields=["name", "case_title", "client", "modified"],
    )
    stuck = []
    for c in cases:
        steps = frappe.get_all(
            "Case Step Instance",
            filters={"parent": c.name, "status": ("in", ["In Progress", "Awaiting Client"])},
            fields=["seq", "step_label", "status", "assignee", "due", "actor_role"],
            order_by="seq asc",
        )
        if not steps:
            continue
        step = steps[0]
        days = _stuck_days(step, c.modified)
        threshold = STUCK_DAYS_CLIENT if step["status"] == "Awaiting Client" else STUCK_DAYS_GATE
        if days >= threshold:
            stuck.append({
                "case": c.name,
                "title": c.case_title or c.name,
                "client": c.client,
                "assigned_to": _op_email(step.get("assignee")),
                "step_seq": step["seq"],
                "step_label": step["step_label"],
                "step_status": step["status"],
                "stuck_days": days,
                "threshold": threshold,
            })
    return stuck


def _rows(items):
    r = ""
    for it in items:
        r += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>"
            f"<a href='{get_url()}/app/investigation-case/{it['case']}'>{it['case']}</a></td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{it['title'][:40]}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>[{it['step_seq']}] {it['step_label'][:30]}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{it['step_status']}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:center;color:#c0392b;font-weight:600'>{it['stuck_days']}g</td>"
            f"</tr>"
        )
    return r


def _table(items):
    return (
        "<table style='border-collapse:collapse;width:100%;font-size:13px'>"
        "<tr style='background:#152821;color:#fff'>"
        "<th style='padding:6px 10px;text-align:left'>Caso</th>"
        "<th style='padding:6px 10px;text-align:left'>Titolo</th>"
        "<th style='padding:6px 10px;text-align:left'>Step fermo</th>"
        "<th style='padding:6px 10px;text-align:left'>Stato</th>"
        "<th style='padding:6px 10px'>Da</th></tr>"
        f"{_rows(items)}</table>"
    )


def daily_stuck_case_check():
    """Schedulato daily: alert sui casi fermi oltre soglia."""
    stuck = find_stuck_cases()
    if not stuck:
        frappe.logger("stuck_monitor").info(f"[{now_datetime()}] nessun caso bloccato")
        return {"stuck": 0}

    by_op = {}
    unassigned = []
    for it in stuck:
        op = it.get("assigned_to")
        (by_op.setdefault(op, []) if op else unassigned).append(it) if op else unassigned.append(it)

    sent = 0
    for op, items in by_op.items():
        if not op:
            unassigned.extend(items)
            continue
        try:
            frappe.sendmail(
                recipients=[op],
                subject=f"⏳ {len(items)} pratiche ferme oltre soglia",
                message=(
                    f"<p>Ciao, hai <b>{len(items)}</b> pratiche il cui step è fermo oltre la soglia SLA. "
                    f"Interveni per sbloccarle:</p>{_table(items)}"
                    f"<p style='margin-top:14px'><a href='{get_url()}/portal/compiti'>Vai ai compiti →</a></p>"
                ),
            )
            sent += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "stuck_monitor operator mail")

    if unassigned:
        try:
            frappe.sendmail(
                recipients=["admin@thanatos.agency"],
                subject=f"⏳ {len(unassigned)} pratiche ferme SENZA operatore",
                message=(
                    f"<p>Pratiche bloccate oltre soglia e non assegnate a nessun operatore:</p>"
                    f"{_table(unassigned)}"
                ),
            )
            sent += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "stuck_monitor admin mail")

    # nudge sulla board di ogni caso (una riga, best-effort)
    for it in stuck:
        try:
            from thanatos_intel.workflow.notify import append_activity
            doc = frappe.get_doc("Investigation Case", it["case"])
            append_activity(
                doc,
                f"⏳ Promemoria automatico: lo step «{it['step_label']}» è fermo da {it['stuck_days']} giorni (soglia {it['threshold']}g).",
                activity_type="Report",
            )
            doc.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"stuck_monitor nudge {it['case']}")

    frappe.db.commit()
    frappe.logger("stuck_monitor").info(f"[{now_datetime()}] stuck={len(stuck)} mail={sent}")
    return {"stuck": len(stuck), "emails": sent}
