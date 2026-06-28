"""Assistente AI del caso (chat che ESEGUE gli strumenti) + valutazione assicurativa.

case_ai_chat(case, message): instrada il messaggio dell'operatore agli strumenti del
caso (doppia cessione, screening, domande, dossier, proforma, fascicolo, formulario,
verifica camerale, riconciliazione fatture, avanzamento, invio WhatsApp, valutazione
assicurativa) oppure risponde in modo conversazionale col contesto reale del caso.
L'idea: tutto ciò che oggi si chiede "a mano" avviene dentro il caso via chat AI.
"""
import re
import frappe
from frappe.utils import now_datetime


@frappe.whitelist()
def valuta_assicurazione(case):
    """Valuta i presupposti per richiesta di indennizzo assicurativo e li registra."""
    c = frappe.get_doc("Investigation Case", case)
    txt = (
        "🛡️ VALUTAZIONE INDENNIZZO ASSICURATIVO — presupposti e percorso\n"
        "VIE PERCORRIBILI:\n"
        "1. RC PROFESSIONALE DEGLI ASSEVERATORI (via principale). Fattorelli, Grube, (Conte) hanno "
        "rilasciato relazioni/visti di conformità che hanno indotto l'acquisto. Se negligenti o non "
        "veritiere → responsabilità professionale (artt. 1176, 2236 c.c.) e azione diretta/escussione "
        "delle loro polizze RC (Grube: DUAL, polizza PI-00K3322450, massimale dichiarato €7M; Fattorelli: "
        "da acquisire). PRESUPPOSTI: nesso causale asseverazione→danno; colpa del professionista; polizza "
        "attiva alla data del fatto (Grube 07/10/2024-07/10/2025); il danno (€800.000) provato.\n"
        "2. ESCROW / DEPOSITO NOTARILE. Il 'Verbale di Deposito' indica un conto dedicato notarile "
        "(IBAN IT30J0623001495000031671206, notai Bechini/Bastianutti): verificare se i fondi del cliente "
        "vi sono transitati → possibile recupero diretto/blocco presso il deposito.\n"
        "3. RC INTERMEDIARI/BROKER (es. T. Venosa) se iscritti con copertura.\n"
        "4. POLIZZE DEL CLIENTE (Trading HU): tutela legale, eventuali coperture su operazioni/crediti, D&O.\n"
        "ATTENZIONE (esclusioni): le polizze escludono di norma il DOLO/la frode → se cedente/intermediari "
        "hanno agito con dolo le LORO coperture potrebbero non operare; la RC dell'asseveratore per COLPA "
        "professionale invece può operare. Verificare il premio anomalo della polizza Grube (€220 per €7M) "
        "= possibile 'polizza di facciata' o esclusioni rilevanti per crediti fiscali.\n"
        "AZIONI: a) acquisire i TESTI INTEGRALI delle polizze RC (massimali, esclusioni, retroattività, "
        "claims-made); b) verificare IVASS/RUI delle compagnie (Arch Insurance EU DAC, DUAL Italia) e "
        "l'effettiva validità; c) costituire in mora gli asseveratori e DENUNCIARE IL SINISTRO alle loro "
        "compagnie nei termini; d) verificare il conto escrow notarile; e) quantificare il danno con i bonifici."
    )
    try:
        c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "Report",
                 "description": txt[:1800], "operator": frappe.session.user})
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "valuta_assicurazione")
    return {"ok": True, "text": txt}


# ── Router intent → strumento ───────────────────────────────────────────────
def _enq(method, **kw):
    frappe.enqueue(method, queue="long", timeout=2400, **kw)


