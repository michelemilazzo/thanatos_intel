"""Dossier IP (inventario live di tutto ciò che abbiamo costruito) + Bacheca.

Il dossier si rilegge di tanto in tanto: app/moduli/DocType custom (l'IP),
servizi, capacità acquisite, compliance, brand. La bacheca raccoglie gli
aggiornamenti (nuovi servizi/capacità/milestone), interni e verso clienti.
"""
import frappe
from frappe.utils import now_datetime


def _count(dt, f=None):
    try:
        return frappe.db.count(dt, f or {})
    except Exception:
        return 0


@frappe.whitelist()
def dossier_data():
    apps = frappe.get_installed_apps()
    mods = [m.module_name for m in frappe.get_all("Module Def",
            filters={"app_name": "thanatos_intel"}, fields=["module_name"])]
    dt_count = _count("DocType", {"custom": 0, "module": ["in", mods]}) if mods else 0
    cats = [r.category for r in frappe.get_all("Service Catalog", fields=["category"],
            group_by="category") if r.category]
    caps = frappe.get_all("Capability Acquisition",
                          fields=["name", "need", "suggested_app", "status"],
                          order_by="creation desc", limit=20) if frappe.db.exists("DocType", "Capability Acquisition") else []
    return {
        "apps": apps,
        "modules": sorted(mods),
        "custom_doctypes": dt_count,
        "services": _count("Service Catalog"),
        "service_categories": sorted(cats),
        "capabilities": caps,
        "compliance": {"policy": _count("Compliance Policy"), "risk": _count("Risk Register Item"),
                       "ropa": _count("ROPA Entry")},
        "counts": {"casi": _count("Investigation Case"), "clienti": _count("Investigation Client"),
                   "entita": _count("Investigation Entity"), "reperti": _count("Investigation Evidence"),
                   "servizi": _count("Service Catalog"), "news": _count("News Article")},
        "brand": {"logo": "/assets/thanatos_intel/images/thanatos-logo-mark.png",
                  "company": "Thanatos Investigazioni S.R.L.", "reg": "Constanța · RO 46901022"},
    }


@frappe.whitelist()
def bacheca(limit=30):
    return frappe.get_all("Bacheca Update",
                          fields=["name", "title", "category", "audience", "body", "published", "modified"],
                          order_by="modified desc", limit=int(limit))


@frappe.whitelist()
def post_update(title, body=None, category="Milestone", audience="Interno", publish=1):
    roles = set(frappe.get_roles())
    if not (roles & {"System Manager", "Investigation Manager", "Thanatos Director", "Investigator"}):
        frappe.throw("Riservato agli operatori.")
    d = frappe.new_doc("Bacheca Update")
    d.title = (title or "Aggiornamento")[:140]
    d.body = body or ""
    d.category = category
    d.audience = audience
    d.published = 1 if int(publish) else 0
    d.published_on = now_datetime()
    d.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": d.name}


def _tbl(headers, rows):
    h = '<table style="width:100%;border-collapse:collapse;font-size:11px;margin:6px 0 16px">'
    h += '<tr>' + ''.join('<th style="text-align:left;border-bottom:1px solid #999;padding:4px 6px;background:#f0ece2">%s</th>' % c for c in headers) + '</tr>'
    for r in rows:
        h += '<tr>' + ''.join('<td style="border-bottom:1px solid #eee;padding:4px 6px">%s</td>' % (c if c is not None else "") for c in r) + '</tr>'
    if not rows:
        h += '<tr><td colspan="%d" style="padding:6px;color:#999">—</td></tr>' % len(headers)
    return h + '</table>'


def _ga(dt, fields, **kw):
    try:
        return frappe.get_all(dt, fields=fields, limit=0, **kw)
    except Exception:
        return []


