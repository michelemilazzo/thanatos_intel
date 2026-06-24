"""
News ingestion engine for Thanatos.
Pulls RSS/Atom feeds, dedup by hash(url+guid), optional AI-rewrite via Claude CLI / Ollama.
"""
import hashlib
import re
from datetime import datetime, timezone

import frappe
from frappe.utils import now_datetime


# ---------- helpers ----------

def _slugify(text: str) -> str:
	"""Slug ASCII URL-safe: translittera accenti, rimuove punteggiatura/emoji,
	collassa i trattini. (frappe.utils.slug fa solo lower()+spazi->trattini.)"""
	import unicodedata
	if not text:
		return ""
	text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
	text = re.sub(r"[^a-z0-9]+", "-", text.lower())
	return text.strip("-")


def _unique_slug(base: str, fallback: str = "") -> str:
	"""Garantisce uno slug univoco fra le News Article (append -2, -3...)."""
	base = base[:160] or (fallback or "news")[:16]
	slug = base
	i = 2
	while frappe.db.exists("News Article", {"slug": slug}):
		suffix = "-%d" % i
		slug = base[:160 - len(suffix)] + suffix
		i += 1
	return slug


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


def _og_image(page_url: str) -> str | None:
	"""Fallback: estrae og:image / twitter:image dalla pagina dell'articolo."""
	if not page_url:
		return None
	try:
		import requests
		r = requests.get(page_url, timeout=8, headers={"User-Agent": "Mozilla/5.0 thanatos-news"})
		if r.status_code != 200:
			return None
		h = r.text[:200000]
		for prop in ("og:image", "twitter:image"):
			m = (re.search(r'<meta[^>]+property=["\']' + prop + r'["\'][^>]+content=["\']([^"\']+)', h, re.I)
			     or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']' + prop + r'["\']', h, re.I)
			     or re.search(r'<meta[^>]+name=["\']' + prop + r'["\'][^>]+content=["\']([^"\']+)', h, re.I))
			if m and m.group(1).startswith("http"):
				return m.group(1)[:500]
	except Exception:
		return None
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


# Categorizzazione per CONTENUTO + filtro pertinenza.
# Chiave = name della News Category (slug). Solo notizie attinenti ai temi Thanatos
# vengono ingerite; le altre (es. cronaca generica) sono scartate.
_KW_RE_CACHE = {}


def _kw_hit(kw, text):
	pat = _KW_RE_CACHE.get(kw)
	if pat is None:
		pat = re.compile(r"\b" + re.escape(kw) + r"\b")
		_KW_RE_CACHE[kw] = pat
	return bool(pat.search(text))


GENERAL_CATEGORY = "generale-cronaca"


CATEGORY_KEYWORDS = {
	"frodi-truffe": ["frode", "frodi", "truffa", "truffe", "raggiro", "raggir", "phishing",
		"scam", "fraud", "ponzi", "piramidale", "riciclagg", "money launder", "estafa",
		"escroquer", "swindle", "financial crime", "reato finanziario", "appropriazione indebita"],
	"cyber-intelligence": ["cyber", "hacker", "ransomware", "malware", "data breach", "databreach",
		"violazione dati", "data leak", "attacco informatico", "cybersecurity", "cyber security",
		"ddos", "exploit", "spyware", "trojan", "credential", "infostealer"],
	"corporate-due-diligence": ["due diligence", "compliance", "kyc", "kyb", "antiriciclaggio",
		"aml", "sanzion", "sanction", "titolare effettivo", "beneficial owner", "conformit",
		"adeguata verifica", "screening", "watchlist"],
	"sequestri-confische": ["sequestr", "confisc", "seizure", "asset recovery", "beni confiscati",
		"forfeiture", "congelamento beni", "frozen asset", "recupero crediti", "recupero beni"],
	"diritto-procedura": ["gdpr", "garante privacy", "data protection", "regolamento ue", "direttiva ue",
		"court ruling", "procedura penale", "diritto penale", "catena di custodia", "chain of custody",
		"ammissibilita delle prove", "onere della prova"],
	"osint-techniques": ["osint", "open source intelligence", "geolocalizzaz", "social media intelligence",
		"deanonim", "verifica delle fonti", "fact-check", "fact check", "humint", "socmint"],
	"crypto-investigations": ["crypto", "cripto", "criptovalut", "bitcoin", "ethereum", "wallet crypto",
		"blockchain", "stablecoin", "cryptocurrency", "exchange crypto", "usdt", "wallet bitcoin"],
}


