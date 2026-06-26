frappe.ui.form.on("Tracking Target", {
	refresh(frm) {
		if (frm.is_new()) return;

		const call = (method, freeze, onOk) => {
			frappe.dom.freeze(freeze);
			frappe.call({ method, args: { target: frm.doc.name } })
				.then((r) => {
					frappe.dom.unfreeze();
					const m = r.message || {};
					if (!onOk || onOk(m) !== false) frm.reload_doc();
				})
				.catch(() => frappe.dom.unfreeze());
		};
		const alertIf = (m) => {
			if (m && m.ok === false) {
				frappe.show_alert({ message: m.reason || __("Errore"), indicator: "orange" });
				return false;
			}
		};

		// --- Azioni dirette (le piu' usate) ---
		frm.add_custom_button(__("Enrich OSINT"), () =>
			call("thanatos_intel.thanatos_tracking.doctype.tracking_target.tracking_target.enrich",
				__("Enriching...")));

		if (frm.doc.description) {
			frm.add_custom_button(__("Traduci (IT)"), () =>
				call("thanatos_intel.thanatos_tracking.doctype.tracking_target.tracking_target.translate_record",
					__("Traduzione..."), alertIf));
		}

		// --- Resto nel menu standard "..." (no affollamento; dedup per label) ---
		frm.page.add_menu_item(__("AI Next Steps"), () =>
			call("thanatos_intel.thanatos_tracking.doctype.tracking_target.tracking_target.ai_suggest",
				__("Asking AI...")));

		frm.page.add_menu_item(__("Add Lead"), () =>
			frappe.new_doc("Tracking Lead", { target: frm.doc.name }));

		if (!frm.doc.photo && frm.doc.source === "Interpol Red Notice") {
			frm.page.add_menu_item(__("Interpol Photo (proxy)"), () =>
				call("thanatos_intel.thanatos_tracking.most_wanted.fetch_interpol_photo",
					__("Fetching via residential proxy..."), alertIf));
		} else if (!frm.doc.photo && frm.doc.source_url) {
			frm.page.add_menu_item(__("Fetch Photo"), () =>
				call("thanatos_intel.thanatos_tracking.most_wanted.fetch_photo",
					__("Fetching photo..."), alertIf));
		}

		if (frm.doc.investigation_case) {
			frm.page.add_menu_item(__("Open Case"), () =>
				frappe.set_route("Form", "Investigation Case", frm.doc.investigation_case));
		}
	},
});
