"""OpenSanctions local cache.

Scarica la dataset 'sanctions' consolidata (JSON statements) e indicizza
nomi/alias in MariaDB per matching offline veloce.

Fonte ufficiale: https://data.opensanctions.org/datasets/latest/sanctions/
Schema: ogni riga è un Entity con 'caption', 'properties.name', 'properties.alias'.
"""
import json
import frappe
import requests
from frappe.utils import now_datetime

DATASET_URL = "https://data.opensanctions.org/datasets/latest/sanctions/entities.ftm.json"


def _ensure_table():
    frappe.db.sql_ddl("""
    CREATE TABLE IF NOT EXISTS `tabOpenSanctions Cache` (
      `id` VARCHAR(255) PRIMARY KEY,
      `name` VARCHAR(512),
      `schema_type` VARCHAR(64),
      `caption` VARCHAR(512),
      `topics` TEXT,
      `birth_date` VARCHAR(20),
      `nationality` VARCHAR(255),
      `aliases` TEXT,
      `source_url` TEXT,
      `updated_on` DATETIME,
      INDEX `idx_name` (`name`),
      INDEX `idx_caption` (`caption`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


@frappe.whitelist()
def sync(limit: int = 0) -> dict:
    """Esegue il refresh della cache OpenSanctions. limit=0 → tutti."""
    _ensure_table()
    inserted = 0
    skipped = 0
    r = requests.get(DATASET_URL, stream=True, timeout=600)
    r.raise_for_status()
    for raw in r.iter_lines():
        if not raw:
            continue
        try:
            ent = json.loads(raw)
        except Exception:
            skipped += 1
            continue
        eid = ent.get("id")
        if not eid:
            continue
        props = ent.get("properties", {}) or {}
        names = props.get("name") or []
        aliases = (props.get("alias") or []) + (props.get("weakAlias") or [])
        nat = ",".join(props.get("nationality") or [])
        bdate = (props.get("birthDate") or [""])[0]
        topics = ",".join(ent.get("topics") or [])
        frappe.db.sql("""
            INSERT INTO `tabOpenSanctions Cache`
                (id, name, schema_type, caption, topics, birth_date, nationality, aliases, source_url, updated_on)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE name=VALUES(name), caption=VALUES(caption),
                topics=VALUES(topics), birth_date=VALUES(birth_date),
                nationality=VALUES(nationality), aliases=VALUES(aliases),
                updated_on=VALUES(updated_on)
        """, (eid, (names[0] if names else "")[:512],
              ent.get("schema") or "", (ent.get("caption") or "")[:512],
              topics, bdate[:20], nat[:255],
              "|".join(aliases)[:4000],
              f"https://www.opensanctions.org/entities/{eid}/",
              now_datetime()))
        inserted += 1
        if inserted % 5000 == 0:
            frappe.db.commit()
        if limit and inserted >= limit:
            break
    frappe.db.commit()
    return {"inserted": inserted, "skipped": skipped, "updated_on": str(now_datetime())}


@frappe.whitelist()
def lookup(name: str, dob: str = "", nationality: str = "") -> dict:
    """Match offline. Ritorna fino a 20 hit ordinati per score (prefix+contains)."""
    if not name:
        return {"matches": []}
    like = f"%{name}%"
    rows = frappe.db.sql("""
        SELECT id, name, schema_type, caption, topics, birth_date,
               nationality, aliases, source_url
        FROM `tabOpenSanctions Cache`
        WHERE name LIKE %s OR caption LIKE %s OR aliases LIKE %s
        LIMIT 200
    """, (like, like, like), as_dict=True)
    name_l = name.lower()
    def score(r):
        s = 0
        if r.get("name", "").lower() == name_l: s += 100
        elif name_l in (r.get("name", "").lower()): s += 60
        elif name_l in (r.get("caption", "").lower()): s += 40
        if dob and r.get("birth_date") and r["birth_date"].startswith(dob[:4]): s += 20
        if nationality and (nationality in (r.get("nationality") or "")): s += 15
        return s
    scored = sorted((dict(r, score=score(r)) for r in rows),
                    key=lambda x: x["score"], reverse=True)
    return {"query": {"name": name, "dob": dob, "nationality": nationality},
            "matches": scored[:20], "total": len(rows)}


def daily_refresh():
    """Job scheduler chiamato da hooks.scheduler_events.daily."""
    try:
        return sync()
    except Exception as e:
        frappe.log_error(f"OpenSanctions daily sync fail: {e}", "DddOSyncDaily")
