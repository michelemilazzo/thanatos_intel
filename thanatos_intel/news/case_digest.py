"""
Generate periodic editorial digests from internal activity (anonymized).
Counts: cases opened, evidence acquired, reports issued, OSINT lookups, fraud patterns matched.
"""
import frappe
from collections import Counter
from frappe.utils import now_datetime, add_days, slug as _slug


def generate_weekly_digest():
	since = add_days(now_datetime(), -7)
	cases = frappe.get_all("Investigation Case", filters={"creation": [">=", since]},
	                       fields=["name", "case_type", "sector"])
	evidence_n = frappe.db.count("Investigation Evidence", {"creation": [">=", since]})
	reports_n = frappe.db.count("Investigation Report", {"creation": [">=", since]})
	osint_n = 0
	try:
		osint_n = frappe.db.count("OSINT Lookup", {"creation": [">=", since]})
	except Exception:
		pass

	if not cases and not evidence_n and not reports_n:
		return {"skipped": "no_activity"}

	sectors = Counter([c.sector for c in cases if c.sector])
	case_types = Counter([c.case_type for c in cases if c.case_type])
	top_sectors = ", ".join(f"{s} ({n})" for s, n in sectors.most_common(5)) or "vari"
	top_types = ", ".join(f"{t} ({n})" for t, n in case_types.most_common(5)) or "vari"

	title = f"Settimana Thanatos: {len(cases)} nuovi casi, {reports_n} report depositati"
	excerpt = (f"In sette giorni la piattaforma ha registrato {len(cases)} nuove indagini, "
	           f"{evidence_n} prove acquisite e {reports_n} report consegnati. "
	           f"Settori prevalenti: {top_sectors}.")
	content = f"""
<p><strong>Periodo:</strong> ultimi 7 giorni.</p>
<ul>
  <li><strong>Nuovi casi aperti:</strong> {len(cases)}</li>
  <li><strong>Prove acquisite (chain-of-custody):</strong> {evidence_n}</li>
  <li><strong>Report investigativi depositati:</strong> {reports_n}</li>
  <li><strong>Lookup OSINT eseguiti:</strong> {osint_n}</li>
</ul>
<h3>Settori più presidiati</h3>
<p>{top_sectors}</p>
<h3>Tipologie d'incarico</h3>
<p>{top_types}</p>
<p><em>Tutti i dati sono aggregati e anonimizzati. Nessun caso specifico è identificabile.</em></p>
"""
	cat = frappe.db.get_value("News Category", {"category_slug": "attivita-thanatos"}, "name") \
	      or frappe.db.get_value("News Category", {"is_active": 1}, "name")
	doc = frappe.get_doc({
		"doctype": "News Article",
		"title": title,
		"slug": _slug(title)[:160],
		"category": cat,
		"excerpt": excerpt,
		"content": content,
		"language": "it",
		"source_type": "AI Generated",
		"source_name_label": "Thanatos Newsroom",
		"published": 1,
		"published_at": now_datetime(),
		"tags": "weekly,attività,thanatos",
		"featured": 0,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"article": doc.name}