def _categorize(text: str):
	"""Ritorna (category_name, score) della categoria piu' pertinente, o (None, 0)."""
	t = (text or "").lower()
	if not t:
		return None, 0
	best, best_score = None, 0
	for cat, kws in CATEGORY_KEYWORDS.items():
		if not frappe.db.exists("News Category", cat):
			continue
		score = sum(1 for k in kws if _kw_hit(k, t))
		if score > best_score:
			best, best_score = cat, score
	return best, best_score


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

def _fetch_feed(url: str):
	"""Scarica il feed con UA browser (alcuni server servono HTML a UA sconosciuti
	o redirigono) e lo passa a feedparser come bytes; fallback al fetch di feedparser."""
	import feedparser
	try:
		import requests
		r = requests.get(url, timeout=20, allow_redirects=True,
			headers={"User-Agent": "Mozilla/5.0 (compatible; thanatos-news/1.0)"})
		if r.status_code == 200 and r.content:
			return feedparser.parse(r.content)
	except Exception:
		pass
	return feedparser.parse(url)


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

	parsed = _fetch_feed(src.rss_url)
	if getattr(parsed, "bozo", 0) and not getattr(parsed, "entries", None):
		_record_fetch(src, ok=False, err=str(parsed.bozo_exception)[:240], inserted=0)
		return {"error": str(parsed.bozo_exception)[:240]}

	max_n = int(src.max_articles_per_fetch or 20)
	inserted = 0
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

		# categoria dal CONTENUTO; la cronaca non attinente va in "generale-cronaca"
		category, _rel = _categorize(title + " " + _strip_html(raw_content or ""))
		if not category:
			category = GENERAL_CATEGORY if frappe.db.exists("News Category", GENERAL_CATEGORY) else _category_for(src)
		if not category:
			continue

		# arricchimento: testo completo leggibile + traduzione lingua sito + angolo Thanatos
		from thanatos_intel.news.enrich import enrich as _enrich
		en = _enrich(title, raw_content, url, lang="it", source_lang=(src.language or "auto"))
		title_it = en["title"] or title
		excerpt = en["excerpt"]
		content = en["body_html"]

		image_url = _entry_image(entry, raw_content, raw_content)
		if not image_url:
			image_url = _og_image(url)

		try:
			doc = frappe.get_doc({
				"doctype": "News Article",
				"title": title_it,
				"slug": _unique_slug(_slugify(title_it), fp),
				"category": category,
				"excerpt": excerpt,
				"content": content,
				"thanatos_angle": en["thanatos_angle"],
				"cta_label": en["cta_label"],
				"cta_url": en["cta_url"],
				"language": "it",
				"country_focus": src.country_focus or "",
				"source_type": "RSS Ingestion",
				"source": src.name,
				"source_url": url[:500] if url else url,
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


def daily_publish(hours: int = 26) -> int:
	"""Pubblica gli articoli ingeriti di recente ancora in bozza (published=0).
	Eseguito ogni giorno alle 07:00 (cron). published_at = data reale della fonte o adesso."""

	from frappe.utils import now_datetime, add_to_date

	cutoff = add_to_date(now_datetime(), hours=-abs(hours))
	names = frappe.get_all(
		"News Article",
		filters={"published": 0, "creation": [">=", cutoff]},
		pluck="name",
	)
	count = 0
	for name in names:
		ext = frappe.db.get_value("News Article", name, "external_published_at")
		frappe.db.set_value(
			"News Article", name,
			{"published": 1, "published_at": ext or now_datetime()},
			update_modified=False,
		)
		count += 1
	frappe.db.commit()
	frappe.logger().info(f"[news] daily_publish: pubblicati {count} articoli")
	return count
