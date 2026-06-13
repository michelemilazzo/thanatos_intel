"""Asset Cloud — valore del sito come asset vendibile + statistiche (per il portale).

Dati reali da Web Page View (traffico, visitatori unici, paese ricavato dal
time_zone del browser). Valore stimato da traffico + anzianita' (parametri
regolabili). Keyword/posizioni SEO: Fase 2 (Google Search Console).
"""
import frappe
from frappe import _
from frappe.utils import flt

# parametri valutazione (regolabili)
VALUE_PER_ANNUAL_VISIT = 0.5     # EUR per visita annua (proxy ricavo)
VALUE_PER_AGE_MONTH = 10.0       # bonus anzianita' EUR/mese
VALUE_FLOOR = 200.0              # valore minimo di un sito attivo

# time_zone -> (paese, iso) per i fusi piu' comuni
_TZ_COUNTRY = {
    "Europe/Rome": ("Italia", "IT"), "Europe/Vatican": ("Italia", "IT"),
    "Europe/Paris": ("Francia", "FR"), "Europe/Berlin": ("Germania", "DE"),
    "Europe/Madrid": ("Spagna", "ES"), "Europe/Zurich": ("Svizzera", "CH"),
    "Europe/London": ("Regno Unito", "GB"), "Europe/Amsterdam": ("Paesi Bassi", "NL"),
    "Europe/Brussels": ("Belgio", "BE"), "Europe/Lisbon": ("Portogallo", "PT"),
    "Europe/Vienna": ("Austria", "AT"), "Europe/Bucharest": ("Romania", "RO"),
    "Europe/Warsaw": ("Polonia", "PL"), "Europe/Athens": ("Grecia", "GR"),
    "Europe/Dublin": ("Irlanda", "IE"), "Europe/Stockholm": ("Svezia", "SE"),
    "America/New_York": ("Stati Uniti", "US"), "America/Chicago": ("Stati Uniti", "US"),
    "America/Los_Angeles": ("Stati Uniti", "US"), "America/Denver": ("Stati Uniti", "US"),
    "America/Sao_Paulo": ("Brasile", "BR"), "America/Toronto": ("Canada", "CA"),
    "Asia/Dubai": ("Emirati", "AE"), "Asia/Shanghai": ("Cina", "CN"),
    "Asia/Tokyo": ("Giappone", "JP"), "Asia/Kolkata": ("India", "IN"),
    "Australia/Sydney": ("Australia", "AU"),
}


def _country(tz):
    if not tz or tz in ("UTC", "Etc/Unknown", "Etc/UTC"):
        return ("Altri", "")
    if tz in _TZ_COUNTRY:
        return _TZ_COUNTRY[tz]
    # fallback: macro-regione dal prefisso
    region = (tz.split("/")[0] if "/" in tz else tz)
    return ({"Europe": "Europa", "America": "Americhe", "Asia": "Asia",
             "Africa": "Africa", "Australia": "Oceania"}.get(region, "Altri"), "")


def stats(days=30):
    tot = frappe.db.count("Web Page View")
    visits = frappe.db.sql(
        "select count(*) from `tabWeb Page View` where creation >= now() - interval %s day", (days,))[0][0]
    uniq = frappe.db.sql(
        "select count(distinct visitor_id) from `tabWeb Page View` "
        "where ifnull(visitor_id,'')!='' and creation >= now() - interval %s day", (days,))[0][0]
    online_since = frappe.db.sql("select min(creation) from `tabWeb Page View`")[0][0]

    # paesi da time_zone
    rows = frappe.db.sql(
        "select time_zone, count(*) c from `tabWeb Page View` "
        "where creation >= now() - interval %s day group by time_zone", (days,))
    agg = {}
    total_geo = 0
    for tz, c in rows:
        name = _country(tz)[0]
        agg[name] = agg.get(name, 0) + c
        total_geo += c
    countries = sorted(
        [{"country": k, "visits": v, "pct": round(v * 100.0 / total_geo) if total_geo else 0}
         for k, v in agg.items()], key=lambda x: -x["visits"])[:7]

    # pagine piu' viste
    top = frappe.db.sql(
        "select path, count(*) c from `tabWeb Page View` "
        "where creation >= now() - interval %s day and path not like '/api%%' "
        "group by path order by c desc limit 5", (days,), as_dict=True)

    return frappe._dict(visits_month=visits, unique_visitors=uniq, total_views=tot,
                        online_since=online_since, countries=countries, top_pages=top)


def valuation(s=None):
    s = s or stats()
    monthly = s.visits_month or 0
    annual = monthly * 12
    age_months = 1
    if s.online_since:
        import datetime
        days = (frappe.utils.now_datetime() - frappe.utils.get_datetime(s.online_since)).days
        age_months = max(1, round(days / 30.0))
    raw = annual * VALUE_PER_ANNUAL_VISIT + age_months * VALUE_PER_AGE_MONTH
    value = max(VALUE_FLOOR, raw)
    value = round(value / 10.0) * 10  # arrotonda a 10
    return frappe._dict(value=value, currency="EUR", monthly_visits=monthly,
                        annual_visits=annual, age_months=age_months)


def card_data(host=None):
    s = stats()
    v = valuation(s)
    host = host or (frappe.local.request.host if getattr(frappe.local, "request", None) else "") or "il tuo sito"
    return frappe._dict(host=host, value=v.value, currency=v.currency,
                        monthly_visits=s.visits_month, unique_visitors=s.unique_visitors,
                        countries=s.countries, top_pages=s.top_pages,
                        online_since=s.online_since,
                        keywords_ready=False)  # Fase 2: Search Console


# ---------------- form: vendi asset / upsell SEO ----------------
def _client():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login richiesto"), frappe.PermissionError)
    return frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")


def _notify(subject, body):
    try:
        frappe.sendmail(recipients=["admin@onekeyco.com"], subject=subject, message=body)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "asset notify")


@frappe.whitelist(methods=["POST"])
def submit_sale(asset_type, desired_price=None, notes=None):
    """Il cliente vuole vendere dominio/sito/progetto/app."""
    client = _client()
    host = frappe.local.request.host if getattr(frappe.local, "request", None) else ""
    user = frappe.session.user
    body = ("Richiesta di VENDITA asset dal portale.\n\n"
            "Cliente: %s (%s)\nSito: %s\nTipo: %s\nPrezzo desiderato: %s\nNote: %s\n"
            % (client or "-", user, host, asset_type, desired_price or "-", notes or "-"))
    _notify("[Asset Cloud] Richiesta vendita — %s" % (host or user), body)
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def request_seo():
    """Il cliente vuole il servizio di ranking SEO."""
    client = _client()
    user = frappe.session.user
    host = frappe.local.request.host if getattr(frappe.local, "request", None) else ""
    _notify("[Asset Cloud] Richiesta servizio ranking SEO — %s" % (host or user),
            "Cliente %s (%s) ha richiesto il servizio di ranking SEO per %s." % (client or "-", user, host))
    return {"ok": True}
