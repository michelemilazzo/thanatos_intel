"""Client Facebook Graph API per la pagina Thanatos.

Gestisce la pubblicazione di contenuti (testo, link, foto) sulla Pagina
Facebook e la lettura degli Insights. Stesso pattern di `waba_notifications`:
zero-config -> no-op, così l'app non si rompe se le credenziali non sono
impostate.

Configurazione (in ordine di priorità):
  1. DocType singolo "Facebook Settings" (UI in /app/facebook-settings)
  2. site_config.json:
        "facebook_enabled": 1,
        "facebook_page_id": "...",       # ID numerico della Pagina
        "facebook_page_token": "...",    # Page Access Token long-lived
        "facebook_api_version": "v19.0"  # opzionale

Per ottenere un Page Access Token long-lived:
  - Crea un'app su developers.facebook.com con prodotto "Facebook Login"
  - Permessi: pages_manage_posts, pages_read_engagement, pages_read_user_content,
    read_insights, business_management
  - Genera un User Token, scambialo per uno long-lived, poi richiedi
    /me/accounts per ottenere il Page Access Token della Pagina Thanatos.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_datetime, now_datetime

GRAPH_HOST = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v19.0"

# Timeout di rete generoso: upload foto può essere lento.
_TIMEOUT = 30


class FacebookNotConfigured(Exception):
    """Sollevata quando mancano page id / token e l'integrazione è disattiva."""


def get_settings() -> dict:
    """Restituisce la config effettiva unendo DocType singolo e site_config.

    Il DocType singolo, se presente e valorizzato, ha la precedenza sui valori
    in site_config.json. Non solleva mai: in assenza di tabella restituisce i
    soli valori di site_config.
    """
    conf = frappe.conf
    data = {
        "enabled": bool(conf.get("facebook_enabled")),
        "page_id": conf.get("facebook_page_id") or "",
        "page_token": conf.get("facebook_page_token") or "",
        "api_version": conf.get("facebook_api_version") or DEFAULT_API_VERSION,
    }
    try:
        if frappe.db.exists("DocType", "Facebook Settings"):
            s = frappe.get_single("Facebook Settings")
            if s.get("enabled"):
                data["enabled"] = True
            if s.get("page_id"):
                data["page_id"] = s.page_id
            token = s.get_password("page_token", raise_exception=False) if hasattr(s, "get_password") else None
            if token:
                data["page_token"] = token
            if s.get("api_version"):
                data["api_version"] = s.api_version
    except Exception:
        # Migrazione non ancora eseguita o tabella assente: usa solo site_config.
        pass
    return data


def is_enabled() -> bool:
    s = get_settings()
    return bool(s["enabled"] and s["page_id"] and s["page_token"])


def _require_config() -> dict:
    s = get_settings()
    if not (s["page_id"] and s["page_token"]):
        raise FacebookNotConfigured(
            "Facebook non configurato: imposta page_id e page_token in "
            "Facebook Settings o in site_config.json."
        )
    return s


def _base_url(settings: dict) -> str:
    return f"{GRAPH_HOST}/{settings['api_version']}"


def _graph_request(method: str, path: str, settings: dict, **kwargs) -> dict:
    """Wrapper HTTP verso Graph API. Inietta l'access_token e alza su errore.

    `path` è relativo alla versione API, es. "/{page_id}/feed".
    """
    import requests

    url = f"{_base_url(settings)}{path}"
    params = kwargs.pop("params", {}) or {}
    data = kwargs.pop("data", None)
    files = kwargs.pop("files", None)

    # access_token va nei params per GET, nel body per POST.
    token = settings["page_token"]
    if method.upper() == "GET":
        params.setdefault("access_token", token)
    else:
        if data is None:
            data = {}
        data.setdefault("access_token", token)

    resp = requests.request(
        method, url, params=params, data=data, files=files, timeout=_TIMEOUT
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"raw": resp.text}

    if not resp.ok:
        err = payload.get("error", {}) if isinstance(payload, dict) else {}
        msg = err.get("message", resp.text)
        frappe.log_error(
            f"{method} {url}\nstatus={resp.status_code}\n{resp.text}",
            "facebook_graph error",
        )
        raise frappe.ValidationError(f"Facebook Graph API: {msg}")

    return payload if isinstance(payload, dict) else {"data": payload}


# ---------------------------------------------------------------------------
# Pubblicazione
# ---------------------------------------------------------------------------

def publish_text(message: str, link: str | None = None,
                 scheduled_time=None) -> dict:
    """Pubblica un post di testo (con link opzionale) sulla Pagina.

    Se `scheduled_time` è indicato e futuro di almeno 10 minuti, usa la
    programmazione nativa di Facebook; altrimenti pubblica subito.
    Restituisce {"id": "<post_id>"} (o {"id"} unito a scheduling info).
    """
    s = _require_config()
    data: dict = {"message": message or ""}
    if link:
        data["link"] = link

    _apply_schedule(data, scheduled_time)
    return _graph_request("POST", f"/{s['page_id']}/feed", s, data=data)


