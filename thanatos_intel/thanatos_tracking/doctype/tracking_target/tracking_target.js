function mwsLightbox(src, name) {
	const esc = frappe.utils.escape_html;
	const $ov = $(`
		<div style="position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:2000;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:zoom-out;">
			<img src="${esc(src)}" style="max-width:90vw;max-height:82vh;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.6);">
			<div style="color:#fff;margin-top:12px;font-size:15px;">${esc(name || "")}</div>
		</div>`);
	$ov.on("click", () => $ov.remove());
	$(document).on("keydown.mwsbox", (e) => { if (e.key === "Escape") { $ov.remove(); $(document).off("keydown.mwsbox"); } });
	$("body").append($ov);
}

frappe.ui.form.on("Tracking Target", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.photo) {
			setTimeout(() => {
				$(frm.wrapper).find('.form-sidebar img, [data-fieldname="photo"] .attach-image-display, [data-fieldname="photo"] img')
					.css("cursor", "zoom-in")
					.off("click.mwsbox")
					.on("click.mwsbox", (e) => {
						e.preventDefault();
						e.stopPropagation();
						mwsLightbox(frm.doc.photo, frm.doc.target_name);
					});
			}, 300);
		}

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
