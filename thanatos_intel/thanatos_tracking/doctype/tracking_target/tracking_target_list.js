frappe.listview_settings["Tracking Target"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Import Interpol"), () => {
			frappe.prompt(
				[{ fieldname: "pages", label: __("Pages (x50)"), fieldtype: "Int", default: 1 }],
				(v) => {
					frappe.dom.freeze(__("Importing Interpol Red Notices..."));
					frappe.call({
						method: "thanatos_intel.thanatos_tracking.most_wanted.import_interpol",
						args: { pages: v.pages || 1 },
					}).then((r) => {
						frappe.dom.unfreeze();
						frappe.show_alert({ message: __("Interpol: {0} created, {1} updated",
							[r.message.created, r.message.updated]), indicator: "green" });
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
