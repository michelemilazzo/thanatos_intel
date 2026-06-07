"""Pipeline CRM -> fascicolo -> fatturazione.

CRM Deal (status 'Won')  ->  Customer (ERPNext)  ->  Investigation Case + Project
La Sales Invoice si aggancia poi al Project (dimensione obbligatoria).

Trigger: automatico quando il Deal passa a 'Won' (doc_event) E manuale via bottone
sul form desk del CRM Deal. Idempotente: il Deal porta il link al caso creato.
"""
import frappe
from frappe.model.naming import make_autoname

DEFAULT_CASE_TYPE = "Corporate"

CRM_FIELDS = {
    "CRM Deal": [
        {
            "fieldname": "investigation_case",
            "label": "Investigation Case",
            "fieldtype": "Link",
            "options": "Investigation Case",
            "read_only": 1,
            "insert_after": "status",
            "description": "Fascicolo generato da questo deal (pipeline).",
        },
    ],
}

_BUTTON_SCRIPT = """frappe.ui.form.on('CRM Deal', {
    refresh(frm) {
        if (frm.is_new()) return;
        if (frm.doc.investigation_case) {
            frm.add_custom_button(__('Apri fascicolo'), () => {
                frappe.set_route('Form', 'Investigation Case', frm.doc.investigation_case);
            });
            return;
        }
        frm.add_custom_button(__('Crea fascicolo'), () => {
            frappe.call({
                method: 'thanatos_intel.billing.crm_pipeline.create_case_from_deal',
                args: { deal: frm.doc.name },
                freeze: true,
                callback: () => frm.reload_doc(),
            });
        });
    },
});"""


# Bottone nella SPA CRM (frappe/crm) via 'CRM Form Script' (setupForm -> actions).
_CRM_SPA_SCRIPT = """function setupForm({ doc, call, createToast }) {
  let actions = []
  if (doc.investigation_case) {
    actions.push({
      label: 'Apri fascicolo',
      icon: 'folder',
      onClick: () => window.open('/app/investigation-case/' + doc.investigation_case, '_blank'),
    })
  } else {
    actions.push({
      label: 'Crea fascicolo',
      icon: 'folder-plus',
      onClick: async (close) => {
        try {
          let name = await call('thanatos_intel.billing.crm_pipeline.create_case_from_deal', { deal: doc.name })
          createToast({ title: 'Fascicolo creato: ' + name, icon: 'check', iconClasses: 'text-green-600' })
          close && close()
          setTimeout(() => location.reload(), 800)
        } catch (e) {
          createToast({ title: 'Errore creazione fascicolo', icon: 'x', iconClasses: 'text-red-600' })
        }
      },
    })
  }
  return { actions }
}"""


def setup_pipeline():
    """Idempotente, da after_migrate: custom field sul Deal + bottone desk + bottone SPA CRM."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields(CRM_FIELDS, ignore_validate=True)
    _ensure_button_script()
    _ensure_crm_form_script()


def _ensure_crm_form_script():
    if not frappe.db.exists("DocType", "CRM Form Script"):
        return
    name = "Thanatos — Crea fascicolo da Deal (SPA)"
    if frappe.db.exists("CRM Form Script", name):
        frappe.db.set_value("CRM Form Script", name, "script", _CRM_SPA_SCRIPT)
        frappe.db.set_value("CRM Form Script", name, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "CRM Form Script", "name": name,
            "dt": "CRM Deal", "view": "Form", "enabled": 1, "is_standard": 0,
            "script": _CRM_SPA_SCRIPT,
        }).insert(ignore_permissions=True)


def _ensure_button_script():
    name = "Thanatos — Crea fascicolo da Deal"
    if frappe.db.exists("Client Script", name):
        frappe.db.set_value("Client Script", name, "script", _BUTTON_SCRIPT)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": name,
            "dt": "CRM Deal",
            "view": "Form",
            "enabled": 1,
            "script": _BUTTON_SCRIPT,
        }).insert(ignore_permissions=True)


def _default_company():
    return (
        frappe.defaults.get_user_default("Company")
        or frappe.defaults.get_global_default("company")
        or frappe.db.get_value("Company", {}, "name")
    )


def get_or_create_customer(customer_name, currency=None):
    existing = frappe.db.get_value("Customer", {"customer_name": customer_name})
    if existing:
        return existing
    data = {
        "doctype": "Customer",
        "customer_name": customer_name,
        "customer_type": "Company",
    }
    if currency:
        data["default_currency"] = currency
    return frappe.get_doc(data).insert(ignore_permissions=True).name


def _next_case_number():
    """Numero caso libero: make_autoname può collidere con casi pre-esistenti
    creati con altra logica (la serie riparte da 1), quindi salta i presi."""
    for _ in range(10000):
        n = make_autoname("CASE-.YYYY.-.####")
        if not frappe.db.exists("Investigation Case", n):
            return n
    frappe.throw("Nessun numero caso libero")


def _create_billing_project(project_name, customer):
    return frappe.get_doc({
        "doctype": "Project",
        "project_name": project_name,
        "customer": customer,
        "company": _default_company(),
    }).insert(ignore_permissions=True).name


@frappe.whitelist()
def create_case_from_deal(deal):
    """Crea (idempotente) Customer + Investigation Case + Project da un CRM Deal."""
    d = frappe.get_doc("CRM Deal", deal)
    if d.get("investigation_case") and frappe.db.exists("Investigation Case", d.investigation_case):
        return d.investigation_case

    org = d.get("organization")
    cust_name = (
        (frappe.db.get_value("CRM Organization", org, "organization_name") if org else None)
        or d.get("email")
        or d.name
    )
    customer = get_or_create_customer(cust_name, d.get("currency"))

    case = frappe.get_doc({
        "doctype": "Investigation Case",
        "case_number": _next_case_number(),
        "case_title": f"{cust_name} — {d.name}",
        "case_type": DEFAULT_CASE_TYPE,
        "status": "Open",
    }).insert(ignore_permissions=True)

    project = _create_billing_project(case.case_title, customer)
    case.db_set("project", project)
    d.db_set("investigation_case", case.name)
    frappe.db.commit()
    return case.name


def on_deal_update(doc, method=None):
    """doc_event: alla vittoria del deal genera il fascicolo. Non blocca il salvataggio."""
    if doc.get("status") != "Won":
        return
    if doc.get("investigation_case"):
        return
    try:
        create_case_from_deal(doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "crm_pipeline.on_deal_update")
