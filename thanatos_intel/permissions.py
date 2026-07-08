"""Thanatos Intel — permessi row-level.

Modello richiesto:
  - FULL ACCESS (vede tutto): Administrator + System Manager + Investigation Manager
  - Investigator: solo i casi a lui ASSEGNATI (assigned_investigator) o di cui è owner
  - Lawyer / Accountant: solo i casi dei propri client collegati o assegnati/owner
  - Client (portale): solo i casi dei propri Investigation Client (platform_user)

Implementato come:
  - permission_query_conditions  → filtro SQL row-level nelle liste/report Desk
  - has_permission               → check puntuale su singolo documento
  - helper visible_case_names()  → usato anche dai portali web per coerenza
"""
import frappe

# Ruoli operativi
READ_ROLES = (
	"System Manager",
	"Investigation Manager",
	"Investigator",
	"Lawyer",
	"Accountant",
	"WalletSaaS Read",   # integrazione wallet-saas: sola lettura casi (import wallet)
)
WRITE_ROLES = (
	"System Manager",
	"Investigation Manager",
	"Investigator",
)
SUPERVISOR_ROLES = (
	"System Manager",
	"Investigation Manager",
)
# Chi vede TUTTO, senza filtro row-level
FULL_ACCESS_ROLES = (
	"System Manager",
	"Investigation Manager",
	"WalletSaaS Read",   # integrazione wallet-saas: lettura completa (import wallet dai casi)
)


def has_thanatos_role(*roles):
	return bool(set(frappe.get_roles()).intersection(roles))


def is_full_access(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)).intersection(FULL_ACCESS_ROLES))


# ---------------------------------------------------------------------------
# Scope computation: quali casi può vedere un utente non-full-access
# ---------------------------------------------------------------------------

def _investigator_records(user):
	"""Nomi dei record Investigator collegati a questo user (platform_user)."""
	return frappe.get_all("Investigator",
		filters={"platform_user": user}, pluck="name") or []


def _client_records(user):
	"""Nomi degli Investigation Client collegati a questo user (platform_user)."""
	return frappe.get_all("Investigation Client",
		filters={"platform_user": user}, pluck="name") or []


def visible_case_names(user=None):
	"""Lista (deduplicata) dei nomi Investigation Case visibili all'utente.

	Restituisce None se l'utente ha FULL ACCESS (nessun filtro → tutto).
	"""
	user = user or frappe.session.user
	if is_full_access(user):
		return None

	names = set()
	# 1. casi di cui è owner
	names.update(frappe.get_all("Investigation Case",
		filters={"owner": user}, pluck="name") or [])
	# 2. casi a lui assegnati come investigatore
	investigators = _investigator_records(user)
	if investigators:
		names.update(frappe.get_all("Investigation Case",
			filters={"assigned_investigator": ["in", investigators]},
			pluck="name") or [])
	# 3. casi dei propri client (lawyer/accountant/client portal)
	clients = _client_records(user)
	if clients:
		names.update(frappe.get_all("Investigation Case",
			filters={"client": ["in", clients]}, pluck="name") or [])
	return list(names)


def _sql_in(values):
	"""Costruisce la clausola SQL (a,b,c) sanitizzata. Lista vuota → (NULL)."""
	if not values:
		return "(NULL)"
	escaped = ", ".join(frappe.db.escape(v) for v in values)
	return f"({escaped})"


# ---------------------------------------------------------------------------
# permission_query_conditions — uno per DocType
# ---------------------------------------------------------------------------

def case_query_conditions(user=None):
	user = user or frappe.session.user
	if is_full_access(user):
		return ""
	names = visible_case_names(user)
	return f"`tabInvestigation Case`.name in {_sql_in(names)}"


def client_query_conditions(user=None):
	user = user or frappe.session.user
	if is_full_access(user):
		return ""
	clients = _client_records(user)
	# include anche i client dei casi assegnati (investigator deve vedere il cliente del caso)
	names = visible_case_names(user)
	if names:
		case_clients = frappe.get_all("Investigation Case",
			filters={"name": ["in", names]}, pluck="client") or []
		clients = list(set(clients) | set(c for c in case_clients if c))
	return f"`tabInvestigation Client`.name in {_sql_in(clients)}"


def osint_job_query_conditions(user=None):
	user = user or frappe.session.user
	if is_full_access(user):
		return ""
	names = visible_case_names(user)
	# OSINT Job visibile se: richiesto da me, o legato a un mio caso, o a un mio client
	clients = _client_records(user)
	clauses = [f"`tabOSINT Job`.requested_by = {frappe.db.escape(user)}"]
	if names:
		clauses.append(f"`tabOSINT Job`.investigation_case in {_sql_in(names)}")
	if clients:
		clauses.append(f"`tabOSINT Job`.client in {_sql_in(clients)}")
	return "(" + " or ".join(clauses) + ")"


def _child_of_case_conditions(doctype, user):
	"""Condizione generica per DocType figli del caso (campo investigation_case)."""
	if is_full_access(user):
		return ""
	names = visible_case_names(user)
	return f"`tab{doctype}`.investigation_case in {_sql_in(names)}"


def evidence_query_conditions(user=None):
	return _child_of_case_conditions("Investigation Evidence",
		user or frappe.session.user)


def report_query_conditions(user=None):
	return _child_of_case_conditions("Investigation Report",
		user or frappe.session.user)


# ---------------------------------------------------------------------------
# has_permission — check puntuale per documento
# ---------------------------------------------------------------------------

def _user_can_see_case(case_name, user):
	if not case_name:
		return True
	names = visible_case_names(user)
	if names is None:
		return True
	return case_name in names


def can_read_thanatos_doc(doc, user=None):
	"""has_permission per Investigation Case e doc con campo investigation_case."""
	user = user or frappe.session.user
	if is_full_access(user):
		return True
	if not has_thanatos_role(*READ_ROLES) and not _client_records(user):
		# nessun ruolo né client collegato → niente
		return False
	# determina il caso di riferimento
	dt = getattr(doc, "doctype", None)
	if dt == "Investigation Case":
		return _user_can_see_case(doc.name, user)
	case_ref = getattr(doc, "investigation_case", None)
	if case_ref:
		return _user_can_see_case(case_ref, user)
	return True


def can_read_osint_job(doc, user=None):
	user = user or frappe.session.user
	if is_full_access(user):
		return True
	if getattr(doc, "requested_by", None) == user:
		return True
	case_ref = getattr(doc, "investigation_case", None)
	if case_ref and _user_can_see_case(case_ref, user):
		return True
	if getattr(doc, "client", None) in _client_records(user):
		return True
	return False


def can_read_client(doc, user=None):
	user = user or frappe.session.user
	if is_full_access(user):
		return True
	if getattr(doc, "platform_user", None) == user:
		return True
	if getattr(doc, "name", None):
		# visibile se ho un caso con questo client
		names = visible_case_names(user)
		if names:
			cl = frappe.get_all("Investigation Case",
				filters={"name": ["in", names], "client": doc.name}, limit=1)
			return bool(cl)
	return False


# ---------------------------------------------------------------------------
# Write / supervise (invariati)
# ---------------------------------------------------------------------------

def can_write_thanatos_doc(doc, user=None):
	if (user or frappe.session.user) == "Administrator":
		return True
	if not has_thanatos_role(*WRITE_ROLES):
		return False
	return can_read_thanatos_doc(doc, user)


def can_supervise_thanatos_doc(doc, user=None):
	if (user or frappe.session.user) == "Administrator":
		return True
	return has_thanatos_role(*SUPERVISOR_ROLES)
