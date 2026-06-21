frappe.pages['thanatos-dossier'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: 'Dossier & Bacheca', single_column: true });
	frappe.thanatos && frappe.thanatos.nav(page, 'dossier');
	page.set_secondary_action('Aggiorna', () => load());
	injectCSS();
	const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
	const go = (...r) => frappe.set_route.apply(null, r);
	const $root = $('<div class="ds-wrap"><div class="ds-mut">Carico…</div></div>').appendTo(page.body);

	function load() {
		Promise.all([
			frappe.call('thanatos_intel.thanatos_core.dossier.dossier_data'),
			frappe.call('thanatos_intel.thanatos_core.dossier.bacheca', { limit: 30 }),
		]).then(([d, b]) => render(d.message || {}, b.message || []));
	}

	function render(d, updates) {
		const c = d.counts || {}, comp = d.compliance || {}, br = d.brand || {};
		let h = '';
		// Dossier IP
		h += '<div class="ds-sec">📦 Dossier — cosa abbiamo costruito</div>';
		h += `<div class="ds-card ds-brand"><img src="${esc(br.logo)}" alt="" style="height:40px"/>
			<div><div class="ds-co">${esc(br.company)}</div><div class="ds-mut">${esc(br.reg)}</div></div></div>`;
		const metrics = [
			['App Frappe', (d.apps || []).length], ['Moduli Thanatos', (d.modules || []).length],
			['DocType custom (IP)', d.custom_doctypes], ['Servizi a catalogo', d.services],
			['Policy ISO', comp.policy], ['Rischi censiti', comp.risk], ['Trattamenti (ROPA)', comp.ropa],
			['Capacità', (d.capabilities || []).length],
		];
		h += '<div class="ds-metrics">';
		metrics.forEach(m => { h += `<div class="ds-m"><div class="ds-m-v">${m[1] != null ? m[1] : 0}</div><div class="ds-m-l">${m[0]}</div></div>`; });
		h += '</div>';

		h += '<div class="ds-2col">';
		h += '<div><div class="ds-sub">Moduli &amp; aree</div><div class="ds-card ds-list">' +
			(d.modules || []).map(m => `<div class="ds-li">${esc(m)}</div>`).join('') + '</div></div>';
		h += '<div><div class="ds-sub">Capacità acquisite / proposte</div><div class="ds-card ds-list">' +
			((d.capabilities || []).length ? d.capabilities.map(x =>
				`<div class="ds-li ds-click" data-dt="Capability Acquisition" data-n="${esc(x.name)}">${esc(x.need)} <span class="ds-tag">${esc(x.suggested_app || '')} · ${esc(x.status)}</span></div>`).join('')
				: '<div class="ds-mut">Nessuna ancora.</div>') + '</div></div>';
		h += '</div>';

		h += '<div class="ds-sub">Dati operativi</div><div class="ds-metrics">';
		Object.keys(c).forEach(k => { h += `<div class="ds-m"><div class="ds-m-v">${c[k]}</div><div class="ds-m-l">${esc(k)}</div></div>`; });
		h += '</div>';

		// Bacheca
		h += '<div class="ds-sec" style="margin-top:30px">📣 Bacheca aggiornamenti</div>';
		h += `<div class="ds-card ds-form">
			<input id="ds-t" placeholder="Titolo aggiornamento…"/>
			<div class="ds-form-row">
				<select id="ds-cat"><option>Milestone</option><option>Nuovo servizio</option><option>Nuova capacità</option><option>Sistema</option><option>Avviso</option></select>
				<select id="ds-aud"><option>Interno</option><option>Clienti</option><option>Tutti</option></select>
				<button class="btn btn-sm btn-primary" id="ds-post">Pubblica</button>
			</div>
			<textarea id="ds-b" rows="2" placeholder="Dettagli (opzionale)…"></textarea>
		</div>`;
		h += '<div class="ds-feed">';
		if (updates.length) {
			updates.forEach(u => {
				h += `<div class="ds-up"><div class="ds-up-h"><span class="ds-tag ds-cat-${esc((u.category || '').replace(/\s/g, ''))}">${esc(u.category)}</span>
					<span class="ds-up-t">${esc(u.title)}</span>
					<span class="ds-tag">${esc(u.audience)}</span>
					<span class="ds-mut" style="margin-left:auto;font-size:11px">${esc(String(u.modified).slice(0, 10))}</span></div>
					${u.body ? `<div class="ds-up-b">${esc(u.body)}</div>` : ''}</div>`;
			});
		} else { h += '<div class="ds-mut">Nessun aggiornamento.</div>'; }
		h += '</div>';

		$root.html(h);
		$root.find('.ds-click').on('click', function () { go('Form', $(this).data('dt'), $(this).data('n')); });
		$root.find('#ds-post').on('click', function () {
			const t = $root.find('#ds-t').val().trim();
			if (!t) { frappe.show_alert({ message: 'Scrivi un titolo', indicator: 'orange' }); return; }
			frappe.call('thanatos_intel.thanatos_core.dossier.post_update', {
				title: t, body: $root.find('#ds-b').val(), category: $root.find('#ds-cat').val(), audience: $root.find('#ds-aud').val(),
			}).then(() => { frappe.show_alert({ message: 'Pubblicato', indicator: 'green' }); load(); });
		});
	}

	function injectCSS() {
		if (document.getElementById('ds-css')) return;
		const css = `
		.ds-wrap{padding:4px 2px 50px}
		.ds-mut{color:var(--text-muted);font-size:13px;padding:6px 2px}
		.ds-sec{font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:#C8A96E;margin:18px 4px 10px;font-weight:600}
		.ds-sub{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--text-muted);margin:18px 4px 8px;font-weight:600}
		.ds-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:14px}
		.ds-brand{display:flex;align-items:center;gap:14px;margin-bottom:14px}
		.ds-co{font-size:15px;font-weight:600;color:var(--text-color)}
		.ds-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:6px}
		@media(max-width:760px){.ds-metrics{grid-template-columns:repeat(2,1fr)}}
		.ds-m{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:12px}
		.ds-m-v{font-size:22px;font-weight:700;color:#C8A96E}.ds-m-l{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-top:3px}
		.ds-2col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:8px}@media(max-width:760px){.ds-2col{grid-template-columns:1fr}}
		.ds-list .ds-li{font-size:13px;color:var(--text-color);padding:6px 4px;border-bottom:1px solid var(--border-color)}
		.ds-list .ds-li:last-child{border-bottom:0}.ds-click{cursor:pointer}.ds-click:hover{color:#C8A96E}
		.ds-tag{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);border:1px solid var(--border-color);padding:1px 6px;border-radius:8px}
		.ds-form input,.ds-form textarea,.ds-form select{width:100%;background:var(--bg-color);color:var(--text-color);border:1px solid var(--border-color);border-radius:6px;padding:8px 10px;font-size:13px}
		.ds-form-row{display:flex;gap:8px;margin:8px 0}.ds-form-row select{flex:1}.ds-form-row .btn{white-space:nowrap}
		.ds-feed{margin-top:12px;display:flex;flex-direction:column;gap:8px}
		.ds-up{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:10px 12px}
		.ds-up-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.ds-up-t{font-size:13px;font-weight:500;color:var(--text-color)}
		.ds-up-b{font-size:12px;color:var(--text-muted);margin-top:6px;line-height:1.5}
		.ds-cat-Nuovacapacità,.ds-cat-Nuovoservizio{color:#29CD42;border-color:#29CD42}.ds-cat-Milestone{color:#C8A96E;border-color:#C8A96E}
		`;
		$('<style id="ds-css">').text(css).appendTo(document.head);
	}

	load();
};
