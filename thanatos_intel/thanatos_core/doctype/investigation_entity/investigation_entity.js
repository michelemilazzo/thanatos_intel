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
			frm.add_custom_button(__('Genera Company Profile (KYB)'), () => {
				frappe.prompt(
					[{ fieldname: 'cn', label: __('UK Company Number'), fieldtype: 'Data', reqd: 1,
					   default: (frm.doc.full_name || frm.doc.primary_identifier || '').match(/UK\s*([A-Z0-9]{6,8})/)?.[1] || '' }],
					(v) => {
						frappe.call({
							method: 'thanatos_intel.thanatos_corporate.doctype.company_profile.company_profile.sync_company',
							args: { company_number: v.cn, entity: frm.doc.name },
							freeze: true,
							freeze_message: __('Sync Companies House…'),
							callback(r) {
								const m = r.message || {};
								frappe.show_alert({ message: __('Company Profile {0}: {1} officer, {2} PSC, risk {3}', [m.name, m.officers, m.psc, m.risk_score]), indicator: 'green' });
								frappe.set_route('Form', 'Company Profile', m.name);
							}
						});
					}, __('KYB - Company Number'), __('Genera')
				);
			}, __('Intelligence'));
		}
	}
});
