"""Dati per il cockpit Thanatos (pagina desk /app/thanatos-cockpit).

Una sola chiamata restituisce: saluto, KPI, agenda/scadenziario, prossimi step
guidati, inbox Intel (lead), suggerimenti proattivi (Intel), flusso e grafici.
Ogni metrica è best-effort: un errore su una non rompe il cockpit.
"""
import frappe
from frappe.utils import nowdate, add_days, getdate, get_first_day, flt, now_datetime, get_fullname


def _count(dt, filters=None):
    try:
        return frappe.db.count(dt, filters or {})
    except Exception:
        return 0


def _sum(dt, field, filters=None):
    try:
        rows = frappe.get_all(dt, filters=filters or {}, fields=[field], limit=0)
        return sum(flt(r.get(field)) for r in rows)
    except Exception:
        return 0


def _all(dt, **kw):
    try:
        return frappe.get_all(dt, **kw)
    except Exception:
        return []


def _nav_links():
    """Tutti i link operativi, presi dal workspace 'Thanatos Intel' (sync auto)."""
    nav = []
    try:
        ws = frappe.get_doc("Workspace", "Thanatos Intel")
        cur = None
        for l in ws.links:
            if l.type == "Card Break":
                cur = {"title": l.label, "items": []}
                nav.append(cur)
            elif l.type == "Link" and not l.get("hidden"):
                if cur is None:
                    cur = {"title": "Generale", "items": []}
                    nav.append(cur)
                cur["items"].append({"label": l.label, "to": l.link_to, "kind": l.link_type})
    except Exception:
        pass
    # gruppo Compliance/ISMS (doctype del modulo Thanatos Compliance)
    comp = [("Policy & SOP", "Compliance Policy"), ("Risk Register", "Risk Register Item"),
            ("Registro Trattamenti (ROPA)", "ROPA Entry"),
            ("Acquisizione capacità", "Capability Acquisition")]
    items = [{"label": l, "to": d, "kind": "DocType"} for l, d in comp if frappe.db.exists("DocType", d)]
    if items:
        nav.append({"title": "Compliance / ISMS (ISO)", "items": items})
    return nav


