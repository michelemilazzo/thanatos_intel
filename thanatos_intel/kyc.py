# Copyright (c) 2026, MMOS and contributors
"""ThanatosKycProvider — aggancia il KYC personalizzato di Thanatos a mmos_sign.

Il KYC di Thanatos (Vault `Client Vault Item` + `Investigation Client` + tier
identità Base<KYC<KYB<KIT, vedi workflow/vault.py) è la fonte di verità: questo
provider lo espone tramite l'interfaccia generica `mmos_sign.kyc.base.KycProvider`,
così mmos_sign ci parla senza duplicare nulla. Registrato in
`Signing Settings.kyc_provider = thanatos_intel.kyc.ThanatosKycProvider`.
"""
import frappe
from frappe.utils import today

from mmos_sign.kyc.base import KycProvider
from thanatos_intel.workflow import vault

# Livelli di assurance mmos_sign -> tier identità Thanatos.
_LEVEL_TO_TIER = {"low": "Base", "substantial": "KYC", "high": "KYB"}


def _client_name(subject):
	"""Risolve il soggetto (email/user) all'Investigation Client."""
	if not subject:
		return None
	return frappe.db.get_value("Investigation Client", {"platform_user": subject}, "name") \
		or frappe.db.get_value("Investigation Client", {"email": subject}, "name")


class ThanatosKycProvider(KycProvider):
	def record(self, subject, identity, **opts):
		client = _client_name(subject)
		if not client:
			frappe.log_error(
				f"ThanatosKycProvider.record: nessun Investigation Client per {subject}",
				"thanatos kyc")
			return None
		label = identity.get("full_name") or identity.get("doc_number") or "documento"
		item = frappe.get_doc({
			"doctype": "Client Vault Item",
			"client": client,
			"doc_kind": "KYC",
			"title": f"{opts.get('method', 'NFC-eID')} — {label}",
			"status": "Valido",
			"valid_until": identity.get("expiry") or None,
			"verified_on": today(),
			"notes": "Verifica identità automatica via mmos_sign (assurance: %s, passive_auth: %s)."
			         % (opts.get("assurance_level", "low"), bool(opts.get("passive_auth"))),
		}).insert(ignore_permissions=True)
		frappe.db.set_value("Investigation Client", client, "kyc_status", "Passed")
		return item.name

	def get_status(self, subject):
		client = _client_name(subject)
		if not client:
			return {"verified": False, "level": None}
		ok = vault.tier_satisfied(client, "KYC")
		return {"verified": bool(ok), "level": "substantial" if ok else None, "client": client}

	def tier_satisfied(self, subject, tier):
		if not tier or tier == "Base":
			return True
		client = _client_name(subject)
		if not client:
			return False
		thanatos_tier = _LEVEL_TO_TIER.get(tier, tier)  # passa-attraverso KYC/KYB/KIT
		return bool(vault.tier_satisfied(client, thanatos_tier))
