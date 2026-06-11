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
		if (frm.doc.entity_type === 'Company') {
			frm.add_custom_button(__('Verifica KYB'), () => {
				frappe.call({
					method: 'thanatos_intel.osint.companies_house.kyb_lookup',
					args: { entity_name: frm.doc.name },
					freeze: true,
					freeze_message: __('KYB Companies House in corso…'),
					callback(r) {
						const m = r.message || {};
						frappe.msgprint(__('KYB completato: {0} ({1}), bilanci {2}. {3} officer, {4} PSC, {5} persone e {6} societa collegate create.',
							[m.company, m.number, m.accounts_overdue ? 'OVERDUE' : 'ok', m.officers, m.psc, m.persons_created, m.linked_companies]));
						frm.reload_doc();
					}
				});
			}, __('Intelligence'));
		}
	}
});
