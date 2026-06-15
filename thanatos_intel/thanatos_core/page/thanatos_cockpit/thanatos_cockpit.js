frappe.pages['thanatos-cockpit'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Thanatos Intel — Cockpit',
		single_column: true,
	});
	page.set_secondary_action('Aggiorna', () => load());
	injectCSS();
	const $root = $('<div class="tc-wrap"><div class="tc-loading">Caricamento cockpit…</div></div>').appendTo(page.body);

	function load() {
		$root.html('<div class="tc-loading">Caricamento…</div>');
		frappe.call('thanatos_intel.thanatos_core.cockpit.get_cockpit_data')
			.then(r => render(r.message || {}))
			.catch(() => $root.html('<div class="tc-loading">Errore nel caricamento.</div>'));
	}

	function render(d) {
		const kpi = d.kpi || {};
		const eur = n => '€' + frappe.format(n || 0, { fieldtype: 'Float', precision: 0 });
		const kpis = [
			['Casi aperti', kpi.casi_aperti, '#449CF0', 'investigation-case'],
			['Casi totali', kpi.casi_totali, '#8A909E', 'investigation-case'],
			['Case DDD', kpi.ddd, '#761ECE', 'diplomatic-eligibility-case'],
			['Reperti', kpi.reperti, '#C8A96E', 'investigation-evidence'],
			['Attività campo', kpi.attivita, '#29CD42', 'field-activity'],
			['Fatturato mese', eur(kpi.fatturato_mese), '#ECAD4B', 'sales-invoice'],
		];

		// Tile operativi (i FLUSSI dell'applicazione)
		const tiles = [
			['＋', 'Nuovo caso', () => frappe.new_doc('Investigation Case')],
			['📍', 'Cattura campo', () => window.open('/portal/field', '_blank')],
			['🤖', 'AI ingest', () => frappe.set_route('List', 'Investigation Case')],
			['🔎', 'OSINT', () => window.open('/portal/osint', '_blank')],
			['✉️', 'Webmail', () => window.open('/mail', '_blank')],
			['💳', 'Billing', () => frappe.set_route('List', 'Sales Invoice')],
		];

		let h = '';

		// KPI
		h += '<div class="tc-kpis">';
		kpis.forEach(([label, val, color, route]) => {
			h += `<div class="tc-kpi" data-route="${route}" style="--c:${color}">
				<div class="tc-kpi-v">${val != null ? val : 0}</div>
				<div class="tc-kpi-l">${label}</div></div>`;
		});
		h += '</div>';

		// Tile operativi
		h += '<div class="tc-section-t">Avvia</div><div class="tc-tiles">';
		tiles.forEach(([ic, label], i) => {
			h += `<div class="tc-tile" data-tile="${i}"><div class="tc-tile-ic">${ic}</div><div class="tc-tile-l">${label}</div></div>`;
		});
		h += '</div>';

		// 2 colonne: grafici + azioni
		h += '<div class="tc-cols">';
		h += '<div class="tc-col"><div class="tc-section-t">Casi per stato</div><div class="tc-card"><div id="tc-chart-casi"></div></div>';
		h += '<div class="tc-section-t">Mandati DDD per fase</div><div class="tc-card"><div id="tc-chart-mandati"></div></div></div>';

		// Azioni di oggi
		h += '<div class="tc-col"><div class="tc-section-t">Azioni di oggi</div><div class="tc-card tc-actions">';
		if ((d.azioni || []).length) {
			d.azioni.forEach(a => {
				h += `<div class="tc-act" data-dt="${a.doctype}" data-ref="${a.ref}">
					<span class="tc-act-type">${a.type}</span>
					<span class="tc-act-title">${frappe.utils.escape_html(a.title)}</span></div>`;
			});
		} else { h += '<div class="tc-empty">Nessuna azione in sospeso.</div>'; }
		h += '</div>';

		// Attività recenti
		h += '<div class="tc-section-t">Ultime attività sul campo</div><div class="tc-card tc-actions">';
		if ((d.attivita_recenti || []).length) {
			d.attivita_recenti.forEach(a => {
				h += `<div class="tc-act" data-dt="Field Activity" data-ref="${a.ref}">
					<span class="tc-act-type">${a.type}</span>
					<span class="tc-act-title">${frappe.utils.escape_html(a.title)}</span></div>`;
			});
		} else { h += '<div class="tc-empty">Nessuna attività registrata.</div>'; }
		h += '</div></div>';
		h += '</div>'; // cols

		// Flusso end-to-end
		h += '<div class="tc-section-t">Flusso operativo</div><div class="tc-flow">';
		(d.flow || []).forEach((f, i) => {
			if (i) h += '<div class="tc-flow-arrow">→</div>';
			h += `<div class="tc-flow-step" data-dt="${f.doctype}">
				<div class="tc-flow-n">${f.count}</div><div class="tc-flow-l">${f.label}</div></div>`;
		});
		h += '</div>';

		$root.html(h);

		// charts
		drawChart('#tc-chart-casi', d.casi_per_stato, ['#449CF0', '#8A909E', '#ECAD4B', '#29CD42', '#d05a5a']);
		drawChart('#tc-chart-mandati', d.mandati, ['#C8A96E', '#761ECE', '#29CD42', '#d05a5a']);

		// interazioni
		$root.find('.tc-kpi').on('click', function () { frappe.set_route('List', $(this).data('route')); });
		$root.find('.tc-act').on('click', function () { frappe.set_route('Form', $(this).data('dt'), $(this).data('ref')); });
		$root.find('.tc-flow-step').on('click', function () { frappe.set_route('List', $(this).data('dt')); });
		$root.find('.tc-tile').on('click', function () { tiles[$(this).data('tile')][2](); });
	}

	function drawChart(sel, data, colors) {
		if (!data || !data.length) { $(sel).html('<div class="tc-empty">Nessun dato</div>'); return; }
		new frappe.Chart(sel, {
			data: { labels: data.map(x => x.label), datasets: [{ values: data.map(x => x.value) }] },
			type: 'donut', height: 200, colors: colors,
		});
	}

	function injectCSS() {
		if (document.getElementById('tc-css')) return;
		const css = `
		.tc-wrap{padding:4px 2px 40px}
		.tc-loading,.tc-empty{color:var(--text-muted);padding:18px;font-size:13px}
		.tc-section-t{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-muted);margin:22px 4px 10px;font-weight:600}
		.tc-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
		@media(max-width:1100px){.tc-kpis{grid-template-columns:repeat(3,1fr)}}
		.tc-kpi{background:var(--card-bg);border:1px solid var(--border-color);border-left:3px solid var(--c);border-radius:8px;padding:16px 18px;cursor:pointer;transition:transform .12s}
		.tc-kpi:hover{transform:translateY(-2px)}
		.tc-kpi-v{font-size:26px;font-weight:700;color:var(--c);line-height:1}
		.tc-kpi-l{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-top:6px}
		.tc-tiles{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
		@media(max-width:1100px){.tc-tiles{grid-template-columns:repeat(3,1fr)}}
		.tc-tile{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:18px 10px;text-align:center;cursor:pointer;transition:border-color .12s,transform .12s}
		.tc-tile:hover{border-color:#C8A96E;transform:translateY(-2px)}
		.tc-tile-ic{font-size:24px}.tc-tile-l{font-size:12px;margin-top:8px;color:var(--text-color);font-weight:500}
		.tc-cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
		@media(max-width:980px){.tc-cols{grid-template-columns:1fr}}
		.tc-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:14px}
		.tc-actions{padding:6px}
		.tc-act{display:flex;gap:10px;align-items:center;padding:9px 12px;border-bottom:1px solid var(--border-color);cursor:pointer;border-radius:6px}
		.tc-act:last-child{border-bottom:0}.tc-act:hover{background:var(--bg-color)}
		.tc-act-type{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#fff;background:#C8A96E;padding:2px 7px;border-radius:3px;white-space:nowrap}
		.tc-act-title{font-size:13px;color:var(--text-color)}
		.tc-flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:18px}
		.tc-flow-step{text-align:center;cursor:pointer;padding:8px 16px;border-radius:8px;transition:background .12s}
		.tc-flow-step:hover{background:var(--bg-color)}
		.tc-flow-n{font-size:24px;font-weight:700;color:#C8A96E}.tc-flow-l{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px}
		.tc-flow-arrow{color:var(--text-muted);font-size:18px}
		`;
		$('<style id="tc-css">').text(css).appendTo(document.head);
	}

	load();
};
