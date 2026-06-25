"""Import liste pubbliche di latitanti/ricercati come Tracking Target (Public Wanted).

Fonte: dataset bulk **OpenSanctions** (FollowTheMoney NDJSON, aggiornati ogni
giorno, senza chiave). L'API diretta Interpol (ws-public.interpol.int) e' bloccata
dal WAF sugli IP datacenter (403), quindi NON si usa.

Catalogo fonti in DATASETS. Idempotente: dedup per (source, source_ref=id OpenSanctions).
"""
import json

import frappe
import requests

from thanatos_intel.osint.engine import UA

DATASET_URL = "https://data.opensanctions.org/datasets/latest/{key}/entities.ftm.json"
OS_ENTITY_URL = "https://www.opensanctions.org/entities/{id}/"

# key OpenSanctions -> (label sorgente, priorita')
DATASETS = {
    "interpol_red_notices": ("Interpol Red Notice", "High"),
    "eu_europol_wanted": ("Europol EU Most Wanted", "High"),
    "us_fbi_most_wanted": ("FBI Most Wanted", "High"),
    "gb_nca_most_wanted": ("UK NCA Most Wanted", "High"),
    "de_bka_wanted": ("Germany BKA Wanted", "High"),
    "es_cnp_wanted": ("Spain Police Most Wanted", "High"),
    "nl_most_wanted": ("Netherlands Most Wanted", "High"),
    "us_dea_fugitives": ("US DEA Fugitives", "High"),
    "us_ice_wanted": ("US ICE Most Wanted", "High"),
    "us_secret_service": ("US Secret Service Most Wanted", "High"),
    "za_wanted": ("South Africa Wanted", "Medium"),
}
# alias service-secret key reale
_KEY_FIX = {"us_secret_service": "us_ss_wanted"}


def _first(p, *keys):
    for k in keys:
        v = p.get(k)
        if v:
            return v[0]
    return None


def _upsert(source, ref, fields):
    name = frappe.db.get_value(
        "Tracking Target", {"source": source, "source_ref": ref}, "name"
    )
    if name:
        doc = frappe.get_doc("Tracking Target", name)
        doc.update(fields)
        doc.flags.skip_enrich = True
        doc.save(ignore_permissions=True)
        return "updated"
    doc = frappe.new_doc("Tracking Target")
    doc.update(fields)
    doc.classification = "Public Wanted"
    doc.source = source
    doc.source_ref = ref
    doc.flags.skip_enrich = True
    doc.insert(ignore_permissions=True)
    return "created"


@frappe.whitelist()
def import_dataset(key: str, limit: int = 0):
    """Importa un dataset wanted OpenSanctions. limit=0 -> tutti."""
    if key not in DATASETS:
        frappe.throw(f"Dataset non supportato: {key}")
    limit = int(limit)
    label, prio = DATASETS[key]
    url = DATASET_URL.format(key=_KEY_FIX.get(key, key))
    created = updated = seen = 0
    try:
        r = requests.get(url, headers={"user-agent": UA}, stream=True, timeout=90)
        if r.status_code != 200:
            return {"source": label, "error": True, "http": r.status_code,
                    "created": 0, "updated": 0}
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"wanted import {key}")
        return {"source": label, "error": True, "created": 0, "updated": 0}

    for raw in r.iter_lines():
        if not raw:
            continue
        try:
            e = json.loads(raw)
        except Exception:
            continue
        if e.get("schema") != "Person":
            continue
        ref = e.get("id")
        if not ref:
            continue
        p = e.get("properties", {})
        name = _first(p, "name") or " ".join(filter(None, [
            _first(p, "firstName") or "", _first(p, "lastName") or ""]))
        if not name:
            continue
        notes = p.get("notes") or []
        aliases = (p.get("alias") or []) + (p.get("weakAlias") or [])
        loc = ", ".join(p.get("birthPlace") or []) or None
        nat = p.get("nationality") or p.get("citizenship") or p.get("country") or []
        desc = ""
        if notes:
            desc = "".join(f"<p>{frappe.utils.escape_html(x)}</p>" for x in notes)
        fields = {
            "target_name": name.title(),
            "target_type": "Person",
            "nationality": ", ".join(c.upper() for c in nat),
            "gender": _first(p, "gender"),
            "ethnicity": _first(p, "ethnicity"),
            "date_of_birth": _parse_dob(_first(p, "birthDate")),
            "last_known_location": (loc[:140] if loc else None),
            "aliases": "\n".join(aliases) or None,
            "height": _first(p, "height"),
            "weight": _first(p, "weight"),
            "eye_color": _first(p, "eyeColor"),
            "hair_color": _first(p, "hairColor"),
            "distinguishing_marks": "; ".join(p.get("appearance") or []) or None,
            "wanted_for": ", ".join(p.get("topics") or []) or None,
            "description": desc or None,
            "source_url": _first(p, "sourceUrl") or OS_ENTITY_URL.format(id=ref),
            "priority": prio,
        }
        res = _upsert(label, ref, fields)
        created += res == "created"
        updated += res == "updated"
        seen += 1
        if seen % 200 == 0:
            frappe.db.commit()
        if limit and seen >= limit:
            break
    frappe.db.commit()
    return {"source": label, "created": created, "updated": updated, "imported": seen}


