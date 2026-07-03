frappe.ui.form.on('Party Payout', {
    refresh(frm) {
        // Bottone Esegui payout: mostrato solo se pending/queued e c'e Stripe Connect
        if (!frm.doc.__islocal
            && ['Pending', 'Queued', 'Failed'].includes(frm.doc.status)
            && frm.doc.stripe_connect_account_id) {
            frm.add_custom_button(__('Esegui Stripe Transfer'), () => {
                frappe.confirm(
                    __('Confermi bonifico di € {0} a {1} tramite Stripe Connect ({2})?', [
                        frm.doc.amount, frm.doc.beneficiary_name, frm.doc.stripe_connect_account_id
                    ]),
                    () => frm.call('execute').then((r) => {
                        frappe.msgprint({
                            title: __('Payout'),
                            message: JSON.stringify(r.message, null, 2),
                            indicator: r.message?.transfer_id ? 'green' : 'orange',
                        });
                        frm.reload_doc();
                    })
                );
            }, __('Actions')).addClass('btn-primary');
        }

        if (['Pending', 'Queued'].includes(frm.doc.status) && !frm.doc.stripe_connect_account_id) {
            frm.add_custom_button(__('Segna come pagato manualmente'), () => {
                frappe.confirm(
                    __('Confermi bonifico manuale (fuori Stripe)?'),
                    () => {
                        frm.set_value('status', 'Manual Bonifico');
                        frm.save();
                    }
                );
            }, __('Actions'));
        }

        // Info box: transfer id + link Stripe dashboard
        if (frm.doc.stripe_transfer_id) {
            frm.dashboard.add_indicator(
                __('Stripe Transfer: {0}', [frm.doc.stripe_transfer_id]),
                'green'
            );
        }
    },
});
