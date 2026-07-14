"""API whitelisted del modulo Thanatos Social (Facebook).

Permette di creare/pubblicare post dalla Pagina Thanatos anche da altri flussi
(es. quando esce un nuovo contenuto news/intel) o via REST.
"""

import frappe

from thanatos_intel.integrations import facebook_graph as fb


@frappe.whitelist()
def quick_post(message: str = "", link: str | None = None,
               image_url: str | None = None, title: str | None = None,
               publish: int = 1):
    """Crea un Facebook Post e (opzionalmente) lo pubblica subito.

    Restituisce {name, status, fb_post_id, permalink}.
    """
    if not message and not link and not image_url:
        frappe.throw("Serve almeno un testo, un link o un'immagine.")

    post_type = "Foto" if image_url else ("Link" if link else "Testo")
    doc = frappe.get_doc({
        "doctype": "Facebook Post",
        "post_title": title or (message[:80] if message else "Post Facebook"),
        "post_type": post_type,
        "message": message,
        "link": link,
        "image": image_url,
    })
    doc.insert(ignore_permissions=True)

    if int(publish or 0):
        doc.publish_now()

    return {
        "name": doc.name,
        "status": doc.status,
        "fb_post_id": doc.fb_post_id,
        "permalink": doc.permalink,
    }


@frappe.whitelist()
def page_insights(period: str = "day"):
    """Restituisce gli insights aggregati della Pagina Facebook."""
    if not fb.is_enabled():
        frappe.throw("Integrazione Facebook non attiva.")
    return fb.fetch_page_insights(period=period)
