frappe.ui.form.on('Diplomatic Eligibility Case', {
    refresh(frm) {
        ThanatosPipeline.render(frm, 'get_ddd_pipeline');


        // ── Email → bozza webmail ──
        if (!frm.is_new()) {
            frm.add_custom_button(__('✉ Richiesta KYC/KYB'), () => {
                frappe.call({
                    method: 'thanatos_intel.mail_templates.draft_kyc_request',
                    args: { case_name: frm.doc.name },
                    freeze: true, freeze_message: 'Creazione bozza...',
                    callback(r) {
                        if (r.message && r.message.draft_id) {
                            frappe.show_alert({ message: 'Bozza creata nel webmail', indicator: 'green' });
                            window.open('/mail', '_blank');
                        } else {
                            frappe.msgprint('Errore: controlla configurazione email (User Settings).');
                        }
                    }
                });
            }, __('Email'));

            frm.add_custom_button(__('✉ Aggiornamento Stato'), () => {
                frappe.call({
                    method: 'thanatos_intel.mail_templates.draft_status_update',
                    args: { case_name: frm.doc.name },
                    freeze: true, freeze_message: 'Creazione bozza...',
                    callback(r) {
                        if (r.message && r.message.draft_id) {
                            frappe.show_alert({ message: 'Bozza creata nel webmail', indicator: 'green' });
                            window.open('/mail', '_blank');
                        }
                    }
                });
            }, __('Email'));
        }

        const colors = {
            'Draft': 'grey', 'Active': 'blue', 'In Analysis': 'yellow',
            'Completed': 'green', 'Rejected': 'red', 'On Hold': 'orange'
        };
        if (frm.doc.status) {
            frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || 'grey');
        }
    },
    after_save(frm) {
        ThanatosPipeline.render(frm, 'get_ddd_pipeline');
    }
});
