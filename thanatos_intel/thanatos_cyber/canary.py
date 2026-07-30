"""
Thanatos Canary Toolkit — generazione token-esca + ingest hit dal worker Foxglove.

Modello (vedi docs/CANARY_TOOLKIT.md):
- CATTURA: worker Foxglove (foxglove.pages.dev, Cloudflare Pages). Ogni vettore (link/
  pixel/email/PDF/DOCX/XLSX/QR/redirect/DNS) fa phone-home lì. WHOIS = Cloudflare, mai Thanatos.
- INGEST: PULL schedulato (scheduler cron */10) + on-demand. Foxglove non chiama mai onekeyco (opsec).
- STORAGE: Canary Token (una campagna/esca) + Canary Hit (una visita), legati a Investigation Case.
- ALERT: sui NUOVI hit di un token con alert_on → email all'operatore della pratica (notify).

Config in site_config: canary_base, canary_secret, canary_dns_zone (fallback ai default sotto).
"""

import json
import calendar
from datetime import datetime

import frappe
from frappe import _

DEFAULT_BASE = "https://foxglove.pages.dev"
DEFAULT_SECRET = "0305dc03e421d1a59fdb89db517bca7ac0d6f9f446eb4910"
DEFAULT_DNS_ZONE = "c.thanatos.agency"

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# ASN/org che indicano datacenter/hosting/VPN (IP non residenziale = target dietro proxy)
_SUSPECT = (
	"amazon", "aws", "google", "microsoft", "azure", "digitalocean", "linode", "vultr",
	"hetzner", "ovh", "leaseweb", "m247", "choopa", "constant", "contabo", "scaleway",
	"cloudflare", "fastly", "akamai", "datacamp", "packet", "oracle", "alibaba", "tencent",
	"hosting", "datacenter", "data center", "colo", "vpn", "proxy", "proton", "mullvad",
	"nordvpn", "expressvpn", "privateinternet", "surfshark", "cyberghost", "tor", "relay",
)


def _cfg():
	base = (frappe.conf.get("canary_base") or DEFAULT_BASE).rstrip("/")
	secret = frappe.conf.get("canary_secret") or DEFAULT_SECRET
	zone = (frappe.conf.get("canary_dns_zone") or DEFAULT_DNS_ZONE).strip(".")
	return base, secret, zone


def _new_ref():
	return frappe.generate_hash(length=8)


def _http():
	import requests
	return requests


def _suspect_net(asn, org):
	blob = ("%s %s" % (asn or "", org or "")).lower()
	return 1 if any(k in blob for k in _SUSPECT) else 0


def token_links(ref, base=None, zone=None):
	"""Costruisce tutti i vettori scaricabili/inviabili per un ref."""
	b, _s, z = _cfg()
	base = (base or b).rstrip("/")
	zone = zone or z
	q = "utm_content=" + ref
	return {
		"link": "%s/l?%s" % (base, q),
		"pixel": "%s/px?%s&via=img" % (base, q),
		"email_pixel": '<img src="%s/px?%s&via=email" width="1" height="1" style="display:none" alt="">' % (base, q),
		"pdf": "%s/scheda.pdf?%s" % (base, q),
		"docx": "%s/scheda.docx?%s" % (base, q),
		"xlsx": "%s/scheda.xlsx?%s" % (base, q),
		"qr_target": "%s/l?%s&via=qr" % (base, q),
		"redirect": "%s/l?%s" % (base, q),
		"dns_host": "%s.%s" % (ref, zone),
		"admin_hits": "%s/__hits?r=%s" % (base, ref),
	}


def _push_redir(ref, url, title=None, image=None, desc=None):
	"""Configura il redirect-esca sul worker: /l?utm_content=ref previewa (OG) e reindirizza a `url`."""
	base, secret, _z = _cfg()
	try:
		r = _http().post(
			"%s/__redir?k=%s" % (base, secret),
			json={"ref": ref, "url": url or "", "title": title or "", "image": image or "", "desc": desc or ""},
			headers=_UA, timeout=15,
		)
		return r.ok
	except Exception:
		frappe.log_error(frappe.get_traceback(), "canary._push_redir")
		return False


def _require():
	roles = set(frappe.get_roles())
	if not roles & {"System Manager", "Investigation Manager", "Investigator"}:
		frappe.throw(_("Non autorizzato"), frappe.PermissionError)


