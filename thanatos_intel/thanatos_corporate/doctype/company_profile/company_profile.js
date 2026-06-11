frappe.ui.form.on('Company Profile', {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__('Sync da Companies House'), () => {
			frappe.call({
				method: 'sync_companies_house', doc: frm.doc,
				freeze: true, freeze_message: __('Sincronizzazione Companies House…'),
				callback(r) {
					const m = r.message || {};
					frappe.show_alert({message: __('KYB aggiornato: {0} officer, {1} PSC, risk {2}', [m.officers, m.psc, m.risk_score]), indicator: 'green'});
					frm.reload_doc();
				}
			});
		}, __('Intelligence'));

		if (frm.doc.companies_house_url) {
			frm.add_custom_button(__('Apri su Companies House'), () => {
				window.open(frm.doc.companies_house_url, '_blank');
			}, __('Intelligence'));
		}

		frm.add_custom_button(__('Crea Due Diligence Report'), () => {
			frappe.new_doc('Due Diligence Report', {
				company: frm.doc.name, investigation_case: frm.doc.investigation_case,
				title: 'KYB ' + frm.doc.company_name
			});
		}, __('Intelligence'));
	}
});