@frappe.whitelist()
def generate_audit_dossier():
    """F4: raccoglie ISMS (policy, risk, ROPA, SoA, fornitori, incidenti, evidenze)
    in un dossier PDF pronto per l'auditor."""
    roles = set(frappe.get_roles())
    if not (roles & {"System Manager", "Thanatos Compliance Officer", "Thanatos Director", "Investigation Manager"}):
        frappe.throw("Riservato a compliance/direzione.")
    today = frappe.utils.nowdate()
    pol = _ga("Compliance Policy", ["iso_clause", "title", "version", "status", "next_review"], order_by="iso_standard asc")
    risk = _ga("Risk Register Item", ["title", "asset", "risk_level", "treatment", "status"], order_by="risk_level desc")
    ropa = _ga("ROPA Entry", ["title", "legal_basis", "retention", "special_categories"])
    soa = _ga("SoA Control", ["control_id", "control_name", "applicable", "implemented"], order_by="control_id asc")
    sup = _ga("ISMS Supplier", ["supplier_name", "service", "is_foreign", "dpa_signed", "criticality"])
    inc = _ga("Security Incident", ["title", "severity", "status", "category"])
    nc = _ga("Nonconformity", ["title", "source", "status"])
    try:
        custody = frappe.db.count("Chain Of Custody Event")
    except Exception:
        custody = 0

    parts = []
    parts.append('<div style="font-family:Helvetica,Arial,sans-serif;color:#1a1a1a">')
    parts.append('<div style="border-bottom:2px solid #C8A96E;padding-bottom:8px;margin-bottom:14px">'
                 '<div style="font-size:20px;font-weight:bold">Dossier ISMS — Thanatos Investigazioni S.R.L.</div>'
                 '<div style="font-size:12px;color:#555">Statement &amp; evidence per audit · ISO/IEC 27001 · '
                 'ISO 9001 · ISO/IEC 27701 — generato il %s</div></div>' % today)
    parts.append('<p style="font-size:11px;color:#555">Constanța · RO 46901022. Documento riservato, '
                 'generato dal sistema (evidenza viva).</p>')
    parts.append('<h3>1. Politiche e procedure (document control)</h3>')
    parts.append(_tbl(["Clausola", "Documento", "Ver.", "Stato", "Prossima revisione"],
                      [[p.iso_clause, p.title, p.version, p.status, p.next_review] for p in pol]))
    parts.append('<h3>2. Registro dei rischi</h3>')
    parts.append(_tbl(["Rischio", "Asset/Processo", "Livello", "Trattamento", "Stato"],
                      [[r.title, r.asset, r.risk_level, r.treatment, r.status] for r in risk]))
    parts.append('<h3>3. Registro dei trattamenti (ROPA — GDPR art.30)</h3>')
    parts.append(_tbl(["Attività", "Base giuridica", "Conservazione", "Cat. particolari"],
                      [[r.title, r.legal_basis, r.retention, "Sì" if r.special_categories else "No"] for r in ropa]))
    parts.append('<h3>4. Statement of Applicability (Annex A)</h3>')
    parts.append(_tbl(["Controllo", "Descrizione", "Applicabile", "Attuazione"],
                      [[c.control_id, c.control_name, "Sì" if c.applicable else "No", c.implemented] for c in soa]))
    parts.append('<h3>5. Fornitori e DPA</h3>')
    parts.append(_tbl(["Fornitore", "Servizio", "Extra-UE", "DPA", "Criticità"],
                      [[u.supplier_name, u.service, "Sì" if u.is_foreign else "No", "Sì" if u.dpa_signed else "No", u.criticality] for u in sup]))
    parts.append('<h3>6. Incidenti e non conformità</h3>')
    parts.append(_tbl(["Incidente", "Gravità", "Stato", "Categoria"],
                      [[i.title, i.severity, i.status, i.category] for i in inc]))
    parts.append(_tbl(["Non conformità", "Origine", "Stato"], [[n.title, n.source, n.status] for n in nc]))
    parts.append('<h3>7. Evidenza catena di custodia</h3>')
    parts.append('<p style="font-size:12px">Eventi di custodia/hash registrati (incl. completamento step di '
                 'processo con SHA-256): <b>%d</b>. Ogni step di pratica genera un\'evidenza immutabile con '
                 'hash a norma.</p>' % custody)
    parts.append('<p style="font-size:10px;color:#888;margin-top:24px">Generato automaticamente dalla '
                 'piattaforma Thanatos Intel — la piattaforma È l\'evidenza.</p></div>')
    html = "".join(parts)

    try:
        from frappe.utils.pdf import get_pdf
        pdf = get_pdf(html)
        fname = "ISO_Audit_Dossier_%s.pdf" % today
        fdoc = frappe.get_doc({"doctype": "File", "file_name": fname, "is_private": 1,
                               "content": pdf}).insert(ignore_permissions=True)
        return {"ok": True, "url": fdoc.file_url,
                "counts": {"policy": len(pol), "risk": len(risk), "ropa": len(ropa),
                           "soa": len(soa), "custody": custody}}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "audit dossier pdf")
        return {"ok": False, "html": html}