@frappe.whitelist()
def case_ai_chat(case, message):
    """Chat operativa sul caso: esegue lo strumento richiesto o risponde col contesto."""
    t = (message or "").lower().strip()
    if not t:
        return {"reply": "Dimmi pure cosa vuoi fare sul caso."}

    def done(reply, action=None):
        return {"reply": reply, "action": action}

    # — strumenti che girano subito —
    if re.search(r"assicuraz|indennizz|polizz|rc ", t):
        valuta_assicurazione(case)
        return done("🛡️ Valutazione assicurativa generata e registrata nelle attività del caso "
                    "(RC asseveratori, escrow notarile, esclusioni, azioni).", "valuta_assicurazione")
    if re.search(r"avanzament|checklist|a che punt|cosa manca|cosa resta", t):
        from thanatos_intel.ai.case_orchestrator import case_progress
        p = case_progress(case)
        return done(f"📋 Avanzamento {p['done']}/{p['total']} ({p['pct']}%).\n" + p["text"], "case_progress")
    if re.search(r"dossier", t):
        from thanatos_intel.reporting.dossier_cliente import genera_dossier
        r = genera_dossier(case)
        return done(f"📄 Dossier cliente (DOCX) generato: {r.get('documenti')} documenti.", "dossier")
    if re.search(r"proforma|preventiv|onorari", t):
        from thanatos_intel.billing.proforma_cliente import genera_proforma
        r = genera_proforma(case)
        return done(f"💶 Proforma generata: imponibile € {r.get('imponibile'):,.0f}.", "proforma")
    if re.search(r"formulario|playbook", t):
        from thanatos_intel.reporting.formulario import genera_formulario
        genera_formulario(case)
        return done("📋 Formulario investigativo generato (domande+normativa+strategia).", "formulario")
    if re.search(r"fascicolo", t):
        _enq("thanatos_intel.reporting.fascicolo.genera_fascicolo", case=case)
        return done("📑 Genero il fascicolo integrale (in background).", "fascicolo")
    if re.search(r"doppia cession|riconcili.*cession", t):
        _enq("thanatos_intel.ai.cession_recon.detect_double_cession", case=case)
        return done("🔁 Rilevatore doppia cessione avviato (esito nelle attività).", "doppia_cessione")
    if re.search(r"domand", t):
        _enq("thanatos_intel.ai.doc_questions.generate_questions", case=case, post=0)
        return done("🕵️ Genero le domande investigative per ogni documento (in background).", "domande")
    if re.search(r"screening|sanzion|vies", t):
        _enq("thanatos_intel.integrations.company_screen.screen_case_parties", case=case)
        return done("🔎 Screening parti avviato (VIES/sanzioni).", "screening")
    if re.search(r"riconcil.*fattur|fattur.*xml|riconciliazione", t):
        _enq("thanatos_intel.integrations.fatturapa.reconcile_invoices", case=case)
        return done("🧾 Riconciliazione fatture avviata.", "riconciliazione")
    if re.search(r"analisi completa|analizza tutto|esegui tutto|pipeline", t):
        _enq("thanatos_intel.ai.case_orchestrator.run_full_analysis", case=case)
        return done("▶ Pipeline completa avviata (esito + checklist nelle attività).", "full")
    m = re.search(r"verifica\s+camerale.*?(\d{11})|p\.?\s*iva\s*(\d{11})|camerale.*?(\d{11})", t)
    if m or re.search(r"verifica camerale|visura", t):
        piva = next((g for g in (m.groups() if m else []) if g), None)
        if piva:
            from thanatos_intel.osint.registro_imprese import verifica_impresa
            r = verifica_impresa(piva, investigation_case=case)
            vies = (r.get("checks") or {}).get("vies", {})
            return done(f"🏛️ Verifica camerale P.IVA {piva}: checksum "
                        f"{'ok' if (r['checks']['piva_checksum'].get('valid')) else 'NON valido'}, "
                        f"VIES {vies.get('valid')}.", "verifica_camerale")
        return done("Indicami la P.IVA (11 cifre) da verificare, es. «verifica camerale 03293360966».")
    if re.search(r"invia.*whatsapp|manda.*relazion|relazione.*whatsapp", t):
        lead = frappe.db.get_value("Intel Lead", {"linked_case": case}, "name")
        if not lead:
            return done("Nessuna chat WhatsApp collegata al caso.")
        return done("Per inviare la relazione su WhatsApp usa il comando dalla chat operatore "
                    "o il bottone dedicato (evito invii doppi dalla chat del caso).")

    # — fallback conversazionale col contesto del caso —
    try:
        from thanatos_intel.ai.doc_ingest import _gateway
        from thanatos_intel.ai.case_architect import _resp_text
        from thanatos_intel.ingest.operator_console import _case_brief
        sys = ("Sei l'assistente investigativo interno di Thanatos sul caso. Rispondi all'operatore "
               "(dagli del tu, conciso, concreto) usando il contesto. Se l'operatore vuole eseguire "
               "un'azione, suggerisci il comando esatto (es. «genera dossier», «valuta assicurazione», "
               "«verifica camerale <piva>», «analisi completa»).")
        brief = _case_brief(case)
        resp = _gateway(f"Contesto:\n{brief}\n\nOperatore: «{message}»\n\nRispondi.",
                        system=sys, task_type="chat", session_id=f"case-{case}")
        out = (_resp_text(resp) or "").strip()
        return done(out or "Non ho capito; prova con un comando (dossier, proforma, doppia cessione, "
                    "domande, screening, verifica camerale <piva>, valuta assicurazione, avanzamento).")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case_ai_chat")
        return done("Comandi: dossier · proforma · formulario · fascicolo · doppia cessione · domande · "
                    "screening · riconciliazione fatture · verifica camerale <piva> · valuta assicurazione · "
                    "analisi completa · avanzamento.")
