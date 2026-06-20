import frappe


class WhatsAppTemplate(frappe.model.document.Document):

    def render(self, context: dict | None = None) -> str:
        """Sostituisce le variabili nel body_text con i valori del contesto."""
        text = self.body_text or ""
        ctx = context or {}
        for key, val in ctx.items():
            text = text.replace("{{" + key + "}}", str(val))
        return text
