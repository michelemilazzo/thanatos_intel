"""Creazione/arricchimento automatico Intelligence Contact da eventi WhatsApp."""
import frappe

# prefisso internazionale → paese (i più comuni per Thanatos)
_PREFIX_COUNTRY = [
    ("+39", "Italy"), ("+40", "Romania"), ("+41", "Switzerland"), ("+44", "United Kingdom"),
    ("+49", "Germany"), ("+33", "France"), ("+34", "Spain"), ("+351", "Portugal"),
    ("+30", "Greece"), ("+31", "Netherlands"), ("+32", "Belgium"), ("+43", "Austria"),
    ("+48", "Poland"), ("+352", "Luxembourg"), ("+356", "Malta"), ("+357", "Cyprus"),
    ("+359", "Bulgaria"), ("+385", "Croatia"), ("+386", "Slovenia"), ("+420", "Czech Republic"),
    ("+7", "Russia"), ("+90", "Turkey"), ("+212", "Morocco"), ("+216", "Tunisia"),
    ("+1", "United States"), ("+55", "Brazil"), ("+86", "China"), ("+91", "India"),
    ("+971", "United Arab Emirates"), ("+972", "Israel"), ("+380", "Ukraine"), ("+355", "Albania"),
]


def _country_from_number(num: str) -> str:
    n = num if num.startswith("+") else "+" + num
    for pref, country in sorted(_PREFIX_COUNTRY, key=lambda x: -len(x[0])):
        if n.startswith(pref):
            return country
    return ""


def ensure_contact_from_wa(number: str, profile_name: str = "", source: str = "WhatsApp") -> str | None:
    """Trova o crea un Intelligence Contact per un numero WhatsApp, popolando i campi.
    Restituisce il name del contatto."""
    if not number:
        return None
    n = number if number.startswith("+") else "+" + number

    existing = frappe.db.get_value("Intelligence Contact", {"whatsapp": n}, "name") or \
        frappe.db.get_value("Intelligence Contact", {"phone": n}, "name") or \
        frappe.db.get_value("Intelligence Contact", {"whatsapp": number}, "name") or \
        frappe.db.get_value("Intelligence Contact", {"phone": number}, "name")
    if existing:
        # arricchisce campi mancanti
        doc = frappe.get_doc("Intelligence Contact", existing)
        changed = False
        if profile_name and (not doc.full_name or doc.full_name.startswith("Contatto WhatsApp")):
            doc.full_name = profile_name; changed = True
        if not doc.whatsapp:
            doc.whatsapp = n; changed = True
        if not doc.phone:
            doc.phone = n; changed = True
        if not doc.country:
            doc.country = _country_from_number(n); changed = True
        if changed:
            doc.save(ignore_permissions=True)
        return existing

    country = _country_from_number(n)
    doc = frappe.get_doc({
        "doctype": "Intelligence Contact",
        "full_name": profile_name or f"Contatto WhatsApp {n}",
        "contact_type": "Persona",
        "country": country,
        "nationality": country,
        "phone": n,
        "whatsapp": n,
        "source": source,
        "risk_level": "Medio",
        "notes": f"Scheda creata automaticamente da {source} il {frappe.utils.nowdate()}.",
    })
    doc.insert(ignore_permissions=True)
    return doc.name