@frappe.whitelist()
def import_interpol(limit: int = 0):
    return import_dataset("interpol_red_notices", limit)


@frappe.whitelist()
def import_europol(limit: int = 0):
    return import_dataset("eu_europol_wanted", limit)


import re

_IMG_PATTERNS = [
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\']',
    r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
]


@frappe.whitelist()
def fetch_photo(target: str):
    """Scarica la foto dalla pagina sorgente (og:image) e la allega al Target.

    Funziona per fonti con sourceUrl = pagina pubblica reale (Europol/FBI/liste
    nazionali). Per Interpol il mugshot e' solo sull'API WAF-bloccata -> stub.
    """
    doc = frappe.get_doc("Tracking Target", target)
    url = doc.source_url or ""
    if not url or "opensanctions.org" in url:
        return {"ok": False, "reason": "Nessuna pagina sorgente con foto (Interpol: mugshot non accessibile)"}
    try:
        r = requests.get(url, headers={"user-agent": UA}, timeout=20)
        if r.status_code != 200:
            return {"ok": False, "reason": f"HTTP {r.status_code}"}
        html = r.text
    except Exception:
        return {"ok": False, "reason": "fetch fallito"}

    img_url = None
    for pat in _IMG_PATTERNS:
        m = re.search(pat, html, re.I)
        if m:
            img_url = m.group(1)
            break
    if not img_url:
        return {"ok": False, "reason": "nessuna og:image nella pagina"}
    if img_url.startswith("//"):
        img_url = "https:" + img_url
    elif img_url.startswith("/"):
        from urllib.parse import urljoin
        img_url = urljoin(url, img_url)

    try:
        ir = requests.get(img_url, headers={"user-agent": UA}, timeout=20)
        if ir.status_code != 200 or not ir.content:
            return {"ok": False, "reason": "download immagine fallito"}
        from frappe.utils.file_manager import save_file
        ct = (ir.headers.get("content-type") or "").lower()
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
               "image/webp": "webp", "image/gif": "gif"}.get(ct.split(";")[0], "jpg")
        f = save_file(f"{doc.name}.{ext}", ir.content, doc.doctype, doc.name,
                      is_private=0)
        doc.db_set("photo", f.file_url)
        frappe.db.commit()
        return {"ok": True, "photo": f.file_url}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "fetch_photo")
        return {"ok": False, "reason": "errore salvataggio"}


@frappe.whitelist()
def fetch_photos_bulk(source: str = None, limit: int = 100):
    """Recupera le foto mancanti (best-effort) per i target con pagina sorgente."""
    limit = int(limit)
    filters = {"classification": "Public Wanted", "photo": ["is", "not set"],
               "source_url": ["is", "set"]}
    if source:
        filters["source"] = source
    ok = fail = 0
    for n in frappe.get_all("Tracking Target", filters, pluck="name")[:limit]:
        r = fetch_photo(n)
        ok += 1 if r.get("ok") else 0
        fail += 0 if r.get("ok") else 1
    return {"ok": ok, "failed": fail}


@frappe.whitelist()
def list_sources():
    """Fonti disponibili per il selettore desk."""
    return [{"key": k, "label": v[0]} for k, v in DATASETS.items()]


@frappe.whitelist()
def import_all(limit_per: int = 0):
    """Importa tutte le fonti del catalogo. Ritorna il riepilogo per fonte."""
    out = []
    for key in DATASETS:
        out.append(import_dataset(key, int(limit_per)))
    total = sum(r.get("imported", 0) for r in out)
    return {"results": out, "total_imported": total}


def _parse_dob(s):
    if not s:
        return None
    s = str(s).strip().replace("/", "-")
    parts = s.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        try:
            return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        except Exception:
            return None
    return None