def publish_photo(image_url: str | None = None, image_bytes: bytes | None = None,
                  caption: str = "", scheduled_time=None) -> dict:
    """Pubblica una foto sulla Pagina.

    Accetta un URL pubblico (`image_url`) oppure i byte del file
    (`image_bytes`). La caption diventa il testo del post.
    """
    s = _require_config()
    data: dict = {"caption": caption or ""}
    _apply_schedule(data, scheduled_time)

    if image_url:
        data["url"] = image_url
        return _graph_request("POST", f"/{s['page_id']}/photos", s, data=data)
    if image_bytes:
        files = {"source": ("image", image_bytes)}
        return _graph_request(
            "POST", f"/{s['page_id']}/photos", s, data=data, files=files
        )
    raise frappe.ValidationError("publish_photo richiede image_url oppure image_bytes.")


def _apply_schedule(data: dict, scheduled_time) -> None:
    """Applica la programmazione nativa FB se il tempo è futuro >= 10 minuti.

    Facebook impone che scheduled_publish_time sia tra 10 minuti e 6 mesi nel
    futuro. Sotto i 10 minuti pubblichiamo subito (lo scheduler interno gestirà
    i casi ravvicinati chiamando questa funzione senza scheduled_time).
    """
    if not scheduled_time:
        return
    when = get_datetime(scheduled_time)
    delta = (when - now_datetime()).total_seconds()
    if delta >= 600:
        data["published"] = "false"
        data["scheduled_publish_time"] = int(when.timestamp())


def delete_post(fb_post_id: str) -> dict:
    """Elimina un post pubblicato sulla Pagina."""
    s = _require_config()
    return _graph_request("DELETE", f"/{fb_post_id}", s)


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

# Metriche interazione base disponibili senza permessi speciali.
_POST_FIELDS = "permalink_url,likes.summary(true),comments.summary(true),shares"
_POST_INSIGHT_METRICS = "post_impressions,post_impressions_unique,post_clicks"


def fetch_post_metrics(fb_post_id: str) -> dict:
    """Restituisce metriche normalizzate di un singolo post.

    Chiave -> valore int: impressions, reach, clicks, likes, comments, shares,
    più permalink (str). Le metriche mancanti valgono 0.
    """
    s = _require_config()
    out = {
        "impressions": 0, "reach": 0, "clicks": 0,
        "likes": 0, "comments": 0, "shares": 0, "permalink": "",
    }

    # 1) Engagement base + permalink
    base = _graph_request(
        "GET", f"/{fb_post_id}", s, params={"fields": _POST_FIELDS}
    )
    out["permalink"] = base.get("permalink_url", "")
    out["likes"] = _summary_count(base.get("likes"))
    out["comments"] = _summary_count(base.get("comments"))
    shares = base.get("shares") or {}
    out["shares"] = int(shares.get("count", 0) or 0)

    # 2) Insights (impressions/reach/clicks) - best effort
    try:
        ins = _graph_request(
            "GET", f"/{fb_post_id}/insights", s,
            params={"metric": _POST_INSIGHT_METRICS},
        )
        for row in ins.get("data", []):
            name = row.get("name")
            values = row.get("values") or [{}]
            val = int(values[0].get("value", 0) or 0)
            if name == "post_impressions":
                out["impressions"] = val
            elif name == "post_impressions_unique":
                out["reach"] = val
            elif name == "post_clicks":
                out["clicks"] = val
    except Exception:
        # Alcune metriche richiedono read_insights: non bloccare l'engagement.
        frappe.log_error(frappe.get_traceback(), "facebook_graph post insights")

    return out


def fetch_page_insights(metrics: list[str] | None = None, period: str = "day") -> dict:
    """Insights aggregati della Pagina (follower, impression, engagement).

    Restituisce {metric_name: latest_value}. Best-effort: le metriche non
    disponibili sono semplicemente assenti.
    """
    s = _require_config()
    metrics = metrics or [
        "page_impressions",
        "page_post_engagements",
        "page_fans",
        "page_views_total",
    ]
    res = _graph_request(
        "GET", f"/{s['page_id']}/insights", s,
        params={"metric": ",".join(metrics), "period": period},
    )
    out: dict = {}
    for row in res.get("data", []):
        values = row.get("values") or []
        if values:
            out[row["name"]] = values[-1].get("value")
    return out


def _summary_count(obj) -> int:
    if not isinstance(obj, dict):
        return 0
    return int((obj.get("summary") or {}).get("total_count", 0) or 0)
