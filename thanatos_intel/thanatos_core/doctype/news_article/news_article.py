import frappe
import re
from frappe.model.document import Document
from frappe.utils import now_datetime, slug as _slug
from frappe.website.website_generator import WebsiteGenerator


class NewsArticle(WebsiteGenerator):
	website = frappe._dict(
		template="templates/news_article.html",
		condition_field="published",
		page_title_field="title",
	)

	def autoname(self):
		# WebsiteGenerator nominerebbe dal titolo "scrubbed" -> piu articoli con lo stesso
		# titolo (es. "#AccadeOggi") collidono su name='accadeoggi'. Usiamo lo slug, gia
		# reso univoco dall'ingest; fallback alla serie NEWS-YYYY-#####.
		if self.title and not self.slug:
			self.slug = _slug(self.title)[:160]
		if self.slug:
			self.name = self.slug
		else:
			from frappe.model.naming import make_autoname
			self.name = make_autoname("NEWS-.YYYY.-.#####")

	def before_save(self):
		if self.title and not self.slug:
			self.slug = _slug(self.title)[:160]
		if self.slug:
			self.slug = _slug(self.slug)[:160]
		if not self.excerpt and self.content:
			plain = re.sub(r"<[^>]+>", " ", self.content)
			plain = re.sub(r"\s+", " ", plain).strip()
			self.excerpt = (plain[:280] + "…") if len(plain) > 280 else plain
		if self.content:
			plain = re.sub(r"<[^>]+>", " ", self.content)
			words = len(plain.split())
			self.reading_time_min = max(1, round(words / 220))
		if self.published and not self.published_at:
			self.published_at = now_datetime()
		self.route = f"news/{self.slug}" if self.slug else None

	def get_context(self, context):
		context.parents = [{"label": "News", "route": "news"}]
		context.no_cache = 0
		try:
			frappe.db.set_value("News Article", self.name, "views",
			                    (self.views or 0) + 1, update_modified=False)
		except Exception:
			pass
		cat = self.category and frappe.db.get_value("News Category", self.category,
		                                            ["category_name", "color", "category_slug"], as_dict=True)
		context.category_doc = cat or frappe._dict()
		related = frappe.get_all("News Article",
		                         filters={"published": 1, "category": self.category, "name": ["!=", self.name]},
		                         fields=["title", "slug", "excerpt", "published_at", "featured_image"],
		                         order_by="published_at desc", limit=3)
		context.related = related
		return context
