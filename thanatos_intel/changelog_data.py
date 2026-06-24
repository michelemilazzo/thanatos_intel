"""Changelog Thanatos Intel — generato AUTOMATICAMENTE dalla cronologia git del repo.
Ogni commit diventa una voce (data, titolo, dettaglio, area dedotta). Nessuna voce manuale."""
import os
import re
import subprocess

import frappe

APP_PATH = frappe.get_app_path("thanatos_intel", "..") if hasattr(frappe, "get_app_path") else None

# parole chiave -> area (prima corrispondenza vince)
AREA_RULES = [
    ("SEO", ["seo", "analytics", "keyword", "parole chiave", "gsc", "search console", "sitemap", "meta"]),
    ("Profilo", ["profil", "kyc", "kyb", "indirizz", "anagrafic"]),
    ("Portale", ["portale", "portal", "privacy", "gdpr", "consens", "ricerca", "home", "nav", "leggibil", "theme", "tema", "font"]),
    ("Fatturazione", ["fattur", "invoice", "billing", "stripe", "abbonament", "proforma", "iva", "ron", "eur"]),
    ("Sicurezza", ["sicurezz", "2fa", "passkey", "login", "auth", "permess", "ruolo", "ruoli", "role"]),
    ("Comunicazione", ["mail", "webmail", "whatsapp", "waba", "email", "notif", "stalwart"]),
    ("Sistema", ["impostazion", "settings", "workspace", "desk", "deploy", "migrate", "bench", "nginx", "cron", "scheduler"]),
]

# commit da nascondere (rumore)
SKIP_RE = re.compile(r"^(merge|wip|tmp|temp|fixup|amend|revert|bump|typo|lint|format|chore)\b", re.I)
HIGHLIGHT_RE = re.compile(r"\b(nuov|aggiun|pagina|dashboard|feature|introdu|crea)", re.I)


def _area(text):
    t = (text or "").lower()
    for area, kws in AREA_RULES:
        if any(k in t for k in kws):
            return area
    return "Altro"


def _clean_body(body):
    lines = []
    for ln in (body or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.lower().startswith("co-authored-by") or s.startswith("🤖") or "claude code" in s.lower():
            continue
        lines.append(s.lstrip("-• ").strip())
    return lines


def _git_log(limit=200):
    path = os.path.abspath(os.path.join(frappe.get_app_path("thanatos_intel"), ".."))
    sep, rec = "\x1f", "\x1e"
    fmt = sep.join(["%H", "%ad", "%s", "%b"]) + rec
    try:
        out = subprocess.check_output(
            ["git", "-C", path, "log", "--no-merges", "--date=short",
             "-n", str(limit), "--pretty=format:" + fmt],
            stderr=subprocess.DEVNULL, timeout=15).decode("utf-8", "replace")
    except Exception:
        return []
    items = []
    for raw in out.split(rec):
        raw = raw.strip("\n")
        if not raw:
            continue
        parts = raw.split(sep)
        if len(parts) < 3:
            continue
        h, date, subject = parts[0], parts[1], parts[2]
        body = parts[3] if len(parts) > 3 else ""
        if SKIP_RE.match(subject.strip()):
            continue
        # titolo: togli prefisso "Thanatos Intel:" / "thanatos_intel:" e simili
        title = re.sub(r"^[\w \-]{0,24}:\s*", "", subject).strip() or subject
        title = title[:1].upper() + title[1:]
        body_lines = _clean_body(body)
        desc = " · ".join(body_lines[:4])
        area = _area(subject)
        if area == "Altro":
            area = _area(subject + " " + body)
        items.append({
            "date": date,
            "title": title[:160],
            "desc": desc[:600],
            "area": area,
            "audience": "Cliente" if re.search(r"client|portale|portal", subject, re.I) else "Interno",
            "highlight": 1 if HIGHLIGHT_RE.search(subject) else 0,
            "hash": h[:8],
        })
    return items


@frappe.whitelist()
def get_updates():
    if frappe.session.user == "Guest":
        frappe.throw("Accesso non consentito.", frappe.PermissionError)
    cache = frappe.cache()
    key = "thanatos_changelog_git"
    items = cache.get_value(key)
    if not items:
        items = _git_log()
        cache.set_value(key, items, expires_in_sec=600)
    areas = sorted({u.get("area", "Altro") for u in items})
    return {"updates": items, "areas": areas, "count": len(items), "auto": True}
