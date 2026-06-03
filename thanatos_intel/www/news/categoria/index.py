import frappe


def get_context(context):
	slug = frappe.form_dict.get("slug") or ""
	cat = frappe.db.get_value("News Category", {"category_slug": slug},
	                          ["name", "category_name", "color", "description", "category_slug"],
	                          as_dict=True)
	if not cat:
		frappe.local.flags.redirect_location = "/news"
		raise frappe.Redirect
	context.category = cat
	context.articles = frappe.get_all(
		"News Article",
		filters={"published": 1, "category": cat.name},
		fields=["title", "slug", "excerpt", "featured_image", "published_at",
		        "reading_time_min", "source_name_label"],
		order_by="published_at desc",
		limit=30,
	)
	context.parents = [{"label": "Home", "route": "/"}, {"label": "News", "route": "/news"}]
	return context
