import frappe
from frappe import _
from frappe.utils import now_datetime


class IntelLead(frappe.model.document.Document):

    @frappe.whitelist()
    def promote_to_case(self, case_title: str = "", case_type: str = "") -> dict:
        if self.status == "Promosso a Caso" and self.linked_case:
            return {"case": self.linked_case}

        title = case_title or (
            f"[{self.source_type}] {self.source_name or self.source_identifier or 'Lead'}"
        )
        case = frappe.get_doc({
            "doctype": "Investigation Case",
            "case_title": title,
            "case_type": case_type or None,
            "status": "Open",
            "notes": (
                f"Generato da Intel Lead {self.name}\n"
                f"Canale: {self.source_type}\n"
                f"Mittente: {self.source_name or self.source_identifier or '—'}\n\n"
                f"Contenuto originale:\n{self.content or ''}"
            ),
        })
        case.insert(ignore_permissions=True)
        frappe.db.commit()

        self.db_set("status", "Promosso a Caso", notify=True)
        self.db_set("linked_case", case.name, notify=True)
        self.db_set("promoted_at", now_datetime(), notify=True)
        self.db_set("promoted_by", frappe.session.user, notify=True)

        return {"case": case.name, "case_url": f"/app/investigation-case/{case.name}"}
