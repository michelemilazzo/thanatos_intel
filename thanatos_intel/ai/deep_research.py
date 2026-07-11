"""thanatos_intel/ai/deep_research.py — ricerca approfondita multi-fonte su
un nominativo: OSINT free-source interno (PEP/sanzioni/Wikidata/
CourtListener) + ricerca web live (Perplexity Sonar via OpenRouter, gia'
autorizzato per questo progetto). NON associa il soggetto a nessun caso
(nessuna evidence auto-creata) — l'operatore deve confermare esplicitamente
il collegamento prima che venga registrato come reperto."""
import frappe


def _web_research(name):
    """Ricerca web live via Perplexity Sonar (OpenRouter) — risposta con
    citazioni reali. Ritorna (testo, fonti) o ('', []) se non disponibile."""
    from thanatos_intel.ai.ops_brain import _vault
    import requests
    key = _vault("openrouter_key", "ai_engines")
    if not key:
        return "", []
    base_url = (_vault("openrouter_url", "ai_engines") or "https://openrouter.ai/api/v1").rstrip("/")
    prompt = (
        f"Fai una ricerca OSINT approfondita e fattuale su '{name}': chi è, "
        f"ruolo professionale/aziendale, eventuali notizie di rilievo "
        f"(positive o negative), controversie legali, sanzioni, fallimenti, "
        f"indagini, procedimenti giudiziari. Sii prudente e fattuale: se non "
        f"trovi riscontri affidabili per qualcosa, dillo esplicitamente "
        f"invece di inventare o supporre. Cita sempre le fonti."
    )
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "HTTP-Referer": "https://thanatos.agency",
                     "X-Title": "Thanatos Deep Research",
                     "Content-Type": "application/json"},
            json={"model": "perplexity/sonar-pro",
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        text = (msg.get("content") or "").strip()
        citations = d.get("citations") or msg.get("annotations") or []
        return text, citations
    except Exception:
        frappe.log_error(frappe.get_traceback(), "deep_research web")
        return "", []


@frappe.whitelist()
def web_search(query):
    """Ricerca web generica (qualsiasi argomento, non solo persone) via
    Perplexity Sonar — risposta fattuale con fonti reali. Ritorna un dict
    {"wa_message": ...} pronto per l'invio. NON allucina (a differenza della
    WebSearch nativa Claude, US-only, disattivata): Perplexity cerca davvero.
    Costo ~€0.005/ricerca. Usata dal linguaggio naturale del super admin."""
    from thanatos_intel.ai.ops_brain import _vault
    import requests
    key = _vault("openrouter_key", "ai_engines")
    if not key:
        return {"wa_message": "⚠️ Ricerca web non configurata (chiave OpenRouter mancante)."}
    base_url = (_vault("openrouter_url", "ai_engines") or "https://openrouter.ai/api/v1").rstrip("/")
    prompt = (
        f"Ricerca web fattuale su: «{query}». Rispondi in italiano con i "
        f"riscontri reali trovati online. REGOLA FERREA: se non trovi una "
        f"fonte affidabile per un'informazione, dillo esplicitamente invece "
        f"di inventare o supporre — questo serve a un'indagine, i dati falsi "
        f"sono peggio di nessun dato. Cita sempre le fonti (URL)."
    )
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "HTTP-Referer": "https://thanatos.agency",
                     "X-Title": "Thanatos Web Search",
                     "Content-Type": "application/json"},
            json={"model": "perplexity/sonar-pro",
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        text = (msg.get("content") or "").strip()
        citations = d.get("citations") or msg.get("annotations") or []
    except Exception:
        frappe.log_error(frappe.get_traceback(), "web_search")
        return {"wa_message": "⚠️ La ricerca web ha incontrato un errore. Riprova tra poco."}
    if not text:
        return {"wa_message": f"🔎 Nessun riscontro affidabile per «{query}»."}
    out = [f"🔎 *Ricerca web — {query}*", "", text[:2200]]
    urls = []
    for c in citations[:6]:
        u = c.get("url") if isinstance(c, dict) else c
        if u:
            urls.append(str(u))
    if urls:
        out.append("")
        out.append("_Fonti: " + "; ".join(urls) + "_")
    return {"wa_message": "\n".join(out)}


@frappe.whitelist()
def deep_person_research(case, name):
    """Ricerca multi-fonte su una persona: PEP/sanzioni (openapi.it),
    sanzioni offline (OpenSanctions), Wikidata, CourtListener, ricerca web
    live (Perplexity Sonar). NON collega la persona al caso — nessuna
    evidence viene auto-creata, l'operatore deve confermare esplicitamente.
    Pensata per essere lanciata in background (query esterne, puo' richiedere
    fino a ~40-60s); ritorna {"wa_message": ...} per _run_and_notify."""
    lines = [f"🔎 *Ricerca approfondita — {name}*",
             "_(fonti: PEP/sanzioni openapi.it, OpenSanctions, Wikidata, "
             "CourtListener, ricerca web)_", ""]

    # 1) screening_kyc (PEP/sanction_list/adverse_media insieme, mode=full)
    #    SENZA investigation_case: non deve creare evidence/associare al caso.
    try:
        from thanatos_intel.osint.openapi_client import screening_kyc
        r = screening_kyc(name, mode="full")
        if r.get("error"):
            lines.append(f"⚠️ PEP/Sanzioni/Adverse media: {r['error']}")
        else:
            hl = "; ".join(h["nome"] for h in (r.get("hits") or [])[:5]) or "nessun match"
            lines.append(f"*PEP/Sanzioni/Adverse media* (openapi.it): "
                         f"{r.get('match', 0)} match — {hl}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "deep_research screening_kyc")
        lines.append("⚠️ Screening PEP/sanzioni non disponibile")

    # 2) sanzioni offline (OpenSanctions locale — fonte diversa/ridondante)
    try:
        from thanatos_intel.osint import free_sources
        r2 = free_sources.screen_sanctions(name, schema="Person")
        lines.append(f"*Sanzioni offline (OpenSanctions)*: "
                     f"{'⚠️ MATCH' if r2.get('found') else 'nessun match'}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "deep_research sanctions")

    # 3) Wikidata — persona pubblica nota?
    try:
        r3 = free_sources.lookup_wikidata(name)
        if r3.get("found"):
            lines.append("*Wikidata*: profilo pubblico trovato")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "deep_research wikidata")

    # 4) CourtListener — procedimenti giudiziari federali USA
    try:
        r4 = free_sources.lookup_courtlistener(name)
        n = r4.get("count", 0) if r4.get("found") else 0
        lines.append(f"*Procedimenti giudiziari USA* (CourtListener): {n}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "deep_research courtlistener")

    # 5) ricerca web live (Perplexity Sonar via OpenRouter)
    web_text, citations = _web_research(name)
    lines.append("")
    if web_text:
        lines.append("*Ricerca web*:")
        lines.append(web_text[:1800])
        if citations:
            urls = []
            for c in citations[:6]:
                u = c.get("url") if isinstance(c, dict) else c
                if u:
                    urls.append(str(u))
            cs = "; ".join(urls)
            if cs:
                lines.append("")
                lines.append(f"_Fonti: {cs}_")
    else:
        lines.append("_Ricerca web non disponibile al momento (vedi log)._")

    lines.append("")
    lines.append(f"❓ *{name}* è collegato al caso *{case}*? Se sì, dimmelo "
                 f"e lo registro come reperto — non lo aggancio in automatico.")

    return {"wa_message": "\n".join(lines)}
