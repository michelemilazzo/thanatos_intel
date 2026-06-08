from frappe import _


def get_data():
	return {
		"fieldname": "ddd_case",
		"transactions": [
			{
				"label": _("Mandato & Fatturazione"),
				"items": ["Agency Mandate", "Diplomatic Proforma"],
			},
			{
				"label": _("Compliance & Verifica"),
				"items": [
					"Sanctions Screening",
					"Compliance Check",
					"Video Verification Session",
				],
			},
		],
	}
