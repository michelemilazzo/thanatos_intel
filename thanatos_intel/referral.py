"""Thanatos Intel — referral / invita-amico + albero registrazioni + commissioni.

Modello:
  - Ogni Investigation Client ha un codice personale `my_referral_code` (condivisibile)
    e un `referred_by` (Link a Investigation Client) = chi lo ha portato (L1).
  - L'albero è la catena ricorsiva su `referred_by`. Commissioni a 2 livelli:
      L1 = chi invita direttamente, L2 = chi ha invitato l'invitante.
  - Ricompensa allo spendere del referee (Usage Event):
      * referrer COLLABORATORE (Affiliate Application) -> Commission (payout monetario)
      * referrer CLIENTE normale                       -> Earned (credito servizi)
  - Percentuali configurabili in site_config (default sotto).
"""
import frappe
from frappe.utils import flt, now_datetime, get_url

# default % (override in site_config thanatos)
DEF = {
	"welcome_bonus_eur": 25.0,         # credito a ogni nuovo iscritto
	"referral_signup_bonus_eur": 10.0, # credito a chi ha segnalato (registrazione)
	"referral_l1_pct": 10.0,           # collaboratore, % su spesa, livello 1
	"referral_l2_pct": 3.0,            # collaboratore, % su spesa, livello 2
	"referral_client_l1_pct": 0.0,     # cliente: reward = flat alla registrazione
	"referral_client_l2_pct": 0.0,
}


def _pct(key):
	v = frappe.conf.get(key)
	return flt(v) if v not in (None, "") else DEF[key]


# ---------------- identità / codice ----------------

def _client_for_user(user=None):
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("Investigation Client", {"platform_user": user}, "name")


def _gen_code(client_name):
	base = (frappe.scrub(client_name or "ref").replace("_", ""))[:10] or "ref"
	for _ in range(6):
		code = (base + frappe.generate_hash(length=4)).lower()[:16]
		if not frappe.db.exists("Investigation Client", {"my_referral_code": code}):
			return code
	return frappe.generate_hash(length=12)


def get_or_create_code(client):
	code = frappe.db.get_value("Investigation Client", client, "my_referral_code")
	if code:
		return code
	cname = frappe.db.get_value("Investigation Client", client, "client_name")
	code = _gen_code(cname)
	frappe.db.set_value("Investigation Client", client, "my_referral_code", code, update_modified=False)
	return code


def my_code(user=None):
	c = _client_for_user(user)
	return get_or_create_code(c) if c else None


def referral_link(user=None):
	code = my_code(user)
	return (get_url() + "/registrati?ref=" + code) if code else None


def resolve_referrer(code):
	"""Investigation Client name del referrer dal codice, o None."""
	code = (code or "").strip().lower()
	if not code:
		return None
	c = frappe.db.get_value("Investigation Client", {"my_referral_code": code}, "name")
	if c:
		return c
	# compat: vecchio codice collaboratore = scrub(applicant_name)[:24]
	for aff in frappe.get_all("Affiliate Application", fields=["applicant_name", "email"]):
		legacy = frappe.scrub(aff.applicant_name or "")[:24].replace("_", "-")
		if legacy and legacy == code:
			return (frappe.db.get_value("Investigation Client", {"platform_user": aff.email}, "name")
				or frappe.db.get_value("Investigation Client", {"email": aff.email}, "name"))
	return None


def _is_collaborator(email):
	return bool(email and frappe.db.exists("Affiliate Application", {"email": email}))


# ---------------- registrazione referee ----------------

def record_registration(new_client, code):
	"""Imposta referred_by sul nuovo cliente e segna l'invito come registrato."""
	ref = resolve_referrer(code)
	if ref and ref != new_client:
		frappe.db.set_value("Investigation Client", new_client, "referred_by", ref, update_modified=False)
	email = frappe.db.get_value("Investigation Client", new_client, "email")
	if email:
		inv = frappe.db.get_value("Referral Invite",
			{"invitee_email": (email or "").lower(), "status": "Sent"}, "name")
		if inv:
			frappe.db.set_value("Referral Invite", inv,
				{"status": "Registered", "registered_client": new_client})
	_grant_signup_bonuses(new_client, ref)
	return ref


