import frappe

no_cache = 0


def get_context(context):
    context.body_class = "thanatos-home"
	context.no_cache = 0
	context.featured = _safe_get_all(
		"News Article",
		filters={"published": 1, "featured": 1},
		fields=["title", "slug", "excerpt", "featured_image", "category",
		        "published_at", "reading_time_min", "country_focus"],
		order_by="published_at desc",
		limit=3,
	)
	context.latest = _safe_get_all(
		"News Article",
		filters={"published": 1},
		fields=["title", "slug", "excerpt", "featured_image", "category",
		        "published_at", "reading_time_min", "source_name_label"],
		order_by="published_at desc",
		limit=9,
	)
	context.categories = _safe_get_all(
		"News Category",
		filters={"is_active": 1},
		fields=["category_name", "category_slug", "color", "icon", "description"],
		order_by="display_order asc",
		limit=8,
	)
	context.stats = _stats()
	context.plans = _safe_get_all(
		"Investigation Subscription Plan",
		filters={"is_active": 1},
		fields=["name", "plan_name", "plan_level", "monthly_price", "currency",
		        "included_verifications", "included_analyses", "included_reports",
		        "max_users", "support_level"],
		order_by="monthly_price asc",
		limit=4,
	)
	return context


def _safe_get_all(doctype, **kwargs):
	try:
		if not frappe.db.exists("DocType", doctype):
			return []
		return frappe.get_all(doctype, **kwargs)
	except Exception:
		return []


def _stats():
	out = {"cases": 0, "evidence": 0, "reports": 0, "osint": 0, "news": 0, "clients": 0}
	mapping = [
		("Investigation Case", "cases", None),
		("Investigation Evidence", "evidence", None),
		("Investigation Report", "reports", None),
		("OSINT Lookup", "osint", None),
		("News Article", "news", {"published": 1}),
		("Investigation Client", "clients", None),
	]
	for doctype, key, flt in mapping:
		try:
			if not frappe.db.exists("DocType", doctype):
				continue
			out[key] = frappe.db.count(doctype, flt) if flt else frappe.db.count(doctype)
		except Exception:
			pass
	return out
