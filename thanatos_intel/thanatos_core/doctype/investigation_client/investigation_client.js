frappe.ui.form.on("Investigation Client", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Sollecita completamento dati"), () => {
			frappe.call({
				method: "thanatos_intel.notifications.onboarding_completion.send_completion_request",
				args: { client: frm.doc.name },
			}).then((r) => {
				const m = r.message || {};
				if (m.ok) {
					frappe.msgprint({
						title: __("Sollecito inviato a {0}", [m.sent_to]),
						message: __("Dati mancanti richiesti:") + "<ul><li>" + (m.missing || []).join("</li><li>") + "</li></ul>",
						indicator: "green",
					});
					frm.reload_doc();
				} else {
					frappe.show_alert({ message: m.reason || __("Niente da inviare"), indicator: "orange" });
				}
			});
		}, __("Onboarding"));
	},
});
