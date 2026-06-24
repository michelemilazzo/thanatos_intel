"""Stato sistema per la desk page thanatos-settings (solo System Manager)."""
import frappe


def _guard():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Solo un amministratore.", frappe.PermissionError)


@frappe.whitelist()
def system_status():
    _guard()
    conf = frappe.get_site_config()
    st = {}

    # Cloudflare Web Analytics
    st["cloudflare"] = {
        "ok": bool(conf.get("cloudflare_api_key") and conf.get("cf_rum_site_tag")),
        "detail": conf.get("cf_rum_site_tag") and "RUM site attivo" or "non configurato",
    }
    # Google Search Console
    try:
        from thanatos_intel import gsc
        g = gsc.gsc_status()
        st["gsc"] = {"ok": bool(g.get("connected")), "detail": g.get("property") or "—"}
    except Exception:
        st["gsc"] = {"ok": False, "detail": "errore"}
    # Stripe (via Thanatos Billing Settings o site_config)
    st["stripe"] = {
        "ok": bool(conf.get("stripe_secret_key") or conf.get("stripe_publishable_key")),
        "detail": "chiavi presenti" if conf.get("stripe_secret_key") else "—",
    }
    # Mail (Email Account in uscita)
    out = frappe.get_all("Email Account", filters={"enable_outgoing": 1}, fields=["name"], limit=1)
    st["mail"] = {"ok": bool(out), "detail": (out[0].name if out else "nessun account in uscita")}
    # utenti
    st["users"] = {
        "staff": frappe.db.count("User", {"user_type": "System User", "enabled": 1}),
        "portal": frappe.db.count("User", {"user_type": "Website User", "enabled": 1}),
    }
    return st
