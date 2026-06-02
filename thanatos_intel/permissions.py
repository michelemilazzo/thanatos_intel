import frappe

# Ruoli operativi della piattaforma (allineati al contratto MMOS-THANATOS-2026-001)
READ_ROLES = (
	"System Manager",
	"Investigation Manager",
	"Investigator",
	"Lawyer",
	"Accountant",
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


def has_thanatos_role(*roles):
	user_roles = set(frappe.get_roles())
	return bool(user_roles.intersection(roles))


def can_read_thanatos_doc(doc, user=None):
	# Administrator e ruoli di lettura: accesso consentito (filtri riga-per-riga nei blocchi successivi)
	if (user or frappe.session.user) == "Administrator":
		return True
	return has_thanatos_role(*READ_ROLES)


def can_write_thanatos_doc(doc, user=None):
	if (user or frappe.session.user) == "Administrator":
		return True
	return has_thanatos_role(*WRITE_ROLES)


def can_supervise_thanatos_doc(doc, user=None):
	if (user or frappe.session.user) == "Administrator":
		return True
	return has_thanatos_role(*SUPERVISOR_ROLES)
