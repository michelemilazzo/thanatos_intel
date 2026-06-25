"""Import liste pubbliche di latitanti come Tracking Target (classification=Public Wanted).

Fonti:
- Interpol Red Notices — API pubblica JSON (ws-public.interpol.int), nessuna chiave.
- Europol EU Most Wanted — best-effort sul sito pubblico (degrada a stub se cambia).

Idempotente: dedup per (source, source_ref). Re-import aggiorna i campi.
"""
import frappe
import requests

from thanatos_intel.osint.engine import UA

INTERPOL_RED_URL = "https://ws-public.interpol.int/notices/v1/red"


def _upsert(source, ref, fields):
    name = frappe.db.get_value(
        "Tracking Target", {"source": source, "source_ref": ref}, "name"
    )
    if name:
        doc = frappe.get_doc("Tracking Target", name)
        doc.update(fields)
        doc.flags.skip_enrich = True
        doc.save(ignore_permissions=True)
        return ("updated", doc.name)
    doc = frappe.new_doc("Tracking Target")
    doc.update(fields)
    doc.classification = "Public Wanted"
    doc.source = source
    doc.source_ref = ref
    doc.flags.skip_enrich = True
    doc.insert(ignore_permissions=True)
    return ("created", doc.name)


@frappe.whitelist()
def import_interpol(pages: int = 1, per_page: int = 50):
    """Importa Red Notices Interpol. Ritorna conteggio created/updated."""
    pages = int(pages)
    per_page = int(per_page)
    created = updated = 0
    headers = {"user-agent": UA, "accept": "application/json"}
    for page in range(1, pages + 1):
        try:
            r = requests.get(
                INTERPOL_RED_URL,
                params={"resultPerPage": per_page, "page": page},
                headers=headers, timeout=20,
            )
            if r.status_code != 200:
                break
            notices = (r.json() or {}).get("_embedded", {}).get("notices", [])
        except Exception:
            frappe.log_error(frappe.get_traceback(), "interpol import")
            break
        if not notices:
            break
        for n in notices:
            ref = n.get("entity_id")
            if not ref:
                continue
            full = " ".join(filter(None, [n.get("forename"), n.get("name")])).title()
            img = (n.get("_links", {}).get("thumbnail")
                   or n.get("_links", {}).get("images") or {}).get("href")
            fields = {
                "target_name": full or ref,
                "target_type": "Person",
                "nationality": ", ".join(n.get("nationalities") or []),
                "date_of_birth": _parse_dob(n.get("date_of_birth")),
                "source_url": (n.get("_links", {}).get("self") or {}).get("href"),
                "photo": img,
                "priority": "High",
            }
            action, _ = _upsert("Interpol Red Notice", ref, fields)
            created += action == "created"
            updated += action == "updated"
        frappe.db.commit()
    return {"source": "Interpol Red Notice", "created": created, "updated": updated}


@frappe.whitelist()
def import_europol():
    """Best-effort import Europol EU Most Wanted (eumostwanted.eu).

    Il sito non espone un'API stabile: tentiamo il feed pubblico e degradiamo a
    stub senza errori se la struttura cambia.
    """
    created = updated = 0
    headers = {"user-agent": UA}
    try:
        r = requests.get("https://eumostwanted.eu/api/fugitives", headers=headers, timeout=20)
        if r.status_code != 200:
            return {"source": "Europol EU Most Wanted", "stub": True,
                    "note": "feed non disponibile (import manuale)"}
        data = r.json()
    except Exception:
        return {"source": "Europol EU Most Wanted", "stub": True,
                "note": "feed non disponibile (import manuale)"}

    items = data if isinstance(data, list) else data.get("data", [])
    for it in items:
        ref = str(it.get("id") or it.get("slug") or "")
        if not ref:
            continue
        fields = {
            "target_name": it.get("name") or it.get("title") or ref,
            "target_type": "Person",
            "nationality": it.get("nationality") or "",
            "wanted_for": it.get("crime") or it.get("offence") or "",
            "source_url": it.get("url") or "",
            "priority": "High",
        }
        action, _ = _upsert("Europol EU Most Wanted", ref, fields)
        created += action == "created"
        updated += action == "updated"
    frappe.db.commit()
    return {"source": "Europol EU Most Wanted", "created": created, "updated": updated}


def _parse_dob(s):
    if not s:
        return None
    s = str(s).strip()
    # Interpol usa spesso YYYY/MM/DD
    s = s.replace("/", "-")
    parts = s.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        try:
            return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        except Exception:
            return None
    return None
