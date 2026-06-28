"""Orchestratore della pipeline investigativa + checklist di avanzamento.

- case_progress(case): checklist auto-derivata dallo stato reale (✅ fatto / ☐ manca).
- run_full_analysis(case): lancia in sequenza tutte le analisi disponibili (screening,
  doppia cessione, domande, riconciliazione fatture, fascicolo) e aggiorna la checklist.
Pensato per girare in background (enqueue) ed essere agganciato all'apertura caso.
"""
import frappe
from frappe.utils import now_datetime


def _has_activity(case, needle):
    return bool(frappe.db.sql(
        """SELECT 1 FROM `tabCase Activity` WHERE parent=%s AND description LIKE %s LIMIT 1""",
        (case, f"%{needle}%")))


def _has_file(case, needle):
    return bool(frappe.db.exists("File", {"attached_to_doctype": "Investigation Case",
                                          "attached_to_name": case, "file_name": ["like", f"%{needle}%"]}))


def _checklist(case):
    c = frappe.get_doc("Investigation Case", case)
    n_ev = frappe.db.count("Investigation Evidence", {"investigation_case": case})
    n_auth = frappe.db.sql("""SELECT COUNT(*) FROM `tabInvestigation Evidence`
        WHERE investigation_case=%s AND authenticity IS NOT NULL AND authenticity!='' """, (case,))[0][0]
    items = [
        ("Documenti ingeriti", n_ev > 0, f"{n_ev} reperti"),
        ("Autenticità valutata", n_auth > 0, f"{n_auth}/{n_ev}"),
        ("Parti identificate (entità)", len(c.get("case_entities") or []) > 0, f"{len(c.get('case_entities') or [])} parti"),
        ("Anagrafica cliente", bool(c.get("client")), c.get("client") or "—"),
        ("Screening parti (VIES/sanzioni)", _has_activity(case, "Screening automatico parti") or _has_activity(case, "VERIFICA PARTI"), ""),
        ("Verifica camerale (Registro Imprese)", _has_activity(case, "Verifica camerale") or bool(frappe.db.exists("Investigation Evidence", {"investigation_case": case, "source": "Registro Imprese"})), ""),
        ("Rilevatore doppia cessione", _has_activity(case, "DOPPIA CESSIONE"), ""),
        ("Domande investigative", _has_activity(case, "DOMANDE INVESTIGATIVE"), ""),
        ("Riconciliazione fatture (XML)", _has_activity(case, "RICONCILIAZIONE FATTURE"), ""),
        ("Mandato d'incarico", bool(frappe.db.exists("Agency Mandate", {"investigation_case": case})), ""),
        ("Delega AdE generata", _has_file(case, "DELEGA AdE"), ""),
        ("Formulario investigativo", _has_file(case, "FORMULARIO"), ""),
        ("Fascicolo generato", _has_file(case, "FASCICOLO"), ""),
    ]
    # passi che richiedono azione esterna (delega cliente) — restano TODO finché non arrivano dati
    todo_ext = [
        ("Acquisizione XML fatture (via delega Trading HU)", frappe.db.count("File", {"attached_to_doctype": "Investigation Case", "attached_to_name": case, "file_name": ["like", "%.xml"]}) > 0),
        ("Verifica stato credito su cassetto/Piattaforma AdE (delega)", _has_activity(case, "STATO CREDITO ADE")),
        ("Quantificazione danno cliente €800.000 (tracciamento bonifici)", _has_activity(case, "follow-the-money") or _has_activity(case, "bonifici tracciati")),
    ]
    return items, todo_ext


@frappe.whitelist()
def case_progress(case, record=0):
    items, todo_ext = _checklist(case)
    done = sum(1 for _, ok, _ in items if ok)
    pct = round(100 * done / max(1, len(items)))
    lines = [f"📋 AVANZAMENTO CASO — {done}/{len(items)} fasi completate ({pct}%)"]
    for label, ok, extra in items:
        lines.append(f"{'✅' if ok else '☐'} {label}" + (f" — {extra}" if extra else ""))
    lines.append("— Azioni che richiedono la delega/dati del cliente —")
    for label, ok in todo_ext:
        lines.append(f"{'✅' if ok else '☐'} {label}")
    text = "\n".join(lines)
    if int(record):
        try:
            c = frappe.get_doc("Investigation Case", case)
            c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "Report",
                     "description": text[:1500], "operator": frappe.session.user})
            c.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "case_progress record")
    return {"ok": True, "done": done, "total": len(items), "pct": pct,
            "items": [{"label": l, "done": ok, "extra": e} for l, ok, e in items],
            "todo_external": [{"label": l, "done": ok} for l, ok in todo_ext], "text": text}


