frappe.ui.form.on("Agency Report", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Copia testo segnalazione"), () => {
			frm.call("build_text").then((r) => {
				const m = r.message || {};
				frappe.utils.copy_to_clipboard(m.text || "");
				frappe.show_alert({ message: __("Testo copiato — incollalo nel form ufficiale"), indicator: "green" });
			});
		});

		frm.add_custom_button(__("Apri canale ufficiale"), () => {
			frm.call("build_text").then((r) => {
				const url = (r.message || {}).channel;
				if (url) window.open(url, "_blank");
				else frappe.msgprint(__("Nessun canale ufficiale per questa agenzia — usa la polizia nazionale."));
			});
		});

		frm.add_custom_button(__("Anteprima testo"), () => {
			frm.call("build_text").then((r) => {
				frappe.msgprint({
					title: __("Testo segnalazione"),
					message: `<pre style="white-space:pre-wrap;">${frappe.utils.escape_html((r.message || {}).text || "")}</pre>`,
				});
			});
		});

		if (frm.doc.status !== "Submitted" && frm.doc.status !== "Closed") {
			frm.add_custom_button(__("Segna come Inviata"), () => {
				frm.set_value("status", "Submitted");
				frm.save();
			});
		}
	},

	agency(frm) {
		const ch = {
			FBI: "https://tips.fbi.gov/",
			Europol: "https://eumostwanted.eu/",
			Interpol: "https://www.interpol.int/en/Contacts/Contact-INTERPOL",
		}[frm.doc.agency] || "";
		frm.set_value("submission_channel", ch);
	},
});
