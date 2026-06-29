"""Setup layout form Investigation Case: riposiziona i custom HTML panel nei
tab giusti (idempotente). Tab/cockpit_panel/verifiche_panel vivono nel doctype JSON."""
import frappe


def _move(fieldname, insert_after):
    name = frappe.db.get_value("Custom Field", {"dt": "Investigation Case", "fieldname": fieldname})
    if name:
        cf = frappe.get_doc("Custom Field", name)
        if cf.insert_after != insert_after:
            cf.insert_after = insert_after
            cf.save(ignore_permissions=True)
        return cf.insert_after
    return None


@frappe.whitelist()
def setup():
    res = {}
    res["ai_chat_panel"] = _move("ai_chat_panel", "cockpit_panel")   # → tab Cockpit
    res["comms_pane"] = _move("comms_pane", "case_activities")       # → tab Documenti & Esito
    frappe.clear_cache(doctype="Investigation Case")
    frappe.db.commit()
    meta = frappe.get_meta("Investigation Case", cached=False)
    res["tabs"] = [f.label for f in meta.fields if f.fieldtype == "Tab Break"]
    res["has_cockpit_panel"] = bool(meta.get_field("cockpit_panel"))
    res["has_verifiche_panel"] = bool(meta.get_field("verifiche_panel"))
    return res
