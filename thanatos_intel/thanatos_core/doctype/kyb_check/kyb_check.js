frappe.ui.form.on('KYB Check', {
    refresh(frm) {
        const s = frm.doc.status;
        const colors = { 'Pending': 'grey', 'In Review': 'yellow', 'Approved': 'green', 'Rejected': 'red', 'Manual Review': 'orange' };
        frm.page.set_indicator(s, colors[s] || 'grey');

        if (!frm.is_new() && s === 'In Review') {
            frm.add_custom_button(__('✓ Approva'), () => {
                frappe.prompt({ label: 'Note (opzionale)', fieldtype: 'Small Text', fieldname: 'notes' }, (v) => {
                    frappe.call({
                        method: 'frappe.client.set_value',
                        args: { doctype: 'KYB Check', name: frm.doc.name,
                                fieldname: { status: 'Approved', reviewer_notes: v.notes || '', reviewed_by: frappe.session.user } },
                        callback() { frm.reload_doc(); }
                    });
                }, 'Approva KYB', 'Approva');
            }, __('Azione'));

            frm.add_custom_button(__('✗ Rifiuta'), () => {
                frappe.prompt([
                    { label: 'Motivo rifiuto', fieldtype: 'Small Text', fieldname: 'reason', reqd: 1 }
                ], (v) => {
                    frappe.call({
                        method: 'frappe.client.set_value',
                        args: { doctype: 'KYB Check', name: frm.doc.name,
                                fieldname: { status: 'Rejected', rejection_reason: v.reason, reviewed_by: frappe.session.user } },
                        callback() { frm.reload_doc(); }
                    });
                }, 'Rifiuta KYB', 'Rifiuta');
            }, __('Azione'));
        }

        if (!frm.is_new() && s === 'Pending') {
            frm.add_custom_button(__('Prendi in carico'), () => {
                frappe.call({
                    method: 'frappe.client.set_value',
                    args: { doctype: 'KYB Check', name: frm.doc.name, fieldname: { status: 'In Review' } },
                    callback() { frm.reload_doc(); }
                });
            });
        }
    }
});
