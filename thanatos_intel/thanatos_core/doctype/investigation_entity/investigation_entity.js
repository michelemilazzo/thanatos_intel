frappe.ui.form.on('Investigation Entity', {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.entity_type === 'Wallet') {
			frm.add_custom_button(__('Traccia wallet'), () => {
				frappe.call({
					method: 'thanatos_intel.osint.blockchain.trace_wallet',
					args: { address: frm.doc.primary_identifier },
					freeze: true,
					freeze_message: __('Tracciamento on-chain in corso (30-60s)…'),
					callback(r) {
						const m = r.message || {};
						frappe.msgprint(__('Tracciamento completato: {0} tx, {1} controparti verificate, {2} hub creati, {3} case aggiornati. Ultimo movimento: {4}.',
							[m.tx_count, m.counterparties, m.hubs_created, m.cases_updated, m.last_seen]));
						frm.reload_doc();
					}
				});
			}, __('Intelligence'));
		}
	}
});
