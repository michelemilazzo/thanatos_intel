from frappe.app import make_application

def get_app():
    return make_application(__name__)
