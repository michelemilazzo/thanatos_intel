"""Tracking Target — fugitive / target tracking (modello Europol Trackathon).

Aggrega arricchimento OSINT dalle fonti free esistenti e suggerimenti AI sui
prossimi passi. Ogni Target può agganciare un Investigation Case e raccogliere
Tracking Lead durante una Trackathon Session.
"""
import json

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

_SCHEMA = {
    "Person": "Person",
    "Organization": "Organization",
    "Vessel": "Vessel",
    "Aircraft": "Airplane",
    "Asset": "Thing",
}


class TrackingTarget(Document):
    def after_insert(self):
        if self.target_name and not self.flags.get("skip_enrich"):
            frappe.enqueue(
                "thanatos_intel.thanatos_tracking.doctype.tracking_target.tracking_target._enrich_async",
                queue="short", target=self.name,
            )

    def refresh_lead_count(self):
        self.db_set("lead_count", frappe.db.count("Tracking Lead", {"target": self.name}))


def _enrich_async(target):
    try:
        doc = frappe.get_doc("Tracking Target", target)
        doc.enrich()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "tracking_target enrich")


@frappe.whitelist()
def enrich(target=None):
    """Esegue lo screening sanzioni/wanted sul target e aggrega il risultato."""
    doc = frappe.get_doc("Tracking Target", target) if isinstance(target, str) else target
    from thanatos_intel.osint import free_sources as fs

    schema = _SCHEMA.get(doc.target_type or "Person", "Person")
    agg = {}
    risk = 0
    summary_bits = []

    try:
        sanc = fs.screen_sanctions(doc.target_name, schema=schema) or {}
        agg["sanctions"] = sanc
        results = sanc.get("results") or sanc.get("matches") or []
        if results:
            risk = max(risk, 80)
            summary_bits.append(f"{len(results)} match liste sanzioni/wanted")
        elif not sanc.get("error"):
            summary_bits.append("nessun match liste sanzioni")
    except Exception:
        agg["sanctions"] = {"error": "lookup_failed"}

    # Wayback presence per alias/nome (footprint storico)
    try:
        wb = getattr(fs, "wayback_snapshots", None)
        if callable(wb) and doc.source_url:
            agg["wayback"] = wb(doc.source_url)
    except Exception:
        pass

    if doc.priority == "Critical":
        risk = max(risk, 70)

    doc.db_set("aggregated_json", json.dumps(agg, ensure_ascii=False, indent=2))
    doc.db_set("risk_score", risk)
    doc.db_set("osint_summary", "; ".join(summary_bits)[:280] or "Nessun dato OSINT rilevante")
    doc.db_set("last_enriched", now_datetime())
    return {"risk_score": risk, "summary": doc.osint_summary}


@frappe.whitelist()
def translate_record(target=None, lang="it"):
    """Traduce la descrizione (e i campi testuali) del target via libretranslate."""
    import requests
    doc = frappe.get_doc("Tracking Target", target)
    text = doc.description or ""
    if not text.strip():
        return {"ok": False, "reason": "nessuna descrizione da tradurre"}
    base = (frappe.conf.get("libretranslate_url") or "http://10.10.0.4:5000").rstrip("/")
    try:
        r = requests.post(base + "/translate", timeout=30, json={
            "q": text, "source": "auto", "target": lang, "format": "html",
        })
        if not r.ok:
            return {"ok": False, "reason": f"libretranslate HTTP {r.status_code}"}
        out = (r.json() or {}).get("translatedText")
        if not out:
            return {"ok": False, "reason": "traduzione vuota"}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "translate_record")
        return {"ok": False, "reason": "errore libretranslate"}
    doc.db_set("description_it", out)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def ai_suggest(target=None):
    """Chiede all'AI i prossimi passi investigativi sul target."""
    doc = frappe.get_doc("Tracking Target", target)
    leads = frappe.get_all(
        "Tracking Lead", filters={"target": doc.name},
        fields=["lead_type", "summary", "confidence", "status"], limit=30,
    )
    ctx = {
        "name": doc.target_name, "type": doc.target_type,
        "aliases": doc.aliases, "nationality": doc.nationality,
        "last_known_location": doc.last_known_location,
        "wanted_for": doc.wanted_for, "status": doc.status,
        "osint_summary": doc.osint_summary,
        "leads": leads,
    }
    system = (
        "Sei un analista OSINT di Thanatos Intel specializzato nella ricerca di "
        "latitanti e target. Proponi 3-5 prossimi passi investigativi concreti e "
        "legali (fonti aperte da consultare, query, incroci). Sii sintetico, in italiano. "
        "Restituisci un elenco puntato, niente preamboli."
    )
    msg = "Target e lead raccolti:\n" + json.dumps(ctx, ensure_ascii=False)

    out = None
    try:
        from thanatos_intel.ai.doc_ingest import _gateway
        resp = _gateway(msg, system=system, task_type="analysis")
        if resp:
            out = resp.get("reply") or resp.get("message") or resp.get("content")
    except Exception:
        out = None
    if not out:
        try:
            from thanatos_intel.ai.providers import _try_ollama
            txt, _ = _try_ollama(msg, system)
            out = txt
        except Exception:
            out = None

    out = (out or "AI non disponibile (gateway/ollama offline).").strip()
    doc.db_set("ai_suggestions", out[:2000])
    return {"suggestions": out}
