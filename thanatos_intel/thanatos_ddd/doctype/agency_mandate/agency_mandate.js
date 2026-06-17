frappe.ui.form.on('Agency Mandate', {
    refresh(frm) {
        // Genera PDF
        if (!frm.is_new() && frm.doc.status === 'Draft') {
            frm.add_custom_button(__('Genera PDF mandato'), () => {
                frappe.call({
                    method: 'thanatos_intel.thanatos_ddd.pdf.mandate.generate_mandate_pdf',
                    args: { mandate_name: frm.doc.name },
                    btn: this,
                    callback(r) {
                        if (r.message && r.message.file_url) {
                            frappe.show_alert({ message: 'PDF generato', indicator: 'green' });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Firma'));
        }

        // Invia per firma (MMOS Sign — metodo default)
        if (!frm.is_new() && frm.doc.mandate_pdf && frm.doc.status !== 'Signed') {
            frm.add_custom_button(__('Invia per firma (MMOS Sign) ✍'), () => {
                frappe.confirm(
                    'Inviare il mandato in firma con MMOS Sign?',
                    () => {
                        frappe.show_alert({ message: 'Invio in corso...', indicator: 'blue' });
                        frappe.call({
                            method: 'thanatos_intel.thanatos_ddd.signature_methods.dispatch',
                            args: { mandate: frm.doc.name, method: 'MMOS_SIGN' },
                            callback(r) {
                                if (r.message && r.message.status === 'sent') {
                                    frappe.show_alert({ message: 'Inviato! Link firma: ' + (r.message.sign_url || ''), indicator: 'green' });
                                    frm.reload_doc();
                                } else {
                                    frappe.msgprint({ title: 'Errore', message: r.message?.error || 'Errore invio firma', indicator: 'red' });
                                }
                            }
                        });
                    }
                );
            }, __('Firma'));
        }

        // Rigenera corpo dal template
        if (!frm.is_new() && frm.doc.status === 'Draft') {
            frm.add_custom_button(__('Rigenera bozza'), () => {
                frappe.confirm(
                    'Sovrascrivere il corpo del mandato con il template originale? Le modifiche manuali andranno perse.',
                    () => {
                        frappe.call({
                            method: 'thanatos_intel.thanatos_ddd.doctype.agency_mandate.agency_mandate.regenerate_body',
                            args: { mandate_name: frm.doc.name },
                            freeze: true,
                            freeze_message: 'Rigenerazione in corso…',
                            callback(r) {
                                if (r.message && r.message.ok) {
                                    frappe.show_alert({ message: 'Bozza rigenerata dal template', indicator: 'blue' });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __('Firma'));
        }


        // ── Email → bozza webmail ──
        if (!frm.is_new()) {
            frm.add_custom_button(__('✉ Proposta DDD'), () => {
                frappe.call({
                    method: 'thanatos_intel.mail_templates.draft_ddd_offer',
                    args: { mandate_name: frm.doc.name },
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

            if (frm.doc.signature_ref) {
                frm.add_custom_button(__('✉ Link Firma'), () => {
                    frappe.call({
                        method: 'thanatos_intel.mail_templates.draft_mandate_signing',
                        args: { mandate_name: frm.doc.name },
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
        }

        // Badge stato
        const colors = {
            'Draft': 'grey', 'Pending Signature': 'yellow',
            'Signed': 'green', 'Active': 'blue',
            'Completed': 'darkgrey', 'Terminated': 'red'
        };
        if (frm.doc.status) {
            frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || 'grey');
        }
    }
});
