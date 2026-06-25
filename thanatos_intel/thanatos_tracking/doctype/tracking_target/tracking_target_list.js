frappe.listview_settings["Tracking Target"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Import Interpol"), () => {
			frappe.prompt(
				[{ fieldname: "limit", label: __("Max targets (0 = all ~6400)"), fieldtype: "Int", default: 500 }],
				(v) => {
					frappe.dom.freeze(__("Importing Interpol Red Notices..."));
					frappe.call({
						method: "thanatos_intel.thanatos_tracking.most_wanted.import_interpol",
						args: { limit: v.limit || 0 },
					}).then((r) => {
						frappe.dom.unfreeze();
						const m = r.message || {};
						frappe.show_alert({
							message: m.error ? __("Interpol import failed ({0})", [m.http || "network"])
								: __("Interpol: {0} created, {1} updated", [m.created, m.updated]),
							indicator: m.error ? "red" : "green",
						});
						listview.refresh();
					}).catch(() => frappe.dom.unfreeze());
				},
				__("Import Interpol Red Notices"), __("Import")
			);
		}, __("Most Wanted"));

		listview.page.add_inner_button(__("Import Europol"), () => {
			frappe.dom.freeze(__("Importing Europol..."));
			frappe.call({
				method: "thanatos_intel.thanatos_tracking.most_wanted.import_europol",
			}).then((r) => {
				frappe.dom.unfreeze();
				const m = r.message || {};
				frappe.show_alert({
					message: m.stub ? __("Europol: {0}", [m.note])
						: __("Europol: {0} created, {1} updated", [m.created, m.updated]),
					indicator: m.stub ? "orange" : "green",
				});
				listview.refresh();
			}).catch(() => frappe.dom.unfreeze());
		}, __("Most Wanted"));
	},
};