def _grant_signup_bonuses(new_client, ref):
	"""25E di benvenuto al nuovo iscritto + 10E al referrer (una-tantum, idempotente)."""
	from thanatos_intel.billing.credits import grant_credit
	welcome = _pct("welcome_bonus_eur")
	rn = "%s:welcome" % new_client
	if welcome > 0 and not _ref_exists(rn):
		grant_credit(new_client, welcome, "Investigation Client", rn, "Bonus di benvenuto")
	if ref and ref != new_client:
		rb = _pct("referral_signup_bonus_eur")
		rn2 = "%s:referrer" % new_client
		if rb > 0 and not _ref_exists(rn2):
			child = frappe.db.get_value("Investigation Client", new_client, "client_name") or new_client
			grant_credit(ref, rb, "Investigation Client", rn2, "Bonus segnalazione: %s" % child)


# ---------------- ricompensa su spesa (Credit Ledger "Spent") ----------------

def on_credit_spent(doc, method=None):
	"""Quando un cliente spende (revenue reale), accredita la catena referral L1/L2."""
	try:
		if getattr(doc, "kind", None) != "Spent" or getattr(doc, "party_type", None) != "Client":
			return
		_reward_spend(doc.party, flt(doc.amount), doc.name,
			getattr(doc, "reference_doctype", None), getattr(doc, "reference_name", None))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "referral reward failed")


def _ref_exists(rn):
	return bool(frappe.db.exists("Credit Ledger", {"reference_name": rn}))


def _reward_spend(client, amount, ledger_name, ref_dt=None, ref_dn=None):
	if amount <= 0 or not client:
		return
	l1 = frappe.db.get_value("Investigation Client", client, "referred_by")
	if not l1:
		return
	if ref_dt == "Usage Event" and ref_dn and not frappe.db.get_value("Usage Event", ref_dn, "referred_by"):
		frappe.db.set_value("Usage Event", ref_dn, "referred_by", l1, update_modified=False)
	l2 = frappe.db.get_value("Investigation Client", l1, "referred_by")
	_pay(l1, amount, "L1", ledger_name)
	if l2 and l2 != l1 and l2 != client:
		_pay(l2, amount, "L2", ledger_name)


def _pay(referrer_client, base_amount, level, ledger_name):
	rn = "%s:%s" % (ledger_name, level)
	email = (frappe.db.get_value("Investigation Client", referrer_client, "platform_user")
		or frappe.db.get_value("Investigation Client", referrer_client, "email"))
	if _is_collaborator(email):
		pct = _pct("referral_l1_pct") if level == "L1" else _pct("referral_l2_pct")
		amt = round(base_amount * pct / 100.0, 2)
		if amt > 0:
			from thanatos_intel.billing.credits import credit_commission
			credit_commission("Collaborator", email, amt, "Credit Ledger", rn, "Commissione referral %s" % level)
	else:
		pct = _pct("referral_client_l1_pct") if level == "L1" else _pct("referral_client_l2_pct")
		amt = round(base_amount * pct / 100.0, 2)
		if amt > 0 and not _ref_exists(rn):
			from thanatos_intel.billing.credits import grant_credit
			grant_credit(referrer_client, amt, "Credit Ledger", rn, "Bonus referral %s" % level)

# ---------------- albero + guadagni (per il portale) ----------------

def _node(name):
	d = frappe.db.get_value("Investigation Client", name,
		["client_name", "creation", "subscription_status", "total_spent"], as_dict=True) or {}
	d["name"] = name
	return d


