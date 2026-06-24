import frappe
from frappe import _

# Scorciatoie informative/azioni del portale (ricerca per etichetta)
_HELP = [
    ("Guida", "Centro assistenza e guide", "/portal/guide"),
    ("FAQ", "Domande frequenti", "/faq"),
    ("Apri una pratica", "Avvia una nuova richiesta", "/portal/apri"),
    ("Fatture", "Storico pagamenti e proforme", "/portal/invoices"),
    ("Verifica blacklist", "Controlla un soggetto", "/portal/verifica-blacklist"),
    ("Segnala alla blacklist", "Segnala un soggetto", "/portal/segnala"),
    ("Modifica profilo", "Dati, indirizzi, verifica", "/modifica-profilo"),
    ("Privacy e GDPR", "Consensi e i tuoi dati", "/portal/privacy"),
]


@frappe.whitelist()
def portal_search(q=None):
    """Ricerca del portale, limitata ai dati del cliente corrente + articoli/info.
    I clienti vedono SOLO le proprie pratiche/documenti (scoping visible_case_names)."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Accesso richiesto"), frappe.PermissionError)
    q = (q or "").strip()
    if len(q) < 2:
        return {"results": []}
    like = "%" + q + "%"
    user = frappe.session.user
    out = []

    from thanatos_intel.permissions import is_full_access, visible_case_names
    full = is_full_access(user)
    visible = None if full else (visible_case_names(user) or [])

    # --- Pratiche (scoped) ---
    cf = {} if full else {"name": ["in", visible or [""]]}
    cases = frappe.get_all(
        "Investigation Case", filters=cf,
        or_filters=[["case_title", "like", like], ["case_number", "like", like], ["name", "like", like]],
        fields=["name", "case_title", "case_number", "status"], limit=6)
    for c in cases:
        out.append({"type": "Pratica", "title": c.case_title or c.name,
                    "snippet": " · ".join([x for x in [c.case_number, c.status] if x]),
                    "url": "/portal/case/" + c.name})

    # --- Documenti (report dei casi visibili) ---
    rf = {"report_title": ["like", like]}
    if not full:
        rf["investigation_case"] = ["in", visible or [""]]
    for r in frappe.get_all("Investigation Report", filters=rf,
                            fields=["name", "report_title", "pdf_file", "investigation_case"],
                            order_by="modified desc", limit=6):
        out.append({"type": "Documento", "title": r.report_title or r.name,
                    "snippet": r.investigation_case or "",
                    "url": r.pdf_file or ("/portal/case/" + (r.investigation_case or ""))})

    # --- Articoli / News (pubblici) ---
    for n in frappe.get_all("News Article",
                            filters={"published": 1},
                            or_filters=[["title", "like", like], ["excerpt", "like", like]],
                            fields=["title", "slug", "excerpt", "category"],
                            order_by="published_at desc", limit=6):
        out.append({"type": "Articolo", "title": n.title,
                    "snippet": (n.excerpt or "")[:90],
                    "url": "/news/" + (n.slug or "")})

    # --- Scorciatoie / info ---
    ql = q.lower()
    for label, desc, url in _HELP:
        if ql in label.lower() or ql in desc.lower():
            out.append({"type": "Info", "title": label, "snippet": desc, "url": url})

    return {"results": out[:24]}
