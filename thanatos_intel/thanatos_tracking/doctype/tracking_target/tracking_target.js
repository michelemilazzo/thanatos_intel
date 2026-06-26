frappe.ui.form.on("Tracking Target", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Enrich OSINT"), () => {
			frappe.dom.freeze(__("Enriching..."));
			frappe.call({
				method: "thanatos_intel.thanatos_tracking.doctype.tracking_target.tracking_target.enrich",
				args: { target: frm.doc.name },
			}).then(() => {
				frappe.dom.unfreeze();
				frm.reload_doc();
			}).catch(() => frappe.dom.unfreeze());
		}, __("OSINT"));

		frm.add_custom_button(__("AI Next Steps"), () => {
			frappe.dom.freeze(__("Asking AI..."));
			frappe.call({
				method: "thanatos_intel.thanatos_tracking.doctype.tracking_target.tracking_target.ai_suggest",
				args: { target: frm.doc.name },
			}).then(() => {
				frappe.dom.unfreeze();
				frm.reload_doc();
			}).catch(() => frappe.dom.unfreeze());
		}, __("OSINT"));

		if (!frm.doc.photo && frm.doc.source_url) {
			frm.add_custom_button(__("Fetch Photo"), () => {
				frappe.dom.freeze(__("Fetching photo..."));
				frappe.call({
					method: "thanatos_intel.thanatos_tracking.most_wanted.fetch_photo",
					args: { target: frm.doc.name },
				}).then((r) => {
					frappe.dom.unfreeze();
					const m = r.message || {};
					if (m.ok) frm.reload_doc();
					else frappe.show_alert({ message: m.reason || __("No photo"), indicator: "orange" });
				}).catch(() => frappe.dom.unfreeze());
			}, __("OSINT"));
		}

		if (!frm.doc.photo && frm.doc.source === "Interpol Red Notice") {
			frm.add_custom_button(__("Interpol Photo (proxy)"), () => {
				frappe.dom.freeze(__("Fetching via residential proxy..."));
				frappe.call({
					method: "thanatos_intel.thanatos_tracking.most_wanted.fetch_interpol_photo",
					args: { target: frm.doc.name },
				}).then((r) => {
					frappe.dom.unfreeze();
					const m = r.message || {};
					if (m.ok) frm.reload_doc();
					else frappe.show_alert({ message: m.reason || __("No photo"), indicator: "orange" });
				}).catch(() => frappe.dom.unfreeze());
			}, __("OSINT"));
		}

		frm.add_custom_button(__("Add Lead"), () => {
			frappe.new_doc("Tracking Lead", { target: frm.doc.name });
		});

		if (frm.doc.investigation_case) {
			frm.add_custom_button(__("Open Case"), () => {
				frappe.set_route("Form", "Investigation Case", frm.doc.investigation_case);
			});
		}
	},
});