@frappe.whitelist()
def get_cockpit_data():
    today = getdate(nowdate())
    month_start = get_first_day(today)
    now = now_datetime()
    horizon = add_days(today, 14)
    user = frappe.session.user

    # ── KPI ──
    kpi = {
        "casi_aperti": _count("Investigation Case", {"status": ["in", ["Open", "In Progress", "Review"]]}),
        "lead_nuovi": _count("Intel Lead", {"status": ["in", ["Nuovo", "In Valutazione"]]}),
        "appuntamenti_oggi": _count("Investigation Appointment",
                                    {"appointment_date": str(today), "status": ["!=", "Annullato"]}),
        "reperti": _count("Investigation Evidence"),
        "casi_totali": _count("Investigation Case"),
        "fatturato_mese": _sum("Sales Invoice", "base_grand_total",
                               {"docstatus": 1, "posting_date": [">=", str(month_start)]}),
    }

    # ── Agenda / Scadenziario (prossimi 14 gg): appuntamenti + step con scadenza + chiusure caso ──
    agenda = []
    for a in _all("Investigation Appointment",
                  filters={"appointment_date": ["between", [str(today), str(horizon)]],
                           "status": ["!=", "Annullato"]},
                  fields=["name", "title", "appointment_type", "appointment_date",
                          "appointment_time", "status", "linked_case"],
                  order_by="appointment_date asc", limit=20):
        agenda.append({"when": str(a.appointment_date), "time": str(a.appointment_time or "")[:5],
                       "kind": a.appointment_type or "Appuntamento", "title": a.title or a.name,
                       "doctype": "Investigation Appointment", "ref": a.name, "icon": "📅"})
    for s in _all("Case Step Instance",
                  filters={"parenttype": "Investigation Case",
                           "status": ["in", ["Pending", "In Progress", "Awaiting Client", "Blocked"]],
                           "due": ["between", [str(today), str(horizon) + " 23:59:59"]]},
                  fields=["parent", "step_label", "due", "status"],
                  order_by="due asc", limit=20):
        agenda.append({"when": str(s.due)[:10], "time": str(s.due)[11:16],
                       "kind": "Scadenza step", "title": (s.step_label or "Step") + " — " + s.parent,
                       "doctype": "Investigation Case", "ref": s.parent, "icon": "⏰"})
    agenda.sort(key=lambda x: (x["when"], x["time"]))
    agenda = agenda[:12]

    # ── Prossimi step guidati ("fai questo, carica quello") ──
    prossimi_step = []
    for s in _all("Case Step Instance",
                  filters={"parenttype": "Investigation Case",
                           "status": ["in", ["Pending", "In Progress", "Awaiting Client", "Blocked"]]},
                  fields=["parent", "seq", "step_label", "status", "due", "action_type", "assignee"],
                  order_by="due asc", limit=12):
        prossimi_step.append({"case": s.parent, "label": s.step_label or ("Step " + str(s.seq or "")),
                              "status": s.status, "action": s.action_type or "",
                              "due": str(s.due or "")[:16], "assignee": s.assignee or ""})

    # ── Inbox Intel (lead da triage) ──
    intel_inbox = []
    for l in _all("Intel Lead",
                  filters={"status": ["in", ["Nuovo", "In Valutazione"]]},
                  fields=["name", "source_type", "source_name", "content", "priority",
                          "intel_score", "received_at"],
                  order_by="received_at desc", limit=8):
        intel_inbox.append({"ref": l.name, "source": l.source_type or "—",
                            "from": l.source_name or "", "priority": l.priority or "Media",
                            "score": l.intel_score or 0,
                            "snippet": (l.content or "")[:110],
                            "when": str(l.received_at or "")[:16]})

    # ── Suggerimenti proattivi (Intel) — regole v1, base per l'AI ──
    sugg = []
    n = _count("Intel Lead", {"status": "Nuovo"})
    if n:
        sugg.append({"icon": "🔔", "sev": "info",
                     "text": f"{n} lead da valutare in arrivo",
                     "route": ["List", "Intel Lead", {"status": "Nuovo"}]})
    fermi = _all("Investigation Case",
                 filters={"status": ["in", ["Open", "In Progress"]],
                          "modified": ["<", str(add_days(today, -5))]},
                 fields=["name"], limit=50)
    if fermi:
        sugg.append({"icon": "🐌", "sev": "warn",
                     "text": f"{len(fermi)} casi fermi da oltre 5 giorni",
                     "route": ["List", "Investigation Case", {"status": "Open"}]})
    bloccati = _count("Case Step Instance", {"parenttype": "Investigation Case", "status": "Blocked"})
    if bloccati:
        sugg.append({"icon": "⛔", "sev": "warn",
                     "text": f"{bloccati} step bloccati da sbloccare",
                     "route": ["List", "Investigation Case", {"workflow_active": 1}]})
    mand = _count("Agency Mandate", {"signed_on": ["is", "not set"]})
    if mand:
        sugg.append({"icon": "✍️", "sev": "info",
                     "text": f"{mand} mandati da firmare",
                     "route": ["List", "Agency Mandate"]})
    onb = _count("Investigation Client",
                 {"onboarding_status": ["in", ["Pending KYC", "Pending KYB", "Under Review"]]})
    if onb:
        sugg.append({"icon": "🪪", "sev": "info",
                     "text": f"{onb} clienti con onboarding da completare",
                     "route": ["List", "Investigation Client", {"onboarding_status": "Under Review"}]})
    fail = _count("OSINT Job", {"status": "Failed"})
    if fail:
        sugg.append({"icon": "♻️", "sev": "warn",
                     "text": f"{fail} job OSINT falliti da rilanciare",
                     "route": ["List", "OSINT Job", {"status": "Failed"}]})
    if not sugg:
        sugg.append({"icon": "✅", "sev": "ok", "text": "Tutto sotto controllo. Nessuna azione urgente.", "route": None})

    # ── Casi attivi (sintesi) ──
    casi_attivi = []
    for c in _all("Investigation Case",
                  filters={"status": ["in", ["Open", "In Progress", "Review"]]},
                  fields=["name", "case_title", "status", "priority", "client",
                          "payment_status", "current_step_seq", "workflow_active", "modified"],
                  order_by="modified desc", limit=10):
        casi_attivi.append({"ref": c.name, "title": c.case_title or c.name, "status": c.status,
                            "priority": c.priority or "Normal", "client": c.client or "",
                            "payment": c.payment_status or "", "when": str(c.modified)[:10]})

    # ── Casi per stato (grafico) ──
    casi_per_stato = []
    try:
        rows = frappe.db.sql(
            "select coalesce(status,'n/d') s, count(*) n from `tabInvestigation Case` group by s order by n desc",
            as_dict=True)
        casi_per_stato = [{"label": r.s, "value": r.n} for r in rows]
    except Exception:
        pass

    # ── Flusso end-to-end ──
    flow = [
        {"label": "Lead", "count": _count("Intel Lead"), "doctype": "Intel Lead"},
        {"label": "Clienti", "count": _count("Investigation Client"), "doctype": "Investigation Client"},
        {"label": "Casi", "count": _count("Investigation Case"), "doctype": "Investigation Case"},
        {"label": "OSINT", "count": _count("OSINT Job"), "doctype": "OSINT Job"},
        {"label": "Reperti", "count": _count("Investigation Evidence"), "doctype": "Investigation Evidence"},
        {"label": "Report", "count": _count("Investigation Report"), "doctype": "Investigation Report"},
        {"label": "Fatture", "count": _count("Sales Invoice"), "doctype": "Sales Invoice"},
    ]

    return {
        "user": user,
        "fullname": get_fullname(user),
        "kpi": kpi,
        "agenda": agenda,
        "prossimi_step": prossimi_step,
        "intel_inbox": intel_inbox,
        "suggerimenti": sugg,
        "casi_attivi": casi_attivi,
        "casi_per_stato": casi_per_stato,
        "flow": flow,
        "nav": _nav_links(),
    }


