// Gli operatori Thanatos atterrano sul Cockpit invece del Desk grezzo.
// Admin (System Manager) e utenti con funzioni speciali restano sul Desk.
frappe.provide('frappe');
(function () {
	function land() {
		try {
			var roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles)
				|| frappe.user_roles || [];
			var ops = ["Investigator", "Investigation Manager", "Thanatos Investigator",
				"Thanatos Supervisor", "Thanatos Director", "Thanatos Analyst", "Analyst",
				"Thanatos Intake Officer", "Thanatos Legal Officer", "Thanatos Compliance Officer"];
			var isOp = roles.some(function (r) { return ops.indexOf(r) >= 0; });
			var isAdmin = roles.indexOf("System Manager") >= 0 || roles.indexOf("Administrator") >= 0;
			if (!isOp || isAdmin) return;
			var r = (frappe.get_route_str && frappe.get_route_str()) || "";
			if (!r || r === "Workspaces" || r.indexOf("Workspaces") === 0) {
				frappe.set_route("thanatos-cockpit");
			}
		} catch (e) { }
	}
	if (frappe.router && frappe.router.on) {
		// una sola volta, al primo instradamento del desk
		var done = false;
		frappe.after_ajax && frappe.after_ajax(function () {
			if (done) return; done = true; setTimeout(land, 250);
		});
	}
})();