@frappe.whitelist()
def run_full_analysis(case, notify_user=None):
    """Lancia l'intera pipeline disponibile sul caso (idempotente). Background."""
    steps = []

    def _try(label, fn):
        try:
            fn()
            steps.append((label, True))
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"run_full_analysis {label}")
            steps.append((label, False))

    from thanatos_intel.integrations.company_screen import screen_case_parties
    from thanatos_intel.ai.cession_recon import detect_double_cession
    from thanatos_intel.ai.doc_questions import generate_questions
    from thanatos_intel.integrations.fatturapa import reconcile_invoices
    from thanatos_intel.reporting.fascicolo import genera_fascicolo

    _try("screening parti", lambda: screen_case_parties(case))
    _try("doppia cessione", lambda: detect_double_cession(case))
    _try("domande investigative", lambda: generate_questions(case, post=0))
    _try("riconciliazione fatture", lambda: reconcile_invoices(case))
    _try("fascicolo", lambda: genera_fascicolo(case))

    prog = case_progress(case, record=1)
    if notify_user:
        try:
            frappe.publish_realtime("msgprint", {
                "message": f"<b>Analisi completa caso {case}</b><br>Avanzamento: "
                           f"{prog['done']}/{prog['total']} ({prog['pct']}%)", "indicator": "green"},
                user=notify_user)
        except Exception:
            pass
    return {"ok": True, "steps": steps, "progress": prog}


@frappe.whitelist()
def document_walkthrough(case):
    """Dati per il percorso guidato documento-per-documento: sintesi, autenticità,
    hash, domande investigative (dall'ultima attività) e link, per ogni reperto."""
    import re
    has_q = frappe.db.has_column("Investigation Evidence", "investigative_questions")
    fields = ["evidence_name", "authenticity", "hash_value", "attached_file", "notes"]
    if has_q:
        fields.append("investigative_questions")
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=fields, order_by="creation asc", limit=0)
    qmap = {}
    rows = frappe.get_all("Case Activity",
                          filters={"parent": case, "description": ["like", "%DOMANDE INVESTIGATIVE%"]},
                          fields=["description"], order_by="activity_date desc", limit=1)
    if rows:
        for block in rows[0].description.split("\U0001F4C4 ")[1:]:
            lines = block.split("\n")
            fn = re.sub(r"\s*\[.*?\]\s*$", "", lines[0].replace("*", "")).strip().lower()
            qs = [l.strip() for l in lines[1:] if re.match(r"\s*\d+\.", l)]
            if fn:
                qmap[fn] = qs
    docs = []
    for i, e in enumerate(evs):
        fn = (e.attached_file or e.evidence_name or "").split("/files/")[-1]
        summ = ""
        for ln in (e.notes or "").split("\n"):
            ln = ln.strip()
            if ln and not ln.startswith(("—", "Autenticità", "Red flag", "Campi", "OCR provider")):
                summ = ln
                break
        ql = fn.lower()
        stored = (e.get("investigative_questions") or "") if has_q else ""
        if stored.strip():
            qs = [l.strip() for l in stored.split("\n") if l.strip()]
        else:
            qs = qmap.get(ql) or next((v for k, v in qmap.items() if k and (k in ql or ql in k)), [])
        docs.append({"idx": i + 1, "name": fn, "authenticity": e.authenticity or "N/D",
                     "hash": (e.hash_value or "")[:16], "file_url": e.attached_file or "",
                     "summary": summ[:700], "questions": qs[:8]})
    return {"total": len(docs), "docs": docs}


@frappe.whitelist()
def run_full_analysis_async(case):
    frappe.enqueue("thanatos_intel.ai.case_orchestrator.run_full_analysis", queue="long",
                   timeout=2400, case=case, notify_user=frappe.session.user)
    return {"queued": True}
