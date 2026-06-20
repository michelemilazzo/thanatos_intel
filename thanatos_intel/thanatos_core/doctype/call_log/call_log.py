import frappe


class CallLog(frappe.model.document.Document):

    def after_insert(self):
        # Se la chiamata è collegata a un appuntamento, aggiorna lo stato a Completato
        if self.linked_appointment and self.outcome == "Risposta":
            frappe.db.set_value("Investigation Appointment", self.linked_appointment,
                                "status", "Completato")
            frappe.db.commit()
