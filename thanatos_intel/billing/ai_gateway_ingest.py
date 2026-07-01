"""Ingestione del ledger token del gateway AI (volume condiviso mmos-ai-usage) -> AI Usage Log
via ai_meter. Il gateway (ai-core) scrive OGNI chiamata di OGNI modello nel ledger; questo job,
schedulato su ciascun bench, legge i record dei PROPRI siti e li fattura. Idempotente via offset
per-file. Attribuzione: site_config ai_gateway_client_map {site: client} o ai_gateway_default_client;
se un record non e attribuibile NON si fattura alla cieca (viene saltato, resta nel ledger)."""
import json
import os

import frappe

from . import ai_meter

LEDGER_DIR = os.environ.get("MMOS_AI_USAGE_DIR", "/mnt/mmos-shared-storage/mmos-ai-usage")


def _state_path():
    return frappe.get_site_path("ai_gateway_ingest_offset.json")


def _load_offsets():
    try:
        return json.load(open(_state_path()))
    except Exception:
        return {}


def _save_offsets(o):
    tmp = _state_path() + ".tmp"
    json.dump(o, open(tmp, "w"))
    os.replace(tmp, _state_path())


def _client_for_session(session_id):
    """AUTOMATICO: dall'utente nel session_id (<sito>:<utente>[:<chat>]) risolve
    l'Investigation Client collegato (platform_user). Fallback: mappa per-sito o
    house-client per l'uso interno/staff. None => non fatturiamo alla cieca."""
    parts = (session_id or "").split(":")
    site = parts[0] if parts else ""
    user = parts[1] if len(parts) > 1 else ""
    if user:
        try:
            from ..permissions import _client_records
            cs = _client_records(user)
            if cs:
                return cs[0]
        except Exception:
            pass
    cmap = frappe.conf.get("ai_gateway_client_map") or {}
    if site in cmap:
        return cmap[site]
    return frappe.conf.get("ai_gateway_house_client") or frappe.conf.get("ai_gateway_default_client")


def ingest_gateway_usage():
    """Scheduler: legge i nuovi record del ledger e li registra come AI Usage Log."""
    if not os.path.isdir(LEDGER_DIR):
        return 0
    offsets = _load_offsets()
    my_sites = set(frappe.conf.get("ai_gateway_sites") or [frappe.local.site])
    processed = 0
    for fname in sorted(os.listdir(LEDGER_DIR)):
        if not (fname.startswith("usage-") and fname.endswith(".jsonl")):
            continue
        path = os.path.join(LEDGER_DIR, fname)
        try:
            size = os.path.getsize(path)
        except Exception:
            continue
        start = int(offsets.get(fname, 0))
        if size <= start:
            continue
        with open(path) as f:
            f.seek(start)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                sid = rec.get("session_id", "")
                if my_sites and sid.split(":")[0] not in my_sites:
                    continue
                client = _client_for_session(sid)
                if not client:
                    continue
                try:
                    ai_meter.record_usage(client, rec.get("model", ""),
                                          rec.get("tokens_in", 0), rec.get("tokens_out", 0),
                                          provider=None, reference=sid[:140])
                    processed += 1
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "ai_gateway_ingest")
            offsets[fname] = f.tell()
    _save_offsets(offsets)
    if processed:
        frappe.db.commit()
    return processed