# ---------------------------------------------------------------------------
# Generazione token
# ---------------------------------------------------------------------------

@frappe.whitelist()
def generate(label, token_type="Link / Pagina", investigation_case=None, case_step=None,
			 recipient=None, redir_url=None, redir_title=None, notes=None, alert_on=1):
	_require()
	base, _s, _z = _cfg()
	ref = _new_ref()
	doc = frappe.get_doc({
		"doctype": "Canary Token",
		"label": label,
		"token_type": token_type,
		"ref": ref,
		"status": "Attivo",
		"investigation_case": investigation_case or None,
		"case_step": case_step or None,
		"recipient": recipient or None,
		"redir_url": redir_url or None,
		"redir_title": redir_title or None,
		"base_url": base,
		"alert_on": int(alert_on or 0),
		"notes": notes or None,
		"vectors": json.dumps(token_links(ref, base), indent=2),
	})
	doc.insert(ignore_permissions=True)
	if token_type == "Redirect-esca" and redir_url:
		_push_redir(ref, redir_url, title=redir_title)
	frappe.db.commit()
	return {"name": doc.name, "ref": ref, "links": token_links(ref, base)}


@frappe.whitelist()
def generate_batch(label, recipients, token_type="Word (.docx)", investigation_case=None, notes=None):
	"""Un token per destinatario (attribuzione fuga): consegni la STESSA esca a N persone, ref distinto
	per copia → quando fa phone-home sai CHI ha esfiltrato. `recipients` = lista o CSV/newline."""
	_require()
	if isinstance(recipients, str):
		recipients = [r.strip() for r in recipients.replace(",", "\n").splitlines() if r.strip()]
	out = []
	for rcpt in recipients:
		res = generate(label="%s — %s" % (label, rcpt), token_type=token_type,
					   investigation_case=investigation_case, recipient=rcpt, notes=notes)
		res["recipient"] = rcpt
		out.append(res)
	return out


@frappe.whitelist()
def set_redirect(ref, url, title=None, image=None, desc=None):
	_require()
	name = frappe.db.get_value("Canary Token", {"ref": ref}, "name")
	if not name:
		frappe.throw(_("Token non trovato"))
	frappe.db.set_value("Canary Token", name, {"redir_url": url, "redir_title": title})
	ok = _push_redir(ref, url, title=title, image=image, desc=desc)
	frappe.db.commit()
	return {"ok": ok}


@frappe.whitelist()
def disable(ref):
	_require()
	name = frappe.db.get_value("Canary Token", {"ref": ref}, "name")
	if name:
		frappe.db.set_value("Canary Token", name, "status", "Disattivato")
		frappe.db.commit()
	return {"ok": bool(name)}


@frappe.whitelist()
def list_tokens(investigation_case=None):
	_require()
	filters = {}
	if investigation_case:
		filters["investigation_case"] = investigation_case
	rows = frappe.get_all(
		"Canary Token", filters=filters,
		fields=["name", "label", "token_type", "ref", "status", "investigation_case",
				"recipient", "hit_count", "last_hit", "base_url"],
		order_by="modified desc", limit_page_length=500,
	)
	base, _s, _z = _cfg()
	for r in rows:
		r["links"] = token_links(r["ref"], r.get("base_url") or base)
	return {"base": base, "tokens": rows}


# ---------------------------------------------------------------------------
# Ingest hit (PULL dal worker Foxglove)
# ---------------------------------------------------------------------------

def _iso_to_dt(ts):
	try:
		s = str(ts).replace("Z", "").split(".")[0].replace("T", " ")
		return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
	except Exception:
		return frappe.utils.now_datetime()


def _hit_key(h):
	base = "%s|%s|%s|%s|%s|%s" % (
		h.get("ts", ""), h.get("ip", ""), h.get("type", ""),
		h.get("via", ""), h.get("r", ""), (h.get("path") or "")[:40])
	return frappe.utils.sha256_hash(base) if hasattr(frappe.utils, "sha256_hash") else \
		__import__("hashlib").sha256(base.encode()).hexdigest()


