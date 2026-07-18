# -*- coding: utf-8 -*-
"""Raccolta e revisione qualità delle conversazioni WhatsApp del bot.

Le chat sono già persistite (Intel Lead + child Intel Lead Message). Qui le si
legge, si valutano SOLO i messaggi del BOT (outbound sent_by=Administrator) con
un revisore AI (modello economico free → costo 0) e si produce un
`Conversation Review` con problemi puntuali + suggerimenti. Serve a rendere il
bot più umano e funzionale in modo guidato dai dati, non a intuito.
"""

import json
import re

import frappe
from frappe.utils import now_datetime, add_to_date, get_datetime

BOT_USER = "Administrator"

_TYPES = {
    "Tono robotico", "Domanda ignorata", "Errore/confabulazione", "Handoff mancato",
    "Occasione servizio persa", "Azione fallita", "Lingua sbagliata", "Risposta lenta", "Altro",
}

_SYS = """Sei un revisore qualità del bot WhatsApp di un'agenzia investigativa (Thanatos).
Leggi la conversazione e valuti SOLO i messaggi marcati [BOT]. NON valutare i messaggi
[CLIENTE] né quelli [OP ...] (operatori umani): quelli sono contesto.
Obiettivo: rendere il bot più UMANO, CHIARO e UTILE. Sii severo ma onesto: segnala solo
problemi REALI, non inventarli. Se il bot ha gestito bene, restituisci issues vuota e score alto.

Problemi da cercare nei messaggi [BOT]:
- Tono robotico: freddo, burocratico, ripetitivo, troppo lungo o troppo tecnico.
- Domanda ignorata: il cliente chiede qualcosa e il bot non risponde o risponde a lato.
- Errore/confabulazione: afferma cose false, inventa esiti ("fatto", "risolto") non veri, si contraddice.
- Handoff mancato: serviva un umano (richiesta delicata/complessa/cliente arrabbiato) e il bot non ha passato la mano.
- Occasione servizio persa: il cliente aveva un bisogno vendibile e il bot non ha proposto il servizio né un link di pagamento.
- Azione fallita: dice di aver fatto un'azione (visura, screening, invio) ma è andata in errore / nessun esito.
- Lingua sbagliata: risponde in lingua diversa da quella del cliente.

Restituisci SOLO JSON valido, nient'altro:
{"humanness_score": <intero 1-5, 5=molto umano>,
 "handled_by": "Bot|Operatore|Misto",
 "summary": "<max 200 caratteri in italiano>",
 "issues": [{"issue_type":"<una etichetta esatta tra quelle sopra>",
             "severity":"Bassa|Media|Alta",
             "quote":"<il messaggio [BOT] problematico, max 160 caratteri>",
             "suggestion":"<come avrebbe dovuto rispondere, max 200 caratteri>"}]}
Massimo 5 issue, le più importanti."""


def _label(user):
    if not user or user == BOT_USER:
        return "BOT"
    fn = frappe.db.get_value("User", user, "full_name") or user
    return f"OP {fn}"


def _transcript(lead_doc, max_msgs=60):
    rows = sorted(lead_doc.messages, key=lambda m: str(m.sent_at or lead_doc.received_at or ""))
    rows = rows[-max_msgs:]
    out, bot_n = [], 0
    for m in rows:
        c = (m.content or "").strip().replace("\n", " ")
        if not c:
            c = "[media]" if m.media_url else "[vuoto]"
        if m.direction == "Inbound":
            who = "CLIENTE"
        else:
            who = _label(m.sent_by)
            if who == "BOT":
                bot_n += 1
        ts = get_datetime(m.sent_at).strftime("%d/%m %H:%M") if m.sent_at else ""
        out.append(f"[{who} {ts}] {c[:400]}")
    return "\n".join(out), len(rows), bot_n


