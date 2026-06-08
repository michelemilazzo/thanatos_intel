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

        // Invia a DocuSeal
        if (!frm.is_new() && frm.doc.mandate_pdf && !frm.doc.docuseal_submission_id
                && frm.doc.status !== 'Signed') {
            frm.add_custom_button(__('Invia a DocuSeal ✍'), () => {
                frappe.confirm(
                    'Inviare il mandato a DocuSeal per la firma digitale?',
                    () => {
                        frappe.show_alert({ message: 'Invio in corso...', indicator: 'blue' });
                        frappe.call({
                            method: 'thanatos_intel.integrations.docuseal.send_to_docuseal',
                            args: { mandate_name: frm.doc.name },
                            callback(r) {
                                if (r.message && r.message.ok) {
                                    frappe.show_alert({ message: 'Inviato! Link firma: ' + (r.message.signing_url || ''), indicator: 'green' });
                                    frm.reload_doc();
                                } else {
                                    frappe.msgprint({ title: 'Errore', message: r.message?.error || 'Errore DocuSeal', indicator: 'red' });
                                }
                            }
                        });
                    }
                );
            }, __('Firma'));
        }

        // Link al PDF firmato
        if (frm.doc.docuseal_signing_url && frm.doc.status === 'Pending Signature') {
            frm.add_custom_button(__('Apri link firma'), () => {
                window.open(frm.doc.docuseal_signing_url, '_blank');
            }, __('Firma'));
        }

        // Copia link negli appunti
        if (frm.doc.docuseal_signing_url && frm.doc.status === 'Pending Signature') {
            frm.add_custom_button(__('Copia link firma'), () => {
                navigator.clipboard.writeText(frm.doc.docuseal_signing_url).then(() =>
                    frappe.show_alert({ message: 'Link copiato!', indicator: 'green' })
                );
            }, __('Firma'));
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