def _fetch_hits(ref=None):
	base, secret, _z = _cfg()
	url = "%s/__hits?k=%s&format=json&all=1" % (base, secret)
	if ref:
		url += "&r=" + ref
	r = _http().get(url, headers=_UA, timeout=25)
	r.raise_for_status()
	data = r.json()
	return data.get("hits", []) if isinstance(data, dict) else (data or [])


def _materialize_hit(h, tok):
	"""Crea un Canary Hit da un dict hit (formato worker __hits o payload push ALERT_URL).
	Ritorna il doc, o None se duplicato. NON committa (lo fa il chiamante)."""
	hk = _hit_key(h)
	if frappe.db.exists("Canary Hit", {"hit_key": hk}):
		return None
	asn, org = h.get("asn"), h.get("org")
	rtc = h.get("rtc") or h.get("webrtc")
	hit = frappe.get_doc({
		"doctype": "Canary Hit",
		"token": tok["name"],
		"investigation_case": tok.get("investigation_case") or None,
		"hit_ts": _iso_to_dt(h.get("ts")),
		"hit_type": h.get("type"),
		"via": h.get("via"),
		"ip": h.get("ip"),
		"suspect_net": _suspect_net(asn, org),
		"country": h.get("country"),
		"city": h.get("city"),
		"asn": str(asn or ""),
		"org": (org or "")[:140],
		"tz": h.get("tz"),
		"fp": h.get("fp"),
		"webrtc": rtc,
		"ua": h.get("ua"),
		"lat": frappe.utils.flt(h.get("lat")) if h.get("lat") not in (None, "") else None,
		"lon": frappe.utils.flt(h.get("lon")) if h.get("lon") not in (None, "") else None,
		"acc": frappe.utils.flt(h.get("acc")) if h.get("acc") not in (None, "") else None,
		"hit_key": hk,
		"raw": json.dumps(h),
	})
	hit.insert(ignore_permissions=True)
	return hit


def _refresh_token_counters(names):
	for name in names:
		agg = frappe.db.sql(
			"select count(*), max(hit_ts) from `tabCanary Hit` where token=%s", (name,))[0]
		frappe.db.set_value("Canary Token", name, {"hit_count": agg[0] or 0, "last_hit": agg[1]},
							update_modified=False)


@frappe.whitelist(allow_guest=True)
def ingest(k=None):
	"""Webhook PUSH: il worker Foxglove POSTa qui ogni hit (via ALERT_URL) → materializza subito il
	Canary Hit, senza dipendere dalla quota KV list. Real-time. Keyed su canary_secret."""
	_base, secret, _z = _cfg()
	if not k:
		k = frappe.form_dict.get("k") or frappe.request.args.get("k") if frappe.request else None
	if k != secret:
		frappe.local.response["http_status_code"] = 404
		return {"ok": False}
	try:
		body = frappe.request.get_data(as_text=True) if frappe.request else "{}"
		h = json.loads(body or "{}")
	except Exception:
		h = dict(frappe.form_dict)
	ref = h.get("r") or h.get("ref")
	tok = None
	if ref:
		row = frappe.db.get_value(
			"Canary Token", {"ref": ref},
			["name", "ref", "investigation_case", "alert_on", "status"], as_dict=True)
		tok = dict(row) if row else None
	if not tok:
		return {"ok": True, "new": 0}  # ref sconosciuto: 200 per non rivelare nulla al worker
	hit = _materialize_hit(h, tok)
	if hit:
		_refresh_token_counters([tok["name"]])
		frappe.db.commit()
		if tok.get("alert_on") and tok.get("investigation_case"):
			_alert_operator(tok, hit)
	return {"ok": True, "new": 1 if hit else 0}


@frappe.whitelist()
def pull_hits(ref=None, notify_new=1):
	"""Scarica gli hit dal worker (__hits list), materializza i nuovi Canary Hit, aggiorna i token,
	avvisa gli operatori. Backfill/riconciliazione — l'ingest real-time è via push `ingest`.
	Ritorna {new, total, tokens_touched}."""
	_require()
	return _pull(ref=ref, notify_new=int(notify_new or 0))


def pull_all_hits():
	"""Entrypoint scheduler (cron */10). Nessun controllo ruolo (gira come Administrator)."""
	_pull(ref=None, notify_new=1)


