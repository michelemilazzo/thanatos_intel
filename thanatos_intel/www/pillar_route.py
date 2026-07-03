"""Controller Frappe web route per le pillar pages SEO (IT + EN).

Rende thanatos_intel/www/pillar_template.html con i dati di pillar_content.
Mappato in hooks.py website_route_rules:
  /servizi/<slug>       -> lang=it
  /en/services/<slug>   -> lang=en
"""
import frappe

from thanatos_intel.www.pillar_content import PILLARS, get_pillar


LABELS = {
    "it": {
        "when": "Quando usarlo",
        "deliverables": "Cosa ricevi",
        "faq": "Domande frequenti",
        "start": "Inizia ora",
        "others": "Altri servizi",
    },
    "en": {
        "when": "When to use it",
        "deliverables": "What you get",
        "faq": "Frequently asked questions",
        "start": "Start now",
        "others": "Other services",
    },
}


def get_context(context):
    context.no_cache = 1
    path = frappe.local.request.path.strip("/")
    parts = path.split("/")
    if parts[0] == "en":
        lang = "en"
        slug = parts[-1] if len(parts) >= 3 else ""
        cta_link = "/en/register"
        base_it = "https://thanatos.agency/servizi"
        base_en = "https://thanatos.agency/en/services"
    else:
        lang = "it"
        slug = parts[-1] if len(parts) >= 2 else ""
        cta_link = "/registrati"
        base_it = "https://thanatos.agency/servizi"
        base_en = "https://thanatos.agency/en/services"

    data = get_pillar(slug, lang)
    if not data:
        frappe.local.flags.redirect_location = "/servizi" if lang == "it" else "/en/services"
        raise frappe.Redirect

    context.update(data)
    labels = LABELS[lang]
    context.update({
        "lang": lang,
        "slug": slug,
        "label_when": labels["when"],
        "label_deliverables": labels["deliverables"],
        "label_faq": labels["faq"],
        "label_start": labels["start"],
        "label_others": labels["others"],
        "cta_link": cta_link,
        "canonical": f"{base_it if lang == 'it' else base_en}/{slug}",
        "alt_lang": {"hreflang": "en" if lang == "it" else "it",
                     "href": f"{base_en if lang == 'it' else base_it}/{slug}"},
        "others": [
            {"cat": PILLARS[k][lang]["cat"] if lang in PILLARS[k] else PILLARS[k]["it"]["cat"],
             "h1": PILLARS[k][lang]["h1"] if lang in PILLARS[k] else PILLARS[k]["it"]["h1"],
             "href": f"/{'en/services' if lang == 'en' else 'servizi'}/{k}"}
            for k in PILLARS.keys() if k != slug
        ][:8],
    })
    return context
