frappe.ui.form.on('KYC Check', {
    refresh(frm) {
        const s = frm.doc.status;
        const colors = { 'Pending': 'grey', 'In Review': 'yellow', 'Approved': 'green', 'Rejected': 'red', 'Manual Review': 'orange' };
        frm.page.set_indicator(s, colors[s] || 'grey');

        if (!frm.is_new() && s === 'In Review') {
            frm.add_custom_button(__('✓ Approva'), () => {
                frappe.prompt({ label: 'Note (opzionale)', fieldtype: 'Small Text', fieldname: 'notes' }, (v) => {
                    frappe.call({
                        method: 'frappe.client.set_value',
                        args: { doctype: 'KYC Check', name: frm.doc.name,
                                fieldname: { status: 'Approved', reviewer_notes: v.notes || '', reviewed_by: frappe.session.user } },
                        callback() { frm.reload_doc(); }
                    });
                }, 'Approva KYC', 'Approva');
            }, __('Azione'));

            frm.add_custom_button(__('✗ Rifiuta'), () => {
                frappe.prompt([
                    { label: 'Motivo rifiuto', fieldtype: 'Small Text', fieldname: 'reason', reqd: 1 }
                ], (v) => {
                    frappe.call({
                        method: 'frappe.client.set_value',
                        args: { doctype: 'KYC Check', name: frm.doc.name,
                                fieldname: { status: 'Rejected', rejection_reason: v.reason, reviewed_by: frappe.session.user } },
                        callback() { frm.reload_doc(); }
                    });
                }, 'Rifiuta KYC', 'Rifiuta');
            }, __('Azione'));
        }


        if (!frm.is_new() && ['Pending', 'In Review', 'Manual Review'].includes(s)) {
            frm.add_custom_button(__('🎥 Identificazione live'), () => {
                frappe.call({
                    method: 'thanatos_intel.api.kyc_ident.make_link',
                    args: { kyc_check: frm.doc.name },
                    callback(r) {
                        const url = r.message.url;
                        const d = new frappe.ui.Dialog({
                            title: 'Link identificazione (monouso, 48h)',
                            fields: [
                                { fieldtype: 'HTML', options: `<p>Invia questo link al cliente: aprirà la camera per selfie, documento e video. L'esito del face match viene scritto automaticamente sulla pratica.</p><p><a href="${url}" target="_blank">${url}</a></p>` }
                            ],
                            primary_action_label: 'Copia link',
                            primary_action() { frappe.utils.copy_to_clipboard(url); d.hide(); }
                        });
                        d.show();
                    }
                });
            }, __('Azione'));
        }

        if (!frm.is_new() && s === 'Pending') {
            frm.add_custom_button(__('Prendi in carico'), () => {
                frappe.call({
                    method: 'frappe.client.set_value',
                    args: { doctype: 'KYC Check', name: frm.doc.name, fieldname: { status: 'In Review' } },
                    callback() { frm.reload_doc(); }
                });
            });
        }
    }
});
