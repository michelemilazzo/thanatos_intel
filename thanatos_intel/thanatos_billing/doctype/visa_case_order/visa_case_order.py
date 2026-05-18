from frappe.model.document import Document

PAID_STATUS = "Paid"

class VisaCaseOrder(Document):
    def validate(self):
        self.set_portal_access_from_payment_status()

    def set_portal_access_from_payment_status(self):
        """Enable the customer portal only after confirmed payment."""
        self.portal_enabled = 1 if self.payment_status == PAID_STATUS else 0
