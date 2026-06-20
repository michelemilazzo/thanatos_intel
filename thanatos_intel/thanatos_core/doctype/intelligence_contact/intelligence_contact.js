frappe.ui.form.on("Intelligence Contact", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Registra Chiamata"), () => {
                window.thanatos && window.thanatos.logCall({
                    linked_contact: frm.doc.name,
                    caller_name: frm.doc.full_name || "",
                    caller_number: frm.doc.phone || frm.doc.whatsapp || "",
                    onSuccess() { frm.reload_doc(); },
                });
            });

            frm.add_custom_button(__("Nuovo Intel Lead"), () => {
                frappe.new_doc("Intel Lead", {
                    source_type: "Manuale",
                    linked_contact: frm.doc.name,
                    source_name: frm.doc.full_name || "",
                    source_identifier: frm.doc.phone || frm.doc.email || "",
                });
            });
        }
    },
});
