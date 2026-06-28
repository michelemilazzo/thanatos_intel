import frappe

no_cache = 1


def get_context(context):
    # Microsoft redirige qui con ?code=...&state=... oppure ?error=...
    code  = frappe.request.args.get("code")
    state = frappe.request.args.get("state")
    error = frappe.request.args.get("error")

    from thanatos_intel.api.mail_connectors import microsoft_oauth_finish
    # microsoft_oauth_finish fa raise frappe.Redirect internamente
    microsoft_oauth_finish(code=code, state=state, error=error)
