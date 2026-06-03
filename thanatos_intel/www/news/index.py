import frappe


def get_context(context):
	page = max(1, int(frappe.form_dict.get("page") or 1))
	per = 12
	q = (frappe.form_dict.get("q") or "").strip()
	cat = (frappe.form_dict.get("cat") or "").strip()
	filters = {"published": 1}
	if cat:
		filters["category"] = cat
	or_filters = None
	if q:
		or_filters = [["title", "like", f"%{q}%"], ["excerpt", "like", f"%{q}%"],
		              ["tags", "like", f"%{q}%"]]
	total = frappe.db.count("News Article", filters=filters)
	context.articles = frappe.get_all(
		"News Article", filters=filters, or_filters=or_filters,
		fields=["title", "slug", "excerpt", "featured_image", "category",
		        "published_at", "reading_time_min", "source_name_label"],
		order_by="published_at desc",
		limit_start=(page - 1) * per, limit_page_length=per,
	)
	context.page = page
	context.has_next = total > page * per
	context.has_prev = page > 1
	context.q = q
	context.cat = cat
	context.categories = frappe.get_all(
		"News Category", filters={"is_active": 1},
		fields=["category_name", "category_slug"], order_by="display_order")
	context.parents = [{"label": "Home", "route": "/"}]
	return context