def _pull(ref=None, notify_new=1):
	# mappa ref → token (solo ref conosciuti vengono materializzati)
	tok_filters = {"ref": ref} if ref else {}
	tokens = {t["ref"]: t for t in frappe.get_all(
		"Canary Token", filters=tok_filters,
		fields=["name", "ref", "investigation_case", "alert_on", "status", "hit_count"])}
	if not tokens:
		return {"new": 0, "total": 0, "tokens_touched": 0}

	try:
		hits = _fetch_hits(ref=ref)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "canary._fetch_hits")
		return {"new": 0, "total": 0, "tokens_touched": 0, "error": "fetch"}

	new = 0
	touched = {}
	alerts = []
	for h in hits:
		tok = tokens.get(h.get("r"))
		if not tok:
			continue
		hit = _materialize_hit(h, tok)
		if not hit:
			continue
		new += 1
		touched[tok["name"]] = tok
		if notify_new and tok.get("alert_on") and tok.get("investigation_case"):
			alerts.append((tok, hit))

	_refresh_token_counters(touched)
	frappe.db.commit()

	for tok, hit in alerts:
		_alert_operator(tok, hit)

	return {"new": new, "total": len(hits), "tokens_touched": len(touched)}


def _alert_operator(tok, hit):
	try:
		from thanatos_intel.workflow import notify
		case = tok.get("investigation_case")
		flag = " ⚠ rete datacenter/VPN" if hit.get("suspect_net") else ""
		subject = "🎯 Canary: esca aperta (%s)" % (tok.get("ref"))
		msg = (
			"Un token-esca collegato a questa pratica è stato aperto.\n\n"
			"Token: %s (%s)\nTipo hit: %s / %s\nIP: %s%s\nGeo: %s %s · %s\nRete: AS%s %s\n"
			"User-Agent: %s\nQuando (UTC): %s"
		) % (
			tok.get("ref"), tok.get("name"), hit.get("hit_type"), hit.get("via") or "-",
			hit.get("ip"), flag, hit.get("country") or "", hit.get("city") or "", hit.get("tz") or "",
			hit.get("asn") or "", hit.get("org") or "", (hit.get("ua") or "")[:120], hit.get("hit_ts"),
		)
		notify._email_operator(case, subject, msg)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "canary._alert_operator")


# ---------------------------------------------------------------------------
# Lettura / dashboard
# ---------------------------------------------------------------------------

@frappe.whitelist()
def hits(ref=None, investigation_case=None, limit=200):
	_require()
	filters = {}
	if ref:
		name = frappe.db.get_value("Canary Token", {"ref": ref}, "name")
		filters["token"] = name or "__none__"
	if investigation_case:
		filters["investigation_case"] = investigation_case
	return frappe.get_all(
		"Canary Hit", filters=filters,
		fields=["name", "token", "investigation_case", "hit_ts", "hit_type", "via", "ip",
				"suspect_net", "country", "city", "asn", "org", "tz", "fp", "webrtc", "ua",
				"lat", "lon", "acc"],
		order_by="hit_ts desc", limit_page_length=frappe.utils.cint(limit))


@frappe.whitelist()
def dashboard(investigation_case=None):
	"""Riepilogo per il desk: token con hit + hit recenti + entity resolution per fingerprint."""
	_require()
	data = list_tokens(investigation_case)
	recent = hits(investigation_case=investigation_case, limit=100)
	# entity resolution: stessi fingerprint su più token/casi
	entities = {}
	for h in recent:
		fp = h.get("fp")
		if not fp:
			continue
		e = entities.setdefault(fp, {"fp": fp, "hits": 0, "tokens": set(), "cases": set(), "ips": set()})
		e["hits"] += 1
		e["tokens"].add(h.get("token"))
		if h.get("investigation_case"):
			e["cases"].add(h.get("investigation_case"))
		if h.get("ip"):
			e["ips"].add(h.get("ip"))
	ent = []
	for e in entities.values():
		ent.append({"fp": e["fp"], "hits": e["hits"], "tokens": sorted(e["tokens"]),
					"cases": sorted(e["cases"]), "ips": sorted(e["ips"]),
					"cross_case": len(e["cases"]) > 1})
	ent.sort(key=lambda x: (-int(x["cross_case"]), -x["hits"]))
	return {"base": data["base"], "tokens": data["tokens"], "recent_hits": recent, "entities": ent}
