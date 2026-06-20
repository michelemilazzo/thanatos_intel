import base64
import io

import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/portal/invita"
		raise frappe.Redirect

	from thanatos_intel import referral
	t = referral.my_tree(frappe.session.user)
	context.update(t)
	context.title = "Invita e guadagna — Thanatos"

	context.qr = None
	if t.get("link"):
		try:
			import qrcode
			img = qrcode.make(t["link"])
			buf = io.BytesIO()
			img.save(buf, format="PNG")
			context.qr = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
		except Exception:
			context.qr = None

	try:
		from frappe.sessions import get_csrf_token
		context.csrf_token = get_csrf_token()
	except Exception:
		context.csrf_token = ""
	context.no_cache = 1
	return context