@frappe.whitelist()
def ai_brief():
    """Intel AI: priorita' operative di oggi via gateway MMOS AI. On-demand."""
    from thanatos_intel.ai.doc_ingest import _gateway
    from thanatos_intel.workflow.ai_concierge import _resp_text
    today = getdate(nowdate())
    open_cases = _all("Investigation Case",
                      filters={"status": ["in", ["Open", "In Progress", "Review"]]},
                      fields=["name", "case_title", "priority", "modified", "client"],
                      order_by="modified asc", limit=40)
    stalled = [c for c in open_cases if str(c.modified) < str(add_days(today, -5))]
    leads = _all("Intel Lead", filters={"status": "Nuovo"},
                 fields=["source_type", "content"], limit=10)
    appts = _all("Investigation Appointment",
                 filters={"appointment_date": str(today), "status": ["!=", "Annullato"]},
                 fields=["title", "appointment_type"], limit=10)
    blocked = _count("Case Step Instance", {"parenttype": "Investigation Case", "status": "Blocked"})
    lines = [f"Casi aperti: {len(open_cases)} (fermi 5+ giorni: {len(stalled)}). "
             f"Lead nuovi: {len(leads)}. Step bloccati: {blocked}. Appuntamenti oggi: {len(appts)}."]
    if stalled:
        lines.append("Casi fermi: " + "; ".join((c.case_title or c.name) + f" [{c.priority or 'Normal'}]"
                                                 for c in stalled[:8]))
    if leads:
        lines.append("Lead da valutare: " + "; ".join((l.source_type or "") + ": " + ((l.content or "")[:60])
                                                       for l in leads[:6]))
    if appts:
        lines.append("Oggi in agenda: " + "; ".join((a.title or a.appointment_type or "") for a in appts))
    msg = "Stato operativo di oggi:\n" + "\n".join(lines) + \
          "\n\nElenca le 3-5 priorita' della giornata, in ordine."
    sys = ("Sei Intel, il capo-analista di Thanatos Intel. Dato lo stato operativo, elenca le 3-5 "
           "priorita' della giornata in italiano, ognuna su una riga come '- <azione concreta> -> <perche'>'. "
           "Conciso, concreto, niente preamboli.")
    resp = _gateway(msg, system=sys, task_type="chat")
    text = _resp_text(resp)
    if not text:
        return {"ok": False, "error": "Intel AI non raggiungibile al momento."}
    try:
        usage = (resp or {}).get("usage") or {}
        if usage.get("tokens_in") or usage.get("tokens_out"):
            from thanatos_intel.billing.ai_meter import record_usage
            record_usage(client=None, model=(resp or {}).get("model", "default"),
                         tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
                         reference="cockpit-brief")
    except Exception:
        pass
    return {"ok": True, "text": text}
