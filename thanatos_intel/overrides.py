"""Override e patch generici per il sito Thanatos."""
import re


def filter_stale_preloads(response=None, request=None, **kwargs):
    """Rimuove dal header Link preload gli asset che il body HTML NON referenzia
    davvero (via <link rel=stylesheet href="…">, <script src="…"> o <img>).

    Frappe genera Link header basato su preload_assets accumulato durante il
    render dei template Jinja: se un template registra un asset ma non lo emette
    (es. login page che triggera hook web_include_css contenenti bundle di altre
    app), il browser lo scarica ma non lo usa → warning
    «preloaded using link preload but not used». Il filtro qui elimina quei
    warning senza rompere il preload legittimo."""
    if response is None:
        return
    try:
        link = response.headers.get("Link")
        if not link or "rel=preload" not in link:
            return
        body = response.get_data(as_text=True) if hasattr(response, "get_data") else ""
        if not body:
            return
        parts = [p.strip() for p in link.split(",") if p.strip()]
        keep = []
        for p in parts:
            if "rel=preload" not in p:
                keep.append(p); continue
            m = re.match(r"<([^>?#]+)(\?[^>]*)?>", p)
            if not m:
                keep.append(p); continue
            path = m.group(1)
            # asset "usato" se il body cita il path (con o senza querystring)
            if path in body:
                keep.append(p)
        if len(keep) == len(parts):
            return
        if keep:
            response.headers["Link"] = ",".join(keep)
        else:
            response.headers.pop("Link", None)
    except Exception:
        # silenzioso: mai far cadere una request per un warning cosmetico
        pass
