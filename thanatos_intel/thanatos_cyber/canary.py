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
		"page": "%s/?%s" % (base, q),  # homepage blog: carica b.js → fingerprint + WebRTC de-anon (VPN-proof). Vettore attribuzione forte.
		"link": "%s/l?%s" % (base, q),
		"pixel": "%s/px?%s&via=img" % (base, q),
		"email_pixel": '<img src="%s/px?%s&via=email" width="1" height="1" style="display:none" alt="">' % (base, q),
		"pdf": "%s/scheda.pdf?%s" % (base, q),
		"docx": "%s/scheda.docx?%s" % (base, q),
		"xlsx": "%s/scheda.xlsx?%s" % (base, q),
		"qr_target": "%s/l?%s&via=qr" % (base, q),
		"redirect": "%s/l?%s" % (base, q),
		"dns_host": "%s.%s" % (ref, zone),
		"login": "%s/login?%s" % (base, q),          # honeypot credenziale-esca: chi PROVA le creds piantate viene loggato
		"api": "%s/api/v1/me?api_key=%s" % (base, ref),  # honeypot endpoint: uso della "chiave API" piantata = alert
		"admin_hits": "%s/__hits?r=%s" % (base, ref),
	}


def planted_creds(ref, base=None):
	"""Credenziali-esca DETERMINISTICHE dal ref (ricostruibili, niente storage). Sono i valori finti che
	l'operatore pianta sul device del cliente: se il device è compromesso e un malware le esfiltra e le
	PROVA contro l'honeypot, l'hit viene loggato e attribuito a questo token."""
	import hashlib
	b, secret, _z = _cfg()
	L = token_links(ref, base or b)
	pw = hashlib.sha256((ref + secret).encode()).hexdigest()[:14]
	return {
		"credential": {"login_url": L["login"], "username": "reader_" + ref[:6], "password": pw},
		"honeypot": {"api_url": L["api"], "api_key": ref, "authorization": "Bearer " + ref},
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
	out = {"name": doc.name, "ref": ref, "links": token_links(ref, base)}
	if token_type in ("Credenziale-esca", "Endpoint honeypot"):
		out["planted"] = planted_creds(ref, base)
	return out


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


# Kit consensuale "il mio device è sotto controllo di terzi?" — counter-surveillance dimostrativa.
# Il cliente (o l'operatore, sul device del CLIENTE col suo consenso) pianta esche credibili: se un terzo
# che controlla/monitora il device le apre / le prova / le esfiltra, l'hit fa phone-home → PROVA che il
# device è sorvegliato + attribuzione del watcher (IP reale, geo, device). Solo device del cliente,
# consensuale, su mandato. NON è accesso a dispositivi di terzi.
_DEVICE_KIT_PLAN = [
	("Credenziale-esca", "🔑 Login «salvato»",
	 "Salva queste credenziali nel gestore password / login del browser sul device. Uno stalkerware che "
	 "ruba le password salvate proverà a usarle → cattura del watcher."),
	("Word (.docx)", "📄 Documento «riservato»",
	 "Metti il file sul device con un nome allettante (es. «accessi_banca.docx», «seed_wallet.docx»). "
	 "Chi esfiltra i file e lo apre → phone-home con IP/rete reali."),
	("Link / Pagina", "🔗 Nota/Link «riservato»",
	 "Incolla il link in una nota/chat sul device (es. «accesso conto: <link>»). Chi legge lo schermo o "
	 "le note e lo apre → de-anon: IP reale, fingerprint, WebRTC anche dietro VPN."),
	("Endpoint honeypot", "🔌 Chiave API «esca»",
	 "Metti la chiave in un file tipo .env o negli appunti. Chi la trova e la usa contro l'endpoint → alert."),
]


@frappe.whitelist()
def device_check_kit(label, investigation_case=None):
	"""Genera un bundle di esche per verificare (in modo dimostrativo e consensuale) se il device del
	cliente è sotto controllo di terzi. Ogni esca è legata alla pratica; il Dossier attribuisce il watcher."""
	_require()
	base, _s, _z = _cfg()
	kit = []
	for ttype, title, instr in _DEVICE_KIT_PLAN:
		res = generate(label="Verifica device · %s · %s" % (label, title), token_type=ttype,
					   investigation_case=investigation_case, recipient=label,
					   notes="Kit verifica dispositivo (counter-surveillance consensuale)")
		kit.append({"title": title, "instruction": instr, "ref": res["ref"],
					"token_type": ttype, "links": res["links"], "planted": res.get("planted")})
	return {"label": label, "case": investigation_case, "base": base, "kit": kit}


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
		if r.get("token_type") in ("Credenziale-esca", "Endpoint honeypot"):
			r["planted"] = planted_creds(r["ref"], r.get("base_url") or base)
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
		"attempt_user": h.get("attempt_user"),
		"attempt_secret": h.get("attempt_secret"),
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
				"attempt_user", "attempt_secret", "lat", "lon", "acc"],
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


def _is_private_ip(ip):
	ip = (ip or "").strip()
	if not ip:
		return True
	if ip.startswith(("10.", "192.168.", "127.", "169.254.", "::1", "fc", "fd", "fe80")):
		return True
	if ip.startswith("172."):
		try:
			return 16 <= int(ip.split(".")[1]) <= 31
		except Exception:
			return False
	return False