def my_tree(user=None):
	user = user or frappe.session.user
	c = _client_for_user(user)
	empty = {"code": None, "link": None, "l1": [], "l2": [], "invites": [],
		"earned": 0, "pending": 0, "paid": 0, "is_collaborator": False}
	if not c:
		return empty
	code = get_or_create_code(c)
	l1 = []
	for r in frappe.get_all("Investigation Client", filters={"referred_by": c},
			fields=["name", "client_name", "creation", "subscription_status", "total_spent"],
			order_by="creation desc"):
		r["sub_count"] = frappe.db.count("Investigation Client", {"referred_by": r["name"]})
		l1.append(r)
	l2 = []
	for r in l1:
		for s in frappe.get_all("Investigation Client", filters={"referred_by": r["name"]},
				fields=["name", "client_name", "creation", "total_spent"],
				order_by="creation desc"):
			s["via"] = r["client_name"]
			l2.append(s)
	invites = frappe.get_all("Referral Invite",
		filters={"referrer_client": c, "status": "Sent"},
		fields=["invitee_name", "invitee_email", "channel", "sent_at"],
		order_by="sent_at desc", limit=50)

	from thanatos_intel.billing.credits import party_earnings
	is_collab = _is_collaborator(user)
	if is_collab:
		e = party_earnings("Collaborator", user)
		earned, pending, paid = e["earned"], e["pending"], e["paid"]
	else:
		rows = frappe.get_all("Credit Ledger",
			filters={"party_type": "Client", "party": c, "kind": "Earned"},
			fields=["amount", "reference_name"])
		earned = sum(flt(x.amount) for x in rows if (x.reference_name or "").endswith((":L1", ":L2", ":referrer")))
		pending, paid = 0, earned
	return {"code": code, "link": referral_link(user), "l1": l1, "l2": l2,
		"invites": invites, "earned": flt(earned), "pending": flt(pending),
		"paid": flt(paid), "is_collaborator": is_collab}


# ---------------- inviti ----------------

@frappe.whitelist()
def create_invite(invitee_name=None, invitee_email=None, channel="Link", send_email=0):
	c = _client_for_user()
	if not c:
		frappe.throw("Serve un profilo cliente per invitare.")
	code = get_or_create_code(c)
	email = (invitee_email or "").strip().lower()
	if email and "@" not in email:
		frappe.throw("Email non valida.")
	doc = frappe.get_doc({
		"doctype": "Referral Invite",
		"referrer_client": c,
		"referrer_user": frappe.session.user,
		"invitee_name": (invitee_name or "")[:140],
		"invitee_email": email,
		"referral_code": code,
		"channel": channel if channel in ("Link", "Email", "QR") else "Link",
		"status": "Sent",
		"sent_at": now_datetime(),
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	sent = False
	if int(send_email or 0) and email:
		sent = _send_invite_email(email, invitee_name, code, c)
	return {"ok": True, "invite": doc.name, "email_sent": sent, "link": referral_link()}


def _send_invite_email(email, name, code, referrer_client):
	try:
		referrer_name = frappe.db.get_value("Investigation Client", referrer_client, "client_name") or "un utente Thanatos"
		link = get_url() + "/registrati?ref=" + code
		subject = "%s ti invita su Thanatos Intel" % referrer_name
		msg = (
			"<p>Ciao %s,</p>" % (frappe.utils.escape_html(name or "")) +
			"<p><b>%s</b> ti invita a registrarti su Thanatos Intel, "
			"la piattaforma di intelligence investigativa europea.</p>"
			"<p><a href=\"%s\" style=\"display:inline-block;padding:12px 22px;background:#C8A96E;"
			"color:#0A0E1A;text-decoration:none;border-radius:6px;font-weight:600\">"
			"Registrati ora</a></p>"
			"<p>oppure copia questo link:<br><a href=\"%s\">%s</a></p>" % (link, link, link)
		)
		frappe.sendmail(recipients=[email], subject=subject, message=msg, now=True)
		return True
	except Exception:
		frappe.log_error(frappe.get_traceback(), "referral invite email failed")
		return False