def _parse_json(txt):
    if not txt:
        return None
    m = re.search(r"\{.*\}", txt.strip(), re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _clamp(v, lo, hi, dflt):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return dflt


@frappe.whitelist()
def review_conversation(lead_name, force=0):
    """Revisiona una singola conversazione; idempotente sul progresso (window_to)."""
    force = frappe.utils.cint(force)
    lead = frappe.get_doc("Intel Lead", lead_name)
    if (lead.source_type or "") != "WhatsApp":
        return {"skip": "non WhatsApp"}
    if not lead.messages:
        return {"skip": "nessun messaggio"}
    last_ts = max((m.sent_at for m in lead.messages if m.sent_at),
                  default=lead.received_at)
    if not force:
        prev = frappe.db.get_value("Conversation Review", {"lead": lead_name},
                                   "window_to", order_by="reviewed_at desc")
        if prev and last_ts and get_datetime(prev) >= get_datetime(last_ts):
            return {"skip": "già revisionata"}
    convo, n, bot_n = _transcript(lead)
    if bot_n == 0:
        return {"skip": "nessun messaggio bot"}
    from thanatos_intel.ai.ops_brain import _cheap_chat
    txt, _usage = _cheap_chat(_SYS, convo)
    data = _parse_json(txt)
    if data is None:
        return {"error": "revisore non ha prodotto JSON", "raw": (txt or "")[:200]}
    hb = data.get("handled_by")
    doc = frappe.get_doc({
        "doctype": "Conversation Review",
        "lead": lead_name,
        "contact": lead.source_name or lead.source_identifier or lead_name,
        "phone": lead.source_identifier or "",
        "reviewed_at": now_datetime(),
        "window_to": last_ts,
        "msg_count": n,
        "bot_msg_count": bot_n,
        "handled_by": hb if hb in ("Bot", "Operatore", "Misto") else "Bot",
        "humanness_score": _clamp(data.get("humanness_score"), 1, 5, 3),
        "summary": (data.get("summary") or "")[:200],
        "reviewer": "AI",
        "resolution": "Nuovo",
    })
    for it in (data.get("issues") or [])[:5]:
        typ = it.get("issue_type") or "Altro"
        if typ not in _TYPES:
            typ = "Altro"
        sev = it.get("severity") if it.get("severity") in ("Bassa", "Media", "Alta") else "Media"
        doc.append("issues", {
            "issue_type": typ, "severity": sev,
            "quote": (it.get("quote") or "")[:200],
            "suggestion": (it.get("suggestion") or "")[:300],
        })
    doc.issue_count = len(doc.issues)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "review": doc.name, "score": doc.humanness_score,
            "issues": doc.issue_count}


@frappe.whitelist()
def run_review_batch(hours=48, limit=40):
    """Revisiona le conversazioni WhatsApp con messaggi recenti. Costo 0 (modello free)."""
    hours = frappe.utils.cint(hours) or 48
    limit = frappe.utils.cint(limit) or 40
    since = add_to_date(now_datetime(), hours=-hours)
    leads = frappe.get_all(
        "Intel Lead",
        filters={"source_type": "WhatsApp", "last_message_at": [">=", since]},
        fields=["name"], order_by="last_message_at desc", limit=limit)
    done, skipped, err = 0, 0, 0
    for l in leads:
        try:
            r = review_conversation(l.name)
            if r.get("ok"):
                done += 1
            else:
                skipped += 1
        except Exception:
            err += 1
            frappe.log_error(frappe.get_traceback(), "conversation_review batch")
    return {"leads": len(leads), "reviewed": done, "skipped": skipped, "errors": err}


@frappe.whitelist()
def review_rollup(days=7):
    """Aggrega i problemi ricorrenti: cosa sistemare nel bot, in ordine di frequenza."""
    days = frappe.utils.cint(days) or 7
    since = add_to_date(now_datetime(), days=-days)
    reviews = frappe.get_all("Conversation Review",
                             filters={"reviewed_at": [">=", since]},
                             fields=["humanness_score"])
    n = len(reviews)
    avg = round(sum((r.humanness_score or 0) for r in reviews) / n, 2) if n else 0
    types = frappe.db.sql("""
        select i.issue_type, count(*) c
        from `tabConversation Review Issue` i
        join `tabConversation Review` r on r.name = i.parent
        where r.reviewed_at >= %s
        group by i.issue_type order by c desc""", (since,), as_dict=True)
    return {"giorni": days, "conversazioni": n, "punteggio_medio": avg,
            "problemi_totali": sum(t.c for t in types),
            "per_tipo": [{"tipo": t.issue_type, "n": t.c} for t in types]}


def daily_digest():
    """Job giornaliero: revisiona le conversazioni recenti (costo 0) e, se abilitato
    (`conversation_review_digest` in site_config), manda un digest al super admin."""
    res = run_review_batch(hours=30, limit=60)
    roll = review_rollup(days=1)
    if not frappe.conf.get("conversation_review_digest") or roll["conversazioni"] == 0:
        return {"batch": res, "rollup": roll}
    top = ", ".join(f"{t['tipo']} ×{t['n']}" for t in roll["per_tipo"][:4]) or "nessun problema"
    msg = ("🩺 Qualità bot (24h): {c} conversazioni riviste, punteggio medio "
           "{a}/5, {p} problemi.\nTop: {t}\nDettaglio: /app/conversation-review").format(
        c=roll["conversazioni"], a=roll["punteggio_medio"], p=roll["problemi_totali"], t=top)
    try:
        from thanatos_intel.ingest.wa_bot import notify_operators
        notify_operators(msg)
    except Exception:
        pass
    return {"batch": res, "rollup": roll, "digest": "sent"}
