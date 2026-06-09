frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        ThanatosPipeline.render(frm, 'get_case_pipeline');

        // Badge stato caso
        const colors = {
            'Open': 'blue', 'In Progress': 'yellow', 'Completed': 'green',
            'Closed': 'darkgrey', 'Archived': 'darkgrey', 'On Hold': 'orange'
        };
        if (frm.doc.status) {
            frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || 'grey');
        }

        if (!frm.is_new() && frm.doc.drive_folder) {
            frm.add_custom_button(__('Apri Drive'), () => {
                window.open('/drive?entity=' + frm.doc.drive_folder, '_blank');
            }, __('File'));
        }

        if (!frm.is_new() && !frm.doc.drive_folder) {
            frm.add_custom_button(__('Crea cartella Drive'), () => {
                frappe.call({
                    method: 'thanatos_intel.integrations.intel_inbox.ensure_case_folder_api',
                    args: { case_name: frm.doc.name },
                    callback(r) {
                        if (r.message && r.message.ok) {
                            frappe.show_alert({ message: 'Cartella Drive creata', indicator: 'green' });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('File'));
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__('Calcola Risk Score'), () => {
                frappe.call({
                    method: 'thanatos_intel.thanatos_core.doctype.risk_score.risk_score.calculate_for_case',
                    args: { case_name: frm.doc.name },
                    freeze: true,
                    freeze_message: 'Calcolo in corso…',
                    callback(r) {
                        if (!r.exc && r.message) {
                            frappe.show_alert({
                                message: `Risk Score: <b>${r.message.score}</b> — <b>${r.message.classification}</b> (${r.message.matched} regole)`,
                                indicator: r.message.score >= 61 ? 'red' : r.message.score >= 31 ? 'orange' : 'green'
                            }, 6);
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Intelligence'));
        }
    },
    after_save(frm) {
        ThanatosPipeline.render(frm, 'get_case_pipeline');
    }
});
