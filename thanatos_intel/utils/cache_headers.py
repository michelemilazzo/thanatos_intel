import frappe

# I 404/5xx transitori (deploy, restart, build) venivano serviti con
# `Cache-Control: private, max-age=300, stale-while-revalidate=120` ereditato
# dalle pagine sito. Risultato: un 404 transitorio restava inchiodato nel
# browser per ~5-7 minuti dopo che il sito era gia' tornato su ("la home si
# perde"). Su qualsiasi risposta non-200 forziamo no-store cosi' il browser
# ricarica appena l'origine torna sana.
#
# Va impostato sia su response.headers (re-serve da cache) sia su
# frappe.local.response_headers (layer website cache).


def after_request(response=None, request=None):
	try:
		if response is None or response.status_code == 200:
			return response
		no_store = "no-store, no-cache, must-revalidate, max-age=0"
		response.headers["Cache-Control"] = no_store
		try:
			frappe.local.response_headers["Cache-Control"] = no_store
		except Exception:
			pass
	except Exception:
		pass
	return response
