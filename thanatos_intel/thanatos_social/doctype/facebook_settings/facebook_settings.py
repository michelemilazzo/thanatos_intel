import frappe
from frappe.model.document import Document


class FacebookSettings(Document):
    pass


@frappe.whitelist()
def test_connection() -> dict:
    """Verifica le credenziali leggendo nome e follower della Pagina.

    Chiamata dal pulsante 'Verifica connessione' nel form Facebook Settings.
    """
    from thanatos_intel.integrations import facebook_graph as fb

    settings = fb.get_settings()
    if not (settings["page_id"] and settings["page_token"]):
        frappe.throw("Imposta prima ID Pagina e Page Access Token.")

    info = fb._graph_request(
        "GET", f"/{settings['page_id']}", settings,
        params={"fields": "name,followers_count,fan_count,link"},
    )
    return {
        "ok": True,
        "name": info.get("name"),
        "followers": info.get("followers_count") or info.get("fan_count"),
        "link": info.get("link"),
    }
