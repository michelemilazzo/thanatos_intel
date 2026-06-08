"""
News ingestion engine for Thanatos.
Pulls RSS/Atom feeds, dedup by hash(url+guid), optional AI-rewrite via Claude CLI / Ollama.
"""
import hashlib
import re
from datetime import datetime, timezone

import frappe
from frappe.utils import now_datetime, slug as _slug


# ---------- helpers ----------

def _fingerprint(*parts) -> str:
	h = hashlib.sha256()
	for p in parts:
		h.update((p or "").encode("utf-8", errors="ignore"))
	return h.hexdigest()[:32]


def _strip_html(s: str) -> str:
	if not s:
		return ""
	s = re.sub(r"<[^>]+>", " ", s)
	return re.sub(r"\s+", " ", s).strip()


_IMG_RX = re.compile(r'<img[^>]+src=["\']([^"\']+)', re.I)


def _entry_image(entry, *contents) -> str | None:
	"""Estrae la migliore immagine dall'entry RSS (thumbnail/media/enclosure/<img>)."""
	for thumb in (entry.get("media_thumbnail") or []):
		if thumb.get("url"):
			return thumb["url"]
	for media in (entry.get("media_content") or []):
		if media.get("url") and (media.get("medium") == "image" or "image" in (media.get("type") or "")):
			return media["url"]
	for link in (entry.get("links") or []):
		if link.get("rel") == "enclosure" and "image" in (link.get("type") or "") and link.get("href"):
			return link["href"]
	for c in contents:
		m = _IMG_RX.search(c or "")
		if m:
			return m.group(1)
	return None


def _parse_datetime(raw) -> datetime | None:
	if not raw:
		return None
	try:
		from dateutil import parser as dp
		dt = dp.parse(raw)
		if dt.tzinfo:
			dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
		return dt
	except Exception:
		return None


def _category_for(src) -> str | None:
	if src.default_category and frappe.db.exists("News Category", src.default_category):
		return src.default_category
	cat = frappe.db.get_value("News Category", {"is_active": 1}, "name")
	return cat


# ---------- AI rewrite ----------

def _ai_rewrite(title: str, content: str, language: str = "it") -> tuple[str, str]:
	"""Use Claude CLI or Ollama (whichever available) to rewrite excerpt + body
	in Thanatos editorial voice. Falls back to raw text on any error."""
	plain = _strip_html(content)[:4000]
	try:
		# Prefer ollama (local, free)
		from thanatos_intel.ai.providers import rewrite_news
		out = rewrite_news(title=title, body=plain, language=language)
		if out and isinstance(out, dict):
			return (out.get("excerpt") or plain[:280],
			        out.get("body_html") or content or f"<p>{plain}</p>")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "news AI rewrite failed")
	# fallback: short excerpt + paragraph wrap
	excerpt = plain[:280] + ("…" if len(plain) > 280 else "")
	return excerpt, content or f"<p>{plain}</p>"


# ---------- core ingest ----------

@frappe.whitelist()
def fetch_source(name: str) -> dict:
	src = frappe.get_doc("News Source", name)
	if not src.is_active:
		return {"skipped": "inactive"}
	if src.source_type not in ("RSS", "Atom"):
		return {"skipped": "unsupported_type"}
	try:
		import feedparser
	except ImportError:
		return {"error": "feedparser not installed"}

	parsed = feedparser.parse(src.rss_url)
	if getattr(parsed, "bozo", 0) and not getattr(parsed, "entries", None):
		_record_fetch(src, ok=False, err=str(parsed.bozo_exception)[:240], inserted=0)
		return {"error": str(parsed.bozo_exception)[:240]}

	max_n = int(src.max_articles_per_fetch or 20)
	inserted = 0
	category = _category_for(src)
	for entry in parsed.entries[:max_n]:
		url = entry.get("link") or ""
		guid = entry.get("id") or entry.get("guid") or url
		fp = _fingerprint(url, guid)
		if frappe.db.exists("News Article", {"external_id": fp}):
			continue
		title = (entry.get("title") or "").strip()[:240]
		if not title:
			continue
		raw_content = entry.get("content", [{}])[0].get("value") if entry.get("content") else entry.get("summary", "")
		ext_pub = _parse_datetime(entry.get("published") or entry.get("updated"))

		if src.ai_summarize:
			excerpt, content = _ai_rewrite(title, raw_content, src.language or "it")
		else:
			plain = _strip_html(raw_content)
			excerpt = plain[:280] + ("…" if len(plain) > 280 else "")
			content = raw_content or f"<p>{plain}</p>"

		image_url = _entry_image(entry, raw_content, content)

		try:
			doc = frappe.get_doc({
				"doctype": "News Article",
				"title": title,
				"slug": _slug(title)[:160] or fp[:16],
				"category": category,
				"excerpt": excerpt,
				"content": content,
				"language": src.language or "it",
				"country_focus": src.country_focus or "",
				"source_type": "RSS Ingestion",
				"source": src.name,
				"source_url": url,
				"source_name_label": src.source_name,
				"external_published_at": ext_pub,
				"external_id": fp,
				"featured_image": image_url,
				"published": 1 if src.auto_publish else 0,
				"published_at": now_datetime() if src.auto_publish else None,
			})
			doc.insert(ignore_permissions=True)
			inserted += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"news ingest fail {src.name}")
			continue

	_record_fetch(src, ok=True, err=None, inserted=inserted)
	frappe.db.commit()
	return {"source": src.name, "inserted": inserted, "scanned": len(parsed.entries[:max_n])}


def _record_fetch(src, ok: bool, err: str | None, inserted: int):
	src.last_fetched_at = now_datetime()
	src.last_status = "OK" if ok else "Error"
	src.last_error = err or ""
	src.total_fetched = (src.total_fetched or 0) + inserted
	src.db_update()


# ---------- scheduler hooks ----------

def hourly_ingest():
	"""Called by scheduler_events.hourly. Iterates all active News Source."""
	for s in frappe.get_all("News Source", filters={"is_active": 1}, pluck="name"):
		try:
			fetch_source(s)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"hourly_ingest {s}")


def daily_case_digest():
	"""Generates an anonymized aggregate news article from this week's investigation activity."""
	try:
		from thanatos_intel.news.case_digest import generate_weekly_digest
		generate_weekly_digest()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "daily_case_digest")
