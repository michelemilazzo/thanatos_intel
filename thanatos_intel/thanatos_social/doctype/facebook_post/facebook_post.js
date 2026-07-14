// Pulsanti azione per Facebook Post.
frappe.ui.form.on('Facebook Post', {
	refresh(frm) {
		if (frm.is_new()) return;

		const status = frm.doc.status;

		if (status !== 'Pubblicato' && status !== 'Annullato') {
			frm.add_custom_button(__('Pubblica ora'), () => {
				frappe.confirm(__('Pubblicare subito sulla Pagina Facebook?'), () => {
					frm.call('publish_now').then(() => frm.reload_doc());
				});
			}).addClass('btn-primary');

			if (frm.doc.scheduled_time) {
				frm.add_custom_button(__('Programma'), () => {
					frm.call('schedule').then(() => frm.reload_doc());
				});
			}
		}

		if (status === 'Programmato') {
			frm.add_custom_button(__('Annulla programmazione'), () => {
				frm.call('cancel_schedule').then(() => frm.reload_doc());
			});
		}

		if (status === 'Pubblicato' && frm.doc.fb_post_id) {
			frm.add_custom_button(__('Aggiorna Insights'), () => {
				frm.call('refresh_insights').then(() => frm.reload_doc());
			});
			if (frm.doc.permalink) {
				frm.add_custom_button(__('Apri su Facebook'), () => {
					window.open(frm.doc.permalink, '_blank');
				});
			}
		}
	},
});
