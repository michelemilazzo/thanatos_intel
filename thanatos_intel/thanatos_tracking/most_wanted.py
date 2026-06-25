"""Import liste pubbliche di latitanti come Tracking Target (classification=Public Wanted).

Fonti:
- Interpol Red Notices — via dataset bulk OpenSanctions (interpol_red_notices,
  FollowTheMoney NDJSON, aggiornato giornalmente, no chiave). L'API diretta
  ws-public.interpol.int e' bloccata dal WAF sugli IP datacenter (403).
- Europol EU Most Wanted — best-effort sul sito pubblico (degrada a stub se cambia).

Idempotente: dedup per (source, source_ref). Re-import aggiorna i campi.
"""
import json

import frappe
import requests

from thanatos_intel.osint.engine import UA

INTERPOL_OS_DATASET = (
    "https://data.opensanctions.org/datasets/latest/"
    "interpol_red_notices/entities.ftm.json"
)
OS_ENTITY_URL = "https://www.opensanctions.org/entities/{id}/"


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
def import_interpol(limit: int = 500):
    """Importa Red Notices Interpol dal dataset bulk OpenSanctions (FTM NDJSON).

    `limit` = max target da importare (0 = tutti, ~6400). Idempotente.
    """
    limit = int(limit)
    created = updated = seen = 0
    headers = {"user-agent": UA, "accept": "application/json"}
    try:
        r = requests.get(INTERPOL_OS_DATASET, headers=headers, stream=True, timeout=60)
        if r.status_code != 200:
            return {"source": "Interpol Red Notice", "error": True,
                    "http": r.status_code, "created": 0, "updated": 0}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "interpol import")
        return {"source": "Interpol Red Notice", "error": True,
                "created": 0, "updated": 0}

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
        name = (p.get("name") or [None])[0] or " ".join(
            filter(None, [(p.get("firstName") or [""])[0], (p.get("lastName") or [""])[0]])
        )
        if not name:
            continue
        fields = {
            "target_name": name.title(),
            "target_type": "Person",
            "nationality": ", ".join(c.upper() for c in (p.get("nationality") or [])),
            "date_of_birth": _parse_dob((p.get("birthDate") or [None])[0]),
            "last_known_location": ", ".join(p.get("birthPlace") or [])[:140] or None,
            "wanted_for": ", ".join(p.get("topics") or []),
            "source_url": OS_ENTITY_URL.format(id=ref),
            "priority": "High",
        }
        action, _ = _upsert("Interpol Red Notice", ref, fields)
        created += action == "created"
        updated += action == "updated"
        seen += 1
        if seen % 200 == 0:
            frappe.db.commit()
        if limit and seen >= limit:
            break
    frappe.db.commit()
    return {"source": "Interpol Red Notice", "created": created,
            "updated": updated, "imported": seen}


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
