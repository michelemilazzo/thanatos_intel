frappe.ui.form.on("Intel Lead", {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.status !== "Promosso a Caso" && frm.doc.status !== "Archiviato") {
            frm.add_custom_button(__("Promuovi a Caso"), () => {
                const d = new frappe.ui.Dialog({
                    title: __("Promuovi a Caso investigativo"),
                    fields: [
                        {
                            fieldname: "case_title",
                            fieldtype: "Data",
                            label: __("Titolo pratica"),
                            default: `[${frm.doc.source_type}] ${frm.doc.source_name || frm.doc.source_identifier || "Lead"}`,
                        },
                        {
                            fieldname: "case_type",
                            fieldtype: "Link",
                            label: __("Tipo pratica"),
                            options: "Case Type",
                        },
                    ],
                    primary_action_label: __("Crea Pratica"),
                    primary_action({ case_title, case_type }) {
                        d.hide();
                        frappe.call({
                            method: "promote_to_case",
                            doc: frm.doc,
                            args: { case_title, case_type },
                            freeze: true,
                            freeze_message: __("Creazione pratica in corso…"),
                            callback(r) {
                                if (r.message && r.message.case) {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("Pratica {0} creata", [r.message.case]),
                                        indicator: "green",
                                    });
                                    setTimeout(() => frappe.set_route("Form", "Investigation Case", r.message.case), 1000);
                                }
                            },
                        });
                    },
                });
                d.show();
            }, __("Azioni")).addClass("btn-primary");

            frm.add_custom_button(__("Archivia"), () => {
                frappe.confirm(__("Archiviare questo lead?"), () => {
                    frm.set_value("status", "Archiviato");
                    frm.save();
                });
            }, __("Azioni"));
        }

        if (frm.doc.linked_case) {
            frm.add_custom_button(__("Apri Pratica"), () => {
                frappe.set_route("Form", "Investigation Case", frm.doc.linked_case);
            });
        }

        frm.set_indicator_formatter("status", (doc) => {
            const map = {
                "Nuovo": "blue",
                "In Valutazione": "orange",
                "Promosso a Caso": "green",
                "Archiviato": "grey",
            };
            return map[doc.status] || "grey";
        });
    },
});