def _webrtc_public(webrtc):
	"""Estrae gli IP pubblici REALI dai candidati WebRTC ('ip:typ ip:typ'). srflx = server-reflexive =
	IP pubblico reale (rivelato anche dietro VPN in-browser); host privati = LAN, scartati."""
	out = []
	for tokn in (webrtc or "").replace(",", " ").split():
		parts = tokn.split(":")
		if parts[-1] in ("srflx", "host", "prflx", "relay"):
			typ, ip = parts[-1], ":".join(parts[:-1])
		else:
			typ, ip = "", tokn
		if _is_private_ip(ip):
			continue
		if typ in ("srflx", "prflx", "") and ip not in out:  # pubblici reali (VPN-proof)
			out.append(ip)
	return out


@frappe.whitelist()
def dossier(ref):
	"""Fascicolo de-anon per un token (caso ATTRIBUZIONE): distingue IP residenziale vs datacenter/VPN,
	estrae gli IP pubblici reali da WebRTC (VPN-proof), i fingerprint device (+ cross-caso), GPS, timeline,
	e un best-guess dell'IP/identità reale."""
	_require()
	tok = frappe.db.get_value(
		"Canary Token", {"ref": ref},
		["name", "label", "token_type", "ref", "investigation_case", "recipient", "hit_count", "last_hit"],
		as_dict=True)
	if not tok:
		frappe.throw(_("Token non trovato"))
	tok = dict(tok)
	rows = frappe.get_all(
		"Canary Hit", filters={"token": tok["name"]},
		fields=["hit_ts", "hit_type", "via", "ip", "suspect_net", "country", "city", "asn", "org",
				"tz", "fp", "webrtc", "ua", "attempt_user", "attempt_secret", "lat", "lon", "acc"],
		order_by="hit_ts desc", limit_page_length=1000)

	residential, datacenter, webrtc_ips = {}, {}, {}
	fps, gps, attempts = {}, [], []
	for h in rows:
		if h.get("hit_type") in ("credential", "honeypot") or h.get("attempt_user") or h.get("attempt_secret"):
			attempts.append({"ts": h.get("hit_ts"), "type": h.get("hit_type"), "ip": h.get("ip"),
							 "suspect_net": h.get("suspect_net"), "org": h.get("org"),
							 "user": h.get("attempt_user"), "secret": h.get("attempt_secret"),
							 "ua": h.get("ua")})
		ip = h.get("ip")
		if ip:
			bucket = datacenter if h.get("suspect_net") else residential
			b = bucket.setdefault(ip, {"ip": ip, "hits": 0, "country": h.get("country"),
									   "city": h.get("city"), "asn": h.get("asn"), "org": h.get("org")})
			b["hits"] += 1
		for wip in _webrtc_public(h.get("webrtc")):
			webrtc_ips.setdefault(wip, {"ip": wip, "hits": 0})["hits"] += 1
		fp = h.get("fp")
		if fp:
			f = fps.setdefault(fp, {"fp": fp, "hits": 0, "ips": set(), "ua": h.get("ua")})
			f["hits"] += 1
			if h.get("ip"):
				f["ips"].add(h.get("ip"))
		if h.get("lat") and h.get("lon"):
			gps.append({"lat": h.get("lat"), "lon": h.get("lon"), "acc": h.get("acc"), "ts": h.get("hit_ts")})

	# cross-caso: gli stessi fingerprint appaiono su altri token/casi?
	fp_list = []
	for fp, f in fps.items():
		also = frappe.get_all("Canary Hit", filters={"fp": fp, "token": ["!=", tok["name"]]},
							  fields=["token", "investigation_case"], limit_page_length=200)
		also_cases = sorted({a["investigation_case"] for a in also if a.get("investigation_case")})
		also_tokens = sorted({a["token"] for a in also})
		fp_list.append({"fp": fp, "hits": f["hits"], "ua": f["ua"], "ips": sorted(f["ips"]),
						"also_tokens": also_tokens, "also_cases": also_cases,
						"cross_case": bool(also_cases)})
	fp_list.sort(key=lambda x: (-int(x["cross_case"]), -x["hits"]))

	res_sorted = sorted(residential.values(), key=lambda x: -x["hits"])
	dc_sorted = sorted(datacenter.values(), key=lambda x: -x["hits"])
	wrtc_sorted = sorted(webrtc_ips.values(), key=lambda x: -x["hits"])

	# best-guess IP reale: WebRTC pubblico (più forte, VPN-proof) > IP residenziale più frequente
	best_ip, best_src = None, None
	if wrtc_sorted:
		best_ip, best_src = wrtc_sorted[0]["ip"], "webrtc"
	elif res_sorted:
		best_ip, best_src = res_sorted[0]["ip"], "residential"
	elif dc_sorted:
		best_ip, best_src = dc_sorted[0]["ip"], "datacenter"

	return {
		"token": tok,
		"summary": {
			"total_hits": len(rows),
			"residential_ips": len(res_sorted),
			"datacenter_vpn_ips": len(dc_sorted),
			"webrtc_public_ips": len(wrtc_sorted),
			"devices": len(fp_list),
			"cross_case_devices": sum(1 for f in fp_list if f["cross_case"]),
			"gps_points": len(gps),
			"credential_attempts": len(attempts),
			"best_guess_ip": best_ip,
			"best_guess_source": best_src,
			"behind_vpn": bool(dc_sorted) and not res_sorted,
		},
		"residential_ips": res_sorted,
		"datacenter_vpn_ips": dc_sorted,
		"webrtc_public_ips": wrtc_sorted,
		"devices": fp_list,
		"credential_attempts": attempts,
		"gps": gps,
		"timeline": rows,
	}
