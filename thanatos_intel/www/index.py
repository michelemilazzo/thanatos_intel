import frappe

no_cache = 0


def get_context(context):
	context.no_cache = 0
	context.featured = frappe.get_all(
		"News Article",
		filters={"published": 1, "featured": 1},
		fields=["title", "slug", "excerpt", "featured_image", "category",
		        "published_at", "reading_time_min", "country_focus"],
		order_by="published_at desc",
		limit=3,
	)
	context.latest = frappe.get_all(
		"News Article",
		filters={"published": 1},
		fields=["title", "slug", "excerpt", "featured_image", "category",
		        "published_at", "reading_time_min", "source_name_label"],
		order_by="published_at desc",
		limit=9,
	)
	context.categories = frappe.get_all(
		"News Category",
		filters={"is_active": 1},
		fields=["category_name", "category_slug", "color", "icon", "description"],
		order_by="display_order asc",
		limit=8,
	)
	context.stats = _stats()
	return context


def _stats():
	out = {"cases": 0, "evidence": 0, "reports": 0, "osint": 0}
	try:
		out["cases"] = frappe.db.count("Investigation Case")
		out["evidence"] = frappe.db.count("Investigation Evidence")
		out["reports"] = frappe.db.count("Investigation Report")
	except Exception:
		pass
	try:
		out["osint"] = frappe.db.count("OSINT Lookup")
	except Exception:
		pass
	return out
