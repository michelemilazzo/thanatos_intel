"""Pagina pubblica /verifica-blacklist: ricerca gratuita nella blacklist Thanatos
+ ingresso al sistema di segnalazione (reward, modulo per le autorita, denuncia
allegabile dopo registrazione). La verifica approfondita resta nel portale."""
import frappe

no_cache = 1


def get_context(context):
    context.body_class = "bl-public"
    context.total_entries = frappe.db.count("Blacklist Entry", {"is_active": 1})
    context.bonus = frappe.db.get_single_value("Thanatos Billing Settings", "report_bonus_amount") or 2
    context.logged_in = frappe.session.user != "Guest"
    context.title = "Verifica Blacklist — Thanatos"
    context.lang = frappe.local.lang or "it"
    return context


def _norm(entry_type, value):
    value = (value or "").strip()
    if entry_type in ("Email", "Domain"):
        return value.lower()
    return value


@frappe.whitelist(allow_guest=True)
def public_check(entry_value, entry_type=None):
    """Verifica gratuita: l'indirizzo/valore e segnalato? Ritorna solo info minime
    (niente dati di caso o personali). Cap anti-abuso sulla lunghezza."""
    entry_value = (entry_value or "").strip()
    if not entry_value or len(entry_value) > 200:
        return {"ok": False, "error": "Inserisci un valore valido."}

    filters = {"is_active": 1}
    candidates = [entry_value]
    if "@" in entry_value or "." in entry_value:
        candidates.append(entry_value.lower())
    rows = frappe.get_all(
        "Blacklist Entry",
        filters={"is_active": 1, "entry_value": ["in", list(dict.fromkeys(candidates))]},
        fields=["entry_type", "risk_level", "source", "verified", "occurrences", "last_seen"],
        limit=5,
    )
    if not rows:
        return {"ok": True, "found": False, "value": entry_value}
    order = {"Critical": 3, "High": 2, "Medium": 1}
    rows.sort(key=lambda r: -order.get(r.risk_level, 0))
    top = rows[0]
    return {
        "ok": True, "found": True, "value": entry_value,
        "entry_type": top.entry_type, "risk_level": top.risk_level,
        "source": top.source, "verified": bool(top.verified),
        "occurrences": top.occurrences or 1, "matches": len(rows),
    }
