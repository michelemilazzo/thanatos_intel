"""
Quick Scan pubblico — Thanatos Intel.

Lead magnet: un visitatore anonimo inserisce un target e riceve SOLO un
semaforo di rischio (verde/giallo/arancio/rosso). Nessun dettaglio, nessuna
fonte, nessun punteggio numerico → per ottenere l'analisi deve registrarsi e
pagare.

Vincoli anti-abuso/costo:
- esegue SOLO fonti gratis+automatiche (free_auto, offline o API gratuite): mai
  le chiavi a pagamento del cliente su traffico anonimo;
- rate-limit per IP.
"""
import frappe

from thanatos_intel.osint import source_registry as sr
from thanatos_intel.thanatos_osint.doctype.osint_job.osint_job import _score_delta, _band

RATE_LIMIT = 8          # richieste
RATE_WINDOW = 3600      # per ora, per IP

VALID_TARGETS = {"Domain", "Url", "IP", "Company", "Person",
                 "Wallet", "Phone", "Username", "Email"}

SIGNAL = {  # band → semaforo
    "Low": {"signal": "green", "label": "Nessun segnale di rischio rilevato",
            "tone": "Le fonti pubbliche non evidenziano criticità immediate."},
    "Medium": {"signal": "yellow", "label": "Segnali da approfondire",
               "tone": "Emergono elementi che meritano una verifica approfondita."},
    "High": {"signal": "orange", "label": "Rischio elevato",
             "tone": "Le fonti indicano un profilo di rischio elevato."},
    "Critical": {"signal": "red", "label": "Rischio critico",
                 "tone": "Riscontri gravi nelle fonti pubbliche."},
}


def _rate_ok() -> bool:
    ip = getattr(frappe.local, "request_ip", None) or "?"
    key = f"qscan:rl:{ip}"
    c = frappe.cache().get_value(key)
    c = int(c) + 1 if c else 1
    frappe.cache().set_value(key, c, expires_in_sec=RATE_WINDOW)
    return c <= RATE_LIMIT


@frappe.whitelist(allow_guest=True)
def quick_signal(target_type: str, target_value: str) -> dict:
    """Ritorna SOLO il semaforo di rischio. Nessun dettaglio o fonte."""
    tt = (target_type or "").strip()
    val = (target_value or "").strip()
    if tt not in VALID_TARGETS:
        return {"error": "target_type non valido"}
    if not val or len(val) > 200:
        return {"error": "valore non valido"}
    if not _rate_ok():
        return {"error": "rate_limited",
                "message": "Troppe verifiche. Registrati per analisi illimitate."}

    # categoria generica del riscontro (NESSUNA fonte/dettaglio) → solo per invogliare
    HINT = {
        "opensanctions": "Possibili riscontri in liste sanzioni / PEP internazionali",
        "courtlistener": "Possibili procedimenti giudiziari collegati",
        "rdap": "Dominio di registrazione recente",
        "greynoise": "Segnalazioni di sicurezza sull'infrastruttura",
        "otx": "Segnalazioni di threat intelligence",
        "pulsedive": "Indicatori di rischio reputazionale",
        "abuseipdb": "Segnalazioni di abuso sull'IP",
        "virustotal": "Riscontri su motori di sicurezza",
    }

    score = 0
    ran = 0
    hints = []
    for s in sr.SOURCES:
        if tt not in s.get("targets", []):
            continue
        # SOLO fonti gratis+automatiche operative (nessun costo, nessuna key cliente)
        if s.get("tier") != "free_auto" or not sr._operational(s):
            continue
        try:
            fn = frappe.get_attr(s["connector"])
            res = fn(val)
            ran += 1
            name = {"opensanctions_local": "opensanctions"}.get(s["key"], s["key"])
            d, _ = _score_delta(name, res)
            score += d
            if d > 0 and name in HINT and HINT[name] not in hints:
                hints.append(HINT[name])
        except Exception:
            continue

    band = _band(max(0, min(100, score)))
    sig = SIGNAL.get(band, SIGNAL["Low"])
    return {
        "ok": True,
        "signal": sig["signal"],
        "label": sig["label"],
        "tone": sig["tone"],
        "checked": ran,
        "hints": hints[:3],
        "cta": "Registrati per il dossier completo, le fonti certificate e il valore legale.",
    }
