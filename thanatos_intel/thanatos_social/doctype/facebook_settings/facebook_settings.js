// Verifica connessione alla Pagina Facebook.
frappe.ui.form.on('Facebook Settings', {
	refresh(frm) {
		frm.add_custom_button(__('Verifica connessione'), () => {
			frappe.call({
				method: 'thanatos_intel.thanatos_social.doctype.facebook_settings.facebook_settings.test_connection',
				freeze: true,
				freeze_message: __('Contatto Facebook...'),
				callback: (r) => {
					if (r.message && r.message.ok) {
						frappe.msgprint({
							title: __('Connessione riuscita'),
							indicator: 'green',
							message: __('Pagina: {0}<br>Follower: {1}', [
								frappe.utils.escape_html(r.message.name || '-'),
								r.message.followers != null ? r.message.followers : '-',
							]),
						});
					}
				},
			});
		});
	},
});
