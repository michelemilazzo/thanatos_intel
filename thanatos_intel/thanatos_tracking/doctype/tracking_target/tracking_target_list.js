frappe.listview_settings["Tracking Target"] = {
	onload(listview) {
		const run = (method, args, label) => {
			frappe.dom.freeze(__("Importing {0}...", [label]));
			frappe.call({ method, args }).then((r) => {
				frappe.dom.unfreeze();
				const m = r.message || {};
				if (m.results) {
					frappe.msgprint({
						title: __("Import All — {0} imported", [m.total_imported]),
						message: m.results.map((x) => `${x.source}: ${x.error ? "ERR" : x.imported}`).join("<br>"),
					});
				} else {
					frappe.show_alert({
						message: m.error ? __("{0} failed ({1})", [m.source, m.http || "network"])
							: __("{0}: {1} created, {2} updated", [m.source, m.created, m.updated]),
						indicator: m.error ? "red" : "green",
					});
				}
				listview.refresh();
			}).catch(() => frappe.dom.unfreeze());
		};

		// Tutte le azioni nel menu standard "..." (niente inner-button che si sovrappongono)
		listview.page.add_menu_item(__("Cerca ricercato"), () =>
			frappe.set_route("most-wanted-search"));

		listview.page.add_menu_item(__("Import — scegli fonte"), () => {
			frappe.call("thanatos_intel.thanatos_tracking.most_wanted.list_sources").then((r) => {
				const sources = r.message || [];
				frappe.prompt(
					[
						{ fieldname: "key", label: __("Source"), fieldtype: "Select", reqd: 1,
							options: sources.map((s) => ({ label: s.label, value: s.key })) },
						{ fieldname: "limit", label: __("Max (0 = all)"), fieldtype: "Int", default: 0 },
					],
					(v) => run("thanatos_intel.thanatos_tracking.most_wanted.import_dataset",
						{ key: v.key, limit: v.limit || 0 }, v.key),
					__("Import Most Wanted Source"), __("Import")
				);
			});
		});

		listview.page.add_menu_item(__("Import Interpol"), () =>
			run("thanatos_intel.thanatos_tracking.most_wanted.import_interpol", { limit: 0 }, "Interpol"));

		listview.page.add_menu_item(__("Import Europol"), () =>
			run("thanatos_intel.thanatos_tracking.most_wanted.import_europol", { limit: 0 }, "Europol"));

		listview.page.add_menu_item(__("Import TUTTE le fonti"), () => {
			frappe.confirm(__("Import all configured wanted lists? This may create thousands of records."),
				() => run("thanatos_intel.thanatos_tracking.most_wanted.import_all", { limit_per: 0 }, "all sources"));
		});

		listview.page.add_menu_item(__("Recupera foto mancanti"), () => {
			frappe.prompt(
				[{ fieldname: "limit", label: __("Max"), fieldtype: "Int", default: 100 }],
				(v) => {
					frappe.dom.freeze(__("Fetching photos..."));
					frappe.call({
						method: "thanatos_intel.thanatos_tracking.most_wanted.fetch_photos_bulk",
						args: { limit: v.limit || 100 },
					}).then((r) => {
						frappe.dom.unfreeze();
						const m = r.message || {};
						frappe.show_alert({ message: __("Photos: {0} ok, {1} failed", [m.ok, m.failed]), indicator: "blue" });
						listview.refresh();
					}).catch(() => frappe.dom.unfreeze());
				}, __("Fetch Missing Photos"), __("Fetch"));
		});
	},
};
