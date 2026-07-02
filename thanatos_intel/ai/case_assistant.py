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


@frappe.whitelist()
def crea_mandato(case):
    """Crea l'Agency Mandate del caso (auto-compilato) se non esiste già."""
    ex = frappe.db.get_value("Agency Mandate", {"investigation_case": case}, "name")
    if ex:
        return {"ok": True, "mandate": ex, "existing": True}
    from thanatos_intel.thanatos_ddd.doctype.agency_mandate.agency_mandate import autofill_from_case
    af = autofill_from_case(case) or {}
    m = frappe.new_doc("Agency Mandate")
    m.investigation_case = case
    for k, v in af.items():
        try:
            m.set(k, v)
        except Exception:
            pass
    be = frappe.db.get_value("Billing Entity", {"legal_name": ["like", "%THANATOS%"]}, "name") \
        or frappe.db.get_value("Billing Entity", {}, "name")
    if be:
        m.billing_entity = be
    try:
        m.fee_total = 26000
        m.currency = "EUR"
    except Exception:
        pass
    m.status = "Draft"
    m.flags.ignore_mandatory = True
    m.insert(ignore_permissions=True)  # before_insert renderizza il corpo
    frappe.db.commit()
    return {"ok": True, "mandate": m.name}


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

    # — catalogo strumenti dati a disposizione —
    if re.search(r"che strumenti|quali strumenti|catalogo|strumenti.*disposiz|fonti dati|cosa puoi cercar|che dati puoi|che banche dati|elenco strument", t):
        from thanatos_intel.osint.openapi_client import strumenti
        s = strumenti()
        lines = [f"🧰 Strumenti dati a disposizione — {s['totale_servizi']} servizi · "
                 f"ambiente **{s['ambiente']}** · {'connesso' if s['connesso'] else 'NON connesso'}", ""]
        for f in s["famiglie"]:
            lines.append(f"**{f['famiglia']}** ({f['pattern']}, {f['fascia']}) — {f['uso']}")
            lines.append("   · " + ", ".join(f["strumenti"]))
        return done("\n".join(lines)[:1800], "strumenti")

    # — soci + titolari effettivi (UBO) —
    mp = re.search(r"(\d{11})", t)
    if re.search(r"\bsoci\b|titolari effettiv|\bubo\b|compagine|beneficiari effettiv|assetto proprietar|chi possiede|chi controlla", t):
        if mp:
            from thanatos_intel.osint.openapi_client import soci_titolari
            r = soci_titolari(mp.group(1), investigation_case=case)
            soci = "; ".join(f"{x['nome']} ({x['quota']}%)" for x in r.get("soci") or []) or "—"
            ubo = "; ".join(f"{x['nome']} [{x['cf']}]" for x in r.get("ubo") or []) or "—"
            return done(f"👥 P.IVA {mp.group(1)}\n**Soci:** {soci}\n**Titolari effettivi (UBO):** {ubo}", "soci_ubo")
        return done("Indicami la P.IVA (11 cifre), es. «soci e UBO 12485671007».")

    # — screening reputazionale KYC (PEP / sanzioni / adverse media) su un nominativo —
    mk = re.search(r"(?:pep|sanzion|adverse|reputaz|screening kyc|kyc)\s+(?:su |di |per )?(.+)", t)
    if re.search(r"\bpep\b|adverse media|reputazion|screening kyc|\bkyc\b", t):
        nome = (mk.group(1).strip() if mk else "").strip(" ?.")
        if nome and len(nome) > 2:
            mode = ("sanction_list" if "sanzion" in t else "adverse_media" if "adverse" in t
                    else "full" if "kyc" in t and "pep" not in t else "pep")
            from thanatos_intel.osint.openapi_client import screening_kyc
            r = screening_kyc(nome, mode=mode, investigation_case=case)
            if r.get("error"):
                return done(f"⚠️ Screening {mode}: {r['error']}")
            hl = "; ".join(h["nome"] for h in (r.get("hits") or [])[:8]) or "nessun match"
            return done(f"🛂 Screening **{mode}** «{nome}»: {r.get('match', 0)} match — {hl}", "kyc")
        return done("Indicami il nominativo, es. «screening PEP Mario Rossi» o «sanzioni Acme Ltd».")

    # — negatività (protesti / pregiudizievoli) —
    if re.search(r"negativit|protest|pregiudizievol|pignorament", t):
        cf = re.search(r"\b([A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z])\b", message or "")
        idv = (cf.group(1).upper() if cf else (mp.group(1) if mp else None))
        if idv:
            from thanatos_intel.osint.openapi_client import negativita
            r = negativita(idv, investigation_case=case)
            return done(f"⚖️ Negatività {idv}: {r.get('status')} — esito {r.get('esito')}", "negativita")
        return done("Indicami CF (persona) o P.IVA (impresa), es. «negatività RSSMRA80A01H501U».")

    # — patrimoniale persona (beni intestati) —
    if re.search(r"patrimonial|beni intestat|patrimonio di|cosa possiede", t):
        cf = re.search(r"\b([A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z])\b", message or "")
        nm = re.search(r"patrimonial[a-z]*\s+(?:di |su |per )?([A-Za-zÀ-ÿ']+)\s+([A-Za-zÀ-ÿ']+)", message or "", re.I)
        if cf and nm:
            from thanatos_intel.osint.openapi_client import patrimoniale
            r = patrimoniale(nm.group(1), nm.group(2), cf.group(1).upper(), investigation_case=case)
            return done(f"🏦 Patrimoniale {nm.group(1)} {nm.group(2)} [{cf.group(1).upper()}]: {r.get('status')}", "patrimoniale")
        return done("Servono nome, cognome e CF, es. «patrimoniale Mario Rossi RSSMRA80A01H501U».")

    # — strumenti che girano subito —
    if re.search(r"suggerisci.*serviz|che verifich|preventivo dati|quali dati|servizi.*dati|verifiche.*serv|cosa.*comprare|quali visure", t):
        from thanatos_intel.ai.data_services import preventivo_servizi
        r = preventivo_servizi(case)
        return done(r.get("text", "")[:1000], "preventivo_servizi")
    if re.search(r"cluster|censisci.*grupp|modello grupp|costruisci.*grupp|crea.*grupp", t):
        from thanatos_intel.ai.corporate_links import costruisci_cluster
        r = costruisci_cluster(case)
        return done(f"🕸️ Cluster «{r['gruppo']}» costruito/aggiornato: {r['membri']} membri, "
                    f"{r['links']} collegamenti. Aprilo dal doctype Corporate Group.", "cluster")
    if re.search(r"collegament|\bgruppo\b|soci.*comun|rete societ|holding|parti correlate|chi c'?è dietro", t):
        from thanatos_intel.ai.corporate_links import analizza_collegamenti
        r = analizza_collegamenti(case)
        return done("🕸️ Analisi collegamenti societari generata e registrata.\n" + (r.get("text") or "")[:900],
                    "collegamenti")
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
    # — download documento ufficiale PDF (visura camerale, bilancio ottico, certificato) —
    if re.search(r"scarica|documento ufficial|visura ufficial|visura in pdf|estratto camerale|bilancio ottico|\bcertificat", t):
        mpv = re.search(r"\b(\d{11})\b", message or "")
        if not mpv:
            return done("Indicami la P.IVA (11 cifre) del documento ufficiale da scaricare, es. "
                        "«scarica visura ufficiale 12485671007». Tipi: visura ordinaria/storica, "
                        "società di persone, impresa individuale, bilancio, certificato, certificato vigenza.")
        piva = mpv.group(1)
        storica = "storic" in t
        if "individual" in t or "ditta" in t:
            tipo = "storica_individuale" if storica else "ordinaria_individuale"
        elif "persone" in t:
            tipo = "storica_persone" if storica else "ordinaria_persone"
        elif "bilancio" in t:
            tipo = "bilancio"
        elif "certificat" in t:
            tipo = "certificato_vigenza" if "vigenz" in t else "certificato"
        else:
            tipo = "storica_capitale" if storica else "ordinaria_capitale"
        from thanatos_intel.osint.official_documents import richiedi_documento, TIPI
        r = richiedi_documento(case, tipo, piva)
        if r.get("error"):
            return done(f"⚠️ Documento ufficiale: {r['error']}")
        return done(f"📄 Richiesta avviata: {TIPI[tipo][1]} per P.IVA {piva}. "
                    "Il PDF arriverà nei reperti del caso tra qualche minuto.", "documento_ufficiale")

    # — verifica IBAN (validità, banca, titolare) —
    if re.search(r"\biban\b", t):
        mi = re.search(r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b", (message or "").replace(" ", "").upper())
        if mi:
            from thanatos_intel.osint.openapi_client import verifica_iban
            r = verifica_iban(mi.group(1), investigation_case=case)
            if r.get("error"):
                return done(f"⚠️ IBAN: {r['error']}")
            return done(f"🏦 IBAN {mi.group(1)}: valido {r.get('valido')} · banca {r.get('banca') or '—'} · "
                        f"BIC {r.get('bic') or '—'} · SEPA {r.get('sepa')}", "iban")
        return done("Indicami l'IBAN da verificare, es. «verifica IBAN IT60X0542811101000000123456».")

    # — verifica telefono (fraud score, operatore) —
    if re.search(r"verifica.*telefono|telefono.*verific|controlla.*numero|verifica.*numero|verifica.*cellular", t):
        mt = re.search(r"(\+?\d[\d\s]{7,17}\d)", message or "")
        if mt:
            from thanatos_intel.osint.openapi_client import verifica_telefono
            r = verifica_telefono(mt.group(1), investigation_case=case)
            if r.get("error"):
                return done(f"⚠️ Telefono: {r['error']}")
            return done(f"📞 {r.get('numero')}: fraud score {r.get('fraud_score')} · "
                        f"operatore {r.get('operatore') or '—'} · linea {r.get('tipo') or '—'}", "telefono")
        return done("Indicami il numero, es. «verifica telefono +393501234567».")

    # — verifica email (esistenza, fraud score) —
    if re.search(r"verifica.*mail|mail.*verific|controlla.*mail", t):
        me = re.search(r"([\w.+-]+@[\w-]+\.[\w.]+)", message or "")
        if me:
            from thanatos_intel.osint.openapi_client import verifica_email
            r = verifica_email(me.group(1), investigation_case=case)
            if r.get("error"):
                return done(f"⚠️ Email: {r['error']}")
            return done(f"✉️ {r.get('email')}: fraud score {r.get('fraud_score')} · "
                        f"recapitabile {r.get('esiste')} · usa-e-getta {r.get('disposable')}", "email")
        return done("Indicami l'email, es. «verifica email nome@dominio.com».")

    # — veicolo per targa (proprietario/assicurazione) —
    if re.search(r"\btarga\b|veicol|\bauto\b|automobil", t):
        mt = re.search(r"\b([A-Z]{2}\d{3}[A-Z]{2})\b", (message or "").replace(" ", "").upper())
        if mt:
            from thanatos_intel.osint.openapi_client import veicolo
            r = veicolo(mt.group(1), investigation_case=case)
            if r.get("error"):
                return done(f"⚠️ Veicolo: {r['error']}")
            return done(f"🚗 Veicolo targa {mt.group(1)}: dati acquisiti e registrati nei reperti.", "veicolo")
        return done("Indicami la targa (es. AB123CD), es. «veicolo targa AB123CD».")

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
    if re.search(r"\bmandat", t):
        r = crea_mandato(case)
        return done(("📜 Mandato già presente: " + r["mandate"]) if r.get("existing")
                    else f"📜 Mandato d'incarico creato e auto-compilato: {r['mandate']} (bozza, rivedi e genera PDF).",
                    "mandato")
    if re.search(r"invia.*whatsapp|manda.*relazion|relazione.*whatsapp|invia.*relazion", t):
        lead = frappe.db.get_value("Intel Lead", {"linked_case": case}, ["name", "whatsapp_number", "source_identifier"], as_dict=True)
        if not lead:
            return done("Nessuna chat WhatsApp collegata al caso.")
        from thanatos_intel.ingest.operator_console import send_case_report_wa
        res = send_case_report_wa(case, lead.name, lead.whatsapp_number, lead.source_identifier, include_pdf=1)
        return done(f"📲 Relazione inviata su WhatsApp: {res.get('messaggi')} messaggi + {res.get('documenti')} PDF.", "invia_wa")

    # — fallback conversazionale col contesto del caso —
    try:
        from thanatos_intel.ai.doc_ingest import _gateway
        from thanatos_intel.ai.case_architect import _resp_text
        from thanatos_intel.ingest.operator_console import _case_brief
        _cmds = _contextual_commands(case)
        sys = ("Sei l'assistente investigativo interno di Thanatos sul caso. Rispondi all'operatore "
               "(dagli del tu, conciso, concreto) usando il contesto. Se l'operatore vuole eseguire "
               "un'azione, suggerisci SOLO comandi pertinenti a questo caso, scelti tra: "
               + ", ".join("«%s»" % c for c in _cmds) + ".")
        brief = _case_brief(case)
        resp = _gateway(f"Contesto:\n{brief}\n\nOperatore: «{message}»\n\nRispondi.",
                        system=sys, task_type="chat", session_id=f"case-{case}")
        out = (_resp_text(resp) or "").strip()
        return done(out or ("Non ho capito; prova con un comando (" + ", ".join(_cmds) + ")."))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case_ai_chat")
        return done("Comandi: dossier · proforma · formulario · fascicolo · doppia cessione · domande · "
                    "screening · riconciliazione fatture · verifica camerale <piva> · valuta assicurazione · "
                    "analisi completa · avanzamento.")


def _contextual_commands(case):
    """Comandi suggeriti pertinenti al tipo di caso (allineati ai chip del cockpit)."""
    ct = frappe.db.get_value("Investigation Case", case, "case_type")
    common = ["avanzamento", "genera dossier", "proforma", "domande", "analisi completa"]
    extra = {
        "Fraud": ["screening", "doppia cessione", "scarica visura ufficiale <piva>", "verifica IBAN <iban>"],
        "Cyber": ["screening"],
        "Asset Recovery": ["screening", "doppia cessione", "verifica IBAN <iban>", "veicolo targa <targa>", "scarica visura ufficiale <piva>"],
        "Due Diligence": ["verifica camerale <piva>", "scarica visura ufficiale <piva>", "soci e UBO <piva>", "valuta assicurazione", "doppia cessione"],
        "Corporate": ["verifica camerale <piva>", "scarica visura ufficiale <piva>", "soci e UBO <piva>", "screening"],
        "Family": ["screening", "veicolo targa <targa>"],
    }
    out = []
    for c in common + extra.get(ct, ["screening", "verifica camerale <piva>"]):
        if c not in out:
            out.append(c)
    return out


_EV_TYPE = [
    ("audio", "Audio"), ("image", "Photo"), ("video", "Video"),
    ("pdf", "Document"), ("zip", "File"), ("text", "Document"),
]


@frappe.whitelist()
def chat_upload(case, file_url, file_name, content_type=""):
    """File caricato dalla chat del caso → reperto nel dossier (Investigation Evidence
    con attached_file). Il file è già allegato al caso da upload_file."""
    ct = (content_type or "").lower()
    name_l = (file_name or "").lower()
    etype = "Document"
    for key, t in _EV_TYPE:
        if key in ct or name_l.endswith("." + ("jpg" if key == "image" else key)):
            etype = t
            break
    if name_l.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        etype = "Photo"
    elif name_l.endswith((".mp3", ".wav", ".m4a", ".ogg", ".opus", ".aac")):
        etype = "Audio"
    elif name_l.endswith((".mp4", ".mov", ".avi", ".mkv")):
        etype = "Video"
    elif name_l.endswith((".zip", ".rar", ".7z")):
        etype = "File"
    ev = frappe.get_doc({
        "doctype": "Investigation Evidence", "investigation_case": case,
        "evidence_name": file_name[:140], "evidence_type": etype, "source": "Chat caso",
        "attached_file": file_url, "acquisition_date": now_datetime(),
        "custody_status": "Received", "notes": f"Caricato dalla chat del caso: {file_name}"})
    ev.flags.ignore_mandatory = True
    ev.insert(ignore_permissions=True)
    try:
        c = frappe.get_doc("Investigation Case", case)
        c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "Document",
                 "description": f"📎 File nel dossier: {file_name} (reperto {ev.name}, tipo {etype})"[:500],
                 "operator": frappe.session.user})
        c.flags.ignore_mandatory = True
        c.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "chat_upload activity")
    frappe.db.commit()
    return {"evidence": ev.name, "type": etype, "transcribing": False}
