frappe.pages['thanatos-rubrica'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper, title: 'Rubrica Clienti', single_column: true,
	});
	frappe.thanatos && frappe.thanatos.nav(page, 'rubrica');
	page.set_secondary_action('Nuovo cliente', () => frappe.new_doc('Investigation Client'));
	page.add_inner_button('Possibili duplicati', showDups);
	injectCSS();

	const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
	const go = (...r) => frappe.set_route.apply(null, r);
	let CUR = null;

	const $wrap = $(`<div class="rb-wrap">
		<div class="rb-left">
			<div class="rb-search"><input type="text" id="rb-q" placeholder="Cerca nome, email, telefono, P.IVA…"/></div>
			<div class="rb-list" id="rb-list"><div class="rb-empty">Caricamento…</div></div>
		</div>
		<div class="rb-right" id="rb-detail"><div class="rb-empty rb-ph">Seleziona un cliente a sinistra.</div></div>
	</div>`).appendTo(page.body);

	let t = null;
	$wrap.find('#rb-q').on('input', function () { clearTimeout(t); const v = this.value; t = setTimeout(() => loadList(v), 250); });

	function loadList(search) {
		frappe.call('thanatos_intel.thanatos_core.rubrica.clients_list', { search: search || '' })
			.then(r => renderList(r.message || []));
	}

	function renderList(rows) {
		const $l = $wrap.find('#rb-list');
		if (!rows.length) { $l.html('<div class="rb-empty">Nessun cliente.</div>'); return; }
		let h = '';
		rows.forEach(c => {
			const initials = (c.client_name || '?').split(' ').map(x => x[0]).slice(0, 2).join('').toUpperCase();
			h += `<div class="rb-item${CUR === c.name ? ' act' : ''}" data-c="${esc(c.name)}">
				<span class="rb-av">${esc(initials)}</span>
				<span class="rb-it-main"><span class="rb-it-n">${esc(c.client_name || c.name)}</span>
				<span class="rb-it-sub">${esc(c.client_type || '')}${c.email ? ' · ' + esc(c.email) : ''}</span></span>
				${onbChip(c.onboarding_status)}</div>`;
		});
		$l.html(h);
		$l.find('.rb-item').on('click', function () { CUR = $(this).data('c'); $l.find('.rb-item').removeClass('act'); $(this).addClass('act'); loadDetail(CUR); });
	}

	function onbChip(s) {
		if (!s) return '';
		const ok = s === 'Active', warn = /Pending|Review/.test(s);
		const cls = ok ? 'ok' : (warn ? 'warn' : 'mut');
		return `<span class="rb-chip rb-${cls}">${esc(s)}</span>`;
	}

	function loadDetail(client) {
		$wrap.find('#rb-detail').html('<div class="rb-empty">Caricamento scheda…</div>');
		frappe.call('thanatos_intel.thanatos_core.rubrica.client_detail', { client })
			.then(r => renderDetail(r.message || {}));
	}

	function renderDetail(d) {
		const i = d.info || {}, s = d.stats || {};
		const eur = n => '€' + frappe.format(n || 0, { fieldtype: 'Float', precision: 0 });
		const initials = (i.client_name || '?').split(' ').map(x => x[0]).slice(0, 2).join('').toUpperCase();
		let h = `<div class="rb-head">
			<span class="rb-av-lg">${esc(initials)}</span>
			<div class="rb-h-main"><div class="rb-h-n">${esc(i.client_name || i.name)}</div>
			<div class="rb-h-sub">${esc(i.client_type || '')}${i.country ? ' · ' + esc(i.country) : ''}${i.preferred_language ? ' · ' + esc(i.preferred_language) : ''}</div></div>
			<div class="rb-h-act">
				<button class="btn btn-xs btn-default" data-open>Scheda</button>
				<button class="btn btn-xs btn-primary" data-newcase>Nuovo caso</button>
			</div></div>`;

		// chip stato
		h += '<div class="rb-chips">';
		[['Onboarding', i.onboarding_status], ['KYC', i.kyc_status], ['KYB', i.kyb_status],
		['Abbonamento', i.subscription_status], ['Attribuzione', i.attribution_source]].forEach(([k, v]) => {
			if (v) h += `<span class="rb-chip rb-mut">${esc(k)}: <b>${esc(v)}</b></span>`;
		});
		h += '</div>';

		// kpi
		h += `<div class="rb-kpis">
			${kpi('Casi', s.cases)}${kpi('Speso', eur(s.spent))}${kpi('Credito', eur(s.credit))}
			${kpi('Fatture', s.invoices)}${kpi('Da incassare', eur(s.outstanding))}</div>`;

		// contatti
		h += '<div class="rb-sec">Contatti</div><div class="rb-card rb-contacts">';
		[['✉️', i.email], ['📞', i.phone], ['🧾', i.vat_number], ['🪪', i.codice_fiscale], ['🏠', i.address]].forEach(([ic, v]) => {
			if (v) h += `<div class="rb-contact"><span>${ic}</span><span>${esc(v)}</span></div>`;
		});
		h += '</div>';

		// timeline
		h += '<div class="rb-sec">Timeline interazioni</div><div class="rb-card rb-tl">';
		if ((d.timeline || []).length) {
			d.timeline.forEach(e => {
				h += `<div class="rb-ev" data-dt="${esc(e.dt)}" data-ref="${esc(e.ref)}">
					<span class="rb-ev-w">${esc(e.when)}</span>
					<span class="rb-ev-ic">${e.icon || '•'}</span>
					<span class="rb-ev-k">${esc(e.kind)}</span>
					<span class="rb-ev-t">${esc(e.title)}</span>
					${e.tag ? `<span class="rb-chip rb-mut">${esc(e.tag)}</span>` : ''}</div>`;
			});
		} else { h += '<div class="rb-empty">Nessuna interazione registrata.</div>'; }
		h += '</div>';

		const $d = $wrap.find('#rb-detail').html(h);
		$d.find('[data-open]').on('click', () => go('Form', 'Investigation Client', i.name));
		$d.find('[data-newcase]').on('click', () => frappe.new_doc('Investigation Case', { client: i.name }));
		$d.find('.rb-ev').on('click', function () { go('Form', $(this).data('dt'), $(this).data('ref')); });
	}

	function kpi(l, v) { return `<div class="rb-kpi"><div class="rb-kpi-v">${v != null ? v : 0}</div><div class="rb-kpi-l">${l}</div></div>`; }

	function showDups() {
		frappe.call('thanatos_intel.thanatos_core.rubrica.find_duplicates').then(r => {
			const dups = r.message || [];
			let h = dups.length ? '<div class="rb-dups">' : '<p>Nessun duplicato evidente. 👍</p>';
			dups.forEach(x => {
				h += `<div class="rb-dup"><b>${esc(x.field)}</b> = ${esc(x.value)} → ${x.count} clienti: ${x.names.map(n => `<a class="rb-dlink" data-n="${esc(n)}">${esc(n)}</a>`).join(', ')}</div>`;
			});
			h += dups.length ? '</div>' : '';
			const dlg = new frappe.ui.Dialog({ title: 'Possibili duplicati', fields: [{ fieldtype: 'HTML', options: h }] });
			dlg.show();
			dlg.$wrapper.find('.rb-dlink').on('click', function () { dlg.hide(); go('Form', 'Investigation Client', $(this).data('n')); });
		});
	}

	function injectCSS() {
		if (document.getElementById('rb-css')) return;
		const css = `
		.rb-wrap{display:grid;grid-template-columns:340px 1fr;gap:16px;padding:4px 2px 40px;min-height:70vh}
		@media(max-width:900px){.rb-wrap{grid-template-columns:1fr}}
		.rb-empty{color:var(--text-muted);padding:16px;font-size:13px}
		.rb-left{border:1px solid var(--border-color);border-radius:8px;background:var(--card-bg);overflow:hidden;display:flex;flex-direction:column;max-height:80vh}
		.rb-search{padding:10px;border-bottom:1px solid var(--border-color)}
		.rb-search input{width:100%;border:1px solid var(--border-color);border-radius:6px;padding:8px 10px;background:var(--bg-color);color:var(--text-color);font-size:13px}
		.rb-list{overflow-y:auto}
		.rb-item{display:flex;gap:10px;align-items:center;padding:10px 12px;border-bottom:1px solid var(--border-color);cursor:pointer}
		.rb-item:hover{background:var(--bg-color)}.rb-item.act{background:var(--bg-color);box-shadow:inset 3px 0 0 #C8A96E}
		.rb-av{width:32px;height:32px;border-radius:50%;background:#C8A96E;color:#0A0E1A;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex:0 0 auto}
		.rb-it-main{flex:1;min-width:0}
		.rb-it-n{display:block;font-size:13px;color:var(--text-color);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
		.rb-it-sub{display:block;font-size:11px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
		.rb-chip{font-size:10px;padding:2px 7px;border-radius:10px;white-space:nowrap}
		.rb-ok{background:rgba(41,205,66,.15);color:#29CD42}.rb-warn{background:rgba(236,173,75,.15);color:#ECAD4B}.rb-mut{background:var(--bg-color);color:var(--text-muted);border:1px solid var(--border-color)}
		.rb-right{min-width:0}
		.rb-ph{text-align:center;padding-top:80px}
		.rb-head{display:flex;gap:14px;align-items:center;margin:2px 2px 14px}
		.rb-av-lg{width:52px;height:52px;border-radius:50%;background:#C8A96E;color:#0A0E1A;display:flex;align-items:center;justify-content:center;font-size:19px;font-weight:700}
		.rb-h-main{flex:1}.rb-h-n{font-size:20px;font-weight:700;color:var(--text-color)}.rb-h-sub{font-size:12px;color:var(--text-muted);margin-top:2px}
		.rb-h-act{display:flex;gap:8px}
		.rb-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
		.rb-kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:6px}
		@media(max-width:700px){.rb-kpis{grid-template-columns:repeat(3,1fr)}}
		.rb-kpi{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:12px}
		.rb-kpi-v{font-size:19px;font-weight:700;color:#C8A96E}.rb-kpi-l{font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-top:3px}
		.rb-sec{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-muted);margin:20px 2px 8px;font-weight:600}
		.rb-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:8px}
		.rb-contacts{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:12px}
		.rb-contact{display:flex;gap:8px;font-size:13px;color:var(--text-color)}.rb-contact span:first-child{opacity:.7}
		.rb-tl .rb-ev{display:flex;gap:9px;align-items:center;padding:9px 10px;border-bottom:1px solid var(--border-color);cursor:pointer}
		.rb-tl .rb-ev:last-child{border-bottom:0}.rb-tl .rb-ev:hover{background:var(--bg-color)}
		.rb-ev-w{font-size:11px;color:#C8A96E;font-weight:600;min-width:92px;white-space:nowrap}
		.rb-ev-ic{font-size:14px}.rb-ev-k{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);min-width:96px}
		.rb-ev-t{font-size:13px;color:var(--text-color);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
		.rb-dup{padding:8px 4px;border-bottom:1px solid var(--border-color);font-size:13px}.rb-dlink{color:#C8A96E;cursor:pointer}
		`;
		$('<style id="rb-css">').text(css).appendTo(document.head);
	}

	loadList('');
};
