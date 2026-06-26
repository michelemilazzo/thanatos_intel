"""Agency Report — preparazione e tracciamento segnalazioni a FBI/Europol/Interpol.

NB: non esiste API pubblica di invio a queste agenzie. La scheda PREPARA il testo
formattato e fornisce il CANALE UFFICIALE; l'invio avviene tramite il loro form/tip
ufficiale (azione dell'operatore). Qui si traccia stato ed esito.
"""
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

# Canali ufficiali di segnalazione (tip/lead) — pubblici.
CHANNELS = {
    "FBI": "https://tips.fbi.gov/",
    "Europol": "https://eumostwanted.eu/",
    "Interpol": "https://www.interpol.int/en/Contacts/Contact-INTERPOL",
    "National Police": "",
    "Other": "",
}


class AgencyReport(Document):
    def validate(self):
        if self.target and not self.subject_name:
            self.subject_name = frappe.db.get_value("Tracking Target", self.target, "target_name")
        if not self.reporter:
            self.reporter = frappe.session.user
        self.submission_channel = CHANNELS.get(self.agency, "")
        if self.status == "Submitted" and not self.submitted_on:
            self.submitted_on = now_datetime()

    @frappe.whitelist()
    def build_text(self):
        """Testo formattato pronto da incollare nel form ufficiale dell'agenzia."""
        t = frappe.get_doc("Tracking Target", self.target) if self.target else None
        L = []
        L.append(f"SUBJECT: {self.subject_name or '-'}")
        if t:
            if t.aliases:
                L.append("ALIASES: " + ", ".join(t.aliases.splitlines()))
            if t.date_of_birth:
                L.append(f"DOB: {t.date_of_birth}")
            if t.nationality:
                L.append(f"NATIONALITY: {t.nationality}")
            if t.source and t.source_ref:
                L.append(f"REFERENCE: {t.source} {t.source_ref}")
            if t.source_url:
                L.append(f"NOTICE: {t.source_url}")
        L.append("")
        L.append(f"REPORT TYPE: {self.report_type or '-'}  |  CONFIDENCE: {self.confidence or '-'}")
        if self.sighting_location or self.sighting_country:
            L.append("LOCATION: " + ", ".join(filter(None, [self.sighting_location, self.sighting_country])))
        if self.sighting_datetime:
            L.append(f"OBSERVED AT: {self.sighting_datetime}")
        if self.summary:
            L.append(f"SUMMARY: {self.summary}")
        if self.details:
            import re
            plain = re.sub(r"<[^>]+>", "", self.details).strip()
            if plain:
                L.append("")
                L.append("DETAILS:")
                L.append(plain)
        L.append("")
        L.append("Reported by Thanatos Intelligence — follow-up: " + (self.followup_contact or self.reporter or "-"))
        return {"text": "\n".join(L), "channel": self.submission_channel}
