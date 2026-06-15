"""Dati per il cockpit Thanatos (pagina desk /app/thanatos-cockpit).

Una sola chiamata restituisce KPI, flusso, azioni di oggi, dati grafici.
Ogni metrica è best-effort: un errore su una non rompe il cockpit.
"""
import frappe
from frappe.utils import nowdate, add_days, getdate, get_first_day, flt


def _count(dt, filters=None):
    try:
        return frappe.db.count(dt, filters or {})
    except Exception:
        return 0


def _sum(dt, field, filters=None):
    try:
        rows = frappe.get_all(dt, filters=filters or {}, fields=[f"sum(`{field}`) as t"])
        return flt(rows[0].t) if rows else 0
    except Exception:
        return 0


@frappe.whitelist()
def get_cockpit_data():
    today = getdate(nowdate())
    month_start = get_first_day(today)

    # ── KPI ──
    kpi = {
        "casi_aperti": _count("Investigation Case", {"status": "Open"}),
        "casi_totali": _count("Investigation Case"),
        "ddd": _count("Diplomatic Eligibility Case"),
        "reperti": _count("Investigation Evidence"),
        "attivita": _count("Field Activity"),
        "fatturato_mese": _sum("Sales Invoice", "base_grand_total",
                               {"docstatus": 1, "posting_date": [">=", str(month_start)]}),
    }

    # ── Flusso end-to-end (conteggi per fase) ──
    flow = [
        {"label": "Clienti", "count": _count("Investigation Client"), "doctype": "Investigation Client"},
        {"label": "Casi", "count": _count("Investigation Case"), "doctype": "Investigation Case"},
        {"label": "DDD", "count": _count("Diplomatic Eligibility Case"), "doctype": "Diplomatic Eligibility Case"},
        {"label": "Reperti", "count": _count("Investigation Evidence"), "doctype": "Investigation Evidence"},
        {"label": "Report", "count": _count("Investigation Report"), "doctype": "Investigation Report"},
        {"label": "Fatture", "count": _count("Sales Invoice"), "doctype": "Sales Invoice"},
    ]

    # ── Casi per stato (grafico) ──
    casi_per_stato = []
    try:
        rows = frappe.db.sql(
            "select coalesce(status,'n/d') s, count(*) n from `tabInvestigation Case` group by s order by n desc",
            as_dict=True)
        casi_per_stato = [{"label": r.s, "value": r.n} for r in rows]
    except Exception:
        pass

    # ── Mandati DDD per stato ──
    mandati = []
    try:
        rows = frappe.db.sql(
            "select coalesce(status,'n/d') s, count(*) n from `tabAgency Mandate` group by s",
            as_dict=True)
        mandati = [{"label": r.s, "value": r.n} for r in rows]
    except Exception:
        pass

    # ── Azioni di oggi ──
    azioni = []
    try:
        for c in frappe.get_all("Investigation Case", filters={"status": "Open"},
                                fields=["name", "case_title", "modified"],
                                order_by="modified desc", limit=6):
            azioni.append({"type": "Caso aperto", "ref": c.name,
                           "title": c.case_title or c.name, "doctype": "Investigation Case"})
    except Exception:
        pass
    try:
        for m in frappe.get_all("Agency Mandate", filters={"signed_on": ["is", "not set"]},
                                fields=["name", "subject_matter"], limit=4):
            azioni.append({"type": "Mandato da firmare", "ref": m.name,
                           "title": m.subject_matter or m.name, "doctype": "Agency Mandate"})
    except Exception:
        pass

    # ── Attività recenti sul campo ──
    attivita_recenti = []
    try:
        for a in frappe.get_all("Field Activity",
                                fields=["name", "activity_type", "activity_title", "start_datetime", "investigation_case"],
                                order_by="start_datetime desc", limit=6):
            attivita_recenti.append({"ref": a.name, "type": a.activity_type,
                                     "title": a.activity_title or a.activity_type,
                                     "case": a.investigation_case, "when": str(a.start_datetime or "")})
    except Exception:
        pass

    return {
        "kpi": kpi,
        "flow": flow,
        "casi_per_stato": casi_per_stato,
        "mandati": mandati,
        "azioni": azioni,
        "attivita_recenti": attivita_recenti,
        "user": frappe.session.user,
    }
