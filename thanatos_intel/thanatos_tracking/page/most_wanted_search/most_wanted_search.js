frappe.pages["most-wanted-search"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Most Wanted — Ricerca"),
		single_column: true,
	});

	const $body = $(wrapper).find(".layout-main-section");
	$body.html(`
		<div class="mws-wrap" style="max-width:820px;margin:0 auto;">
			<div style="display:flex;gap:8px;margin:8px 0 4px;">
				<input type="text" class="form-control mws-q" placeholder="${__("Nome, alias o ID…")}" style="flex:1;font-size:15px;">
				<button class="btn btn-primary mws-go">${__("Cerca")}</button>
			</div>
			<div class="text-muted small">${__("Cerca un soggetto nel database ricercati (Interpol / Europol / FBI / liste nazionali).")}</div>
			<div class="mws-status" style="margin:14px 0;font-weight:600;"></div>
			<div class="mws-results"></div>
		</div>
	`);

	const $q = $body.find(".mws-q");
	const $status = $body.find(".mws-status");
	const $res = $body.find(".mws-results");

	const esc = frappe.utils.escape_html;
	const badge = (t, c) => `<span class="indicator-pill ${c}" style="margin-right:6px;">${esc(t || "")}</span>`;

	function lightbox(src, name) {
		const $ov = $(`
			<div class="mws-lightbox" style="position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:2000;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:zoom-out;">
				<img src="${esc(src)}" style="max-width:90vw;max-height:82vh;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.6);">
				<div style="color:#fff;margin-top:12px;font-size:15px;">${esc(name || "")}</div>
			</div>
		`);
		$ov.on("click", () => $ov.remove());
		$(document).on("keydown.mwsbox", (e) => { if (e.key === "Escape") { $ov.remove(); $(document).off("keydown.mwsbox"); } });
		$("body").append($ov);
	}

	function render(rows, q) {
		$res.empty();
		if (!rows.length) {
			$status.html(`<span style="color:var(--red-500)">✗ ${__("Nessun ricercato trovato per")} “${esc(q)}”.</span>`);
			return;
		}
		$status.html(`<span style="color:var(--green-600)">✓ ${__("Trovati")} ${rows.length} ${__("record")}.</span>`);
		rows.forEach((r) => {
			const img = r.photo
				? `<img class="mws-photo" src="${esc(r.photo)}" title="${__("Clicca per ingrandire")}" style="width:90px;height:112px;object-fit:cover;border-radius:6px;border:1px solid var(--border-color);cursor:zoom-in;">`
				: `<div style="width:90px;height:112px;border-radius:6px;background:var(--gray-200);display:flex;align-items:center;justify-content:center;color:var(--gray-500);">—</div>`;
			const stColor = { Active: "red", Located: "orange", Apprehended: "green", Cold: "gray", Closed: "gray" }[r.status] || "gray";
			const card = $(`
				<div class="mws-card" style="display:flex;gap:12px;padding:10px;border:1px solid var(--border-color);border-radius:8px;margin-bottom:8px;cursor:pointer;align-items:center;">
					${img}
					<div style="flex:1;min-width:0;">
						<div style="font-weight:600;font-size:15px;">${esc(r.target_name)}</div>
						<div class="small text-muted" style="margin:2px 0;">${esc(r.aliases ? r.aliases.split("\n").slice(0,3).join(" · ") : "")}</div>
						<div style="margin-top:4px;">
							${badge(r.source, "blue")}
							${badge(r.status, stColor)}
							${badge(r.priority, "purple")}
							${r.nationality ? badge(r.nationality, "gray") : ""}
							${r.date_of_birth ? `<span class="small text-muted">${esc(r.date_of_birth)}</span>` : ""}
						</div>
					</div>
				</div>
			`);
			card.on("click", () => frappe.set_route("Form", "Tracking Target", r.name));
			card.find(".mws-photo").on("click", (e) => {
				e.stopPropagation();
				lightbox(r.photo, r.target_name);
			});
			$res.append(card);
		});
	}

	function run() {
		const q = ($q.val() || "").trim();
		if (q.length < 2) {
			$status.text(__("Inserisci almeno 2 caratteri."));
			$res.empty();
			return;
		}
		$status.text(__("Ricerca…"));
		frappe.call({
			method: "thanatos_intel.thanatos_tracking.most_wanted.search_targets",
			args: { query: q },
		}).then((r) => render(r.message || [], q));
	}

	$body.find(".mws-go").on("click", run);
	$q.on("keydown", (e) => { if (e.key === "Enter") run(); });
	setTimeout(() => $q.focus(), 200);
};
