frappe.pages['thanatos-cockpit'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Thanatos Intel — Cockpit',
		single_column: true,
	});
	frappe.thanatos && frappe.thanatos.nav(page, 'cockpit');
	page.set_secondary_action('Aggiorna', () => load());
	injectCSS();
	const $root = $('<div class="tc-wrap"><div class="tc-loading">Caricamento cockpit…</div></div>').appendTo(page.body);

	const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
	const go = (...r) => frappe.set_route.apply(null, r);

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
			['Casi aperti', kpi.casi_aperti, '#449CF0', ['List', 'Investigation Case', { status: 'Open' }]],
			['Lead nuovi', kpi.lead_nuovi, '#ECAD4B', ['List', 'Intel Lead', { status: 'Nuovo' }]],
			['Appunt. oggi', kpi.appuntamenti_oggi, '#29CD42', ['List', 'Investigation Appointment']],
			['Reperti', kpi.reperti, '#C8A96E', ['List', 'Investigation Evidence']],
			['Casi totali', kpi.casi_totali, '#8A909E', ['List', 'Investigation Case']],
			['Fatturato mese', eur(kpi.fatturato_mese), '#761ECE', ['List', 'Sales Invoice']],
		];

		// Quick-launch verso le app Frappe sottostanti (il cockpit le orchestra)
		const tiles = [
			['ð¤', 'Architetto AI', () => go('thanatos-ai-architect')],
			['▶️', 'Nuova pratica', () => launchPractice()],
			['＋', 'Nuovo caso', () => frappe.new_doc('Investigation Case')],
			['📨', 'Lead / WhatsApp', () => go('List', 'Intel Lead')],
			['🔎', 'OSINT', () => frappe.new_doc('OSINT Job')],
			['📅', 'Agenda', () => go('List', 'Investigation Appointment')],
			['🗂️', 'Rubrica', () => go('thanatos-rubrica')],
			['📁', 'Drive', () => window.open('/drive', '_blank')],
			['👥', 'CRM', () => window.open('/crm', '_blank')],
			['🎫', 'Helpdesk', () => window.open('/helpdesk', '_blank')],
			['✉️', 'Webmail', () => window.open('https://webmail.thanatos.agency', '_blank')],
			['📬', 'Provisioning Mail', () => go('thanatos-mail-prov')],
			['👥', 'Rubrica generale', () => go('thanatos-rubrica-gen')],
			['💳', 'Billing', () => go('List', 'Sales Invoice')],
		];

		let h = '';

		// Header + Intel suggerisce
		h += `<div class="tc-head"><div><div class="tc-hi">Ciao, ${esc((d.fullname || '').split(' ')[0] || 'operatore')}</div>
			<div class="tc-sub">Ecco la tua giornata — ${frappe.datetime.str_to_user(frappe.datetime.now_date())}</div></div></div>`;

		h += '<div class="tc-section-t">🧠 Intel suggerisce</div><div class="tc-sugg">';
		(d.suggerimenti || []).forEach((s, i) => {
			h += `<div class="tc-sg tc-sg-${s.sev || 'info'}" data-sg="${i}">
				<span class="tc-sg-ic">${s.icon || '•'}</span><span>${esc(s.text)}</span></div>`;
		});
		h += '</div><div class="tc-aibrief" id="tc-aibrief"><div class="tc-aibrief-load">\ud83e\udde0 Intel sta analizzando la giornata\u2026</div></div>';

		// KPI
		h += '<div class="tc-kpis">';
		kpis.forEach(([label, val, color], i) => {
			h += `<div class="tc-kpi" data-kpi="${i}" style="--c:${color}">
				<div class="tc-kpi-v">${val != null ? val : 0}</div>
				<div class="tc-kpi-l">${label}</div></div>`;
		});
		h += '</div>';

		// Quick-launch
		h += '<div class="tc-section-t">Avvia</div><div class="tc-tiles">';
		tiles.forEach(([ic, label], i) => {
			h += `<div class="tc-tile" data-tile="${i}"><div class="tc-tile-ic">${ic}</div><div class="tc-tile-l">${label}</div></div>`;
		});
		h += '</div>';

		// 2 colonne
		h += '<div class="tc-cols">';

		// SX: Agenda + Prossimi step
		h += '<div class="tc-col">';
		h += '<div class="tc-section-t">📆 Agenda &amp; scadenziario</div><div class="tc-card tc-list">';
		if ((d.agenda || []).length) {
			d.agenda.forEach(a => {
				h += `<div class="tc-row" data-dt="${a.doctype}" data-ref="${esc(a.ref)}">
					<span class="tc-when">${esc(a.when)}${a.time ? ' ' + esc(a.time) : ''}</span>
					<span class="tc-ic">${a.icon || '•'}</span>
					<span class="tc-row-t">${esc(a.title)}</span>
					<span class="tc-tag">${esc(a.kind)}</span></div>`;
			});
		} else { h += '<div class="tc-empty">Niente in agenda nei prossimi 14 giorni.</div>'; }
		h += '</div>';

		h += '<div class="tc-section-t">🧭 Prossimi step guidati</div><div class="tc-card tc-list">';
		if ((d.prossimi_step || []).length) {
			d.prossimi_step.forEach(s => {
				h += `<div class="tc-row" data-dt="Investigation Case" data-ref="${esc(s.case)}">
					<span class="tc-st tc-st-${(s.status || '').replace(/\s/g, '')}">${esc(s.status)}</span>
					<span class="tc-row-t">${esc(s.label)}</span>
					<span class="tc-mut">${esc(s.case)}${s.due ? ' · ' + esc(s.due) : ''}</span></div>`;
			});
		} else { h += '<div class="tc-empty">Nessuno step in coda.</div>'; }
		h += '</div></div>';

		// DX: Inbox Intel + Casi attivi
		h += '<div class="tc-col">';
		h += '<div class="tc-section-t">📥 Inbox Intel (lead)</div><div class="tc-card tc-list">';
		if ((d.intel_inbox || []).length) {
			d.intel_inbox.forEach(l => {
				h += `<div class="tc-row" data-dt="Intel Lead" data-ref="${esc(l.ref)}">
					<span class="tc-tag">${esc(l.source)}</span>
					<span class="tc-row-t">${esc(l.snippet || l.from || l.ref)}</span>
					<span class="tc-pri tc-pri-${esc(l.priority)}">${esc(l.priority)}</span></div>`;
			});
		} else { h += '<div class="tc-empty">Inbox pulita.</div>'; }
		h += '</div>';

		h += '<div class="tc-section-t">📂 Casi attivi</div><div class="tc-card tc-list">';
		if ((d.casi_attivi || []).length) {
			d.casi_attivi.forEach(c => {
				h += `<div class="tc-row" data-dt="Investigation Case" data-ref="${esc(c.ref)}">
					<span class="tc-st tc-st-${(c.status || '').replace(/\s/g, '')}">${esc(c.status)}</span>
					<span class="tc-row-t">${esc(c.title)}</span>
					<span class="tc-mut">${esc(c.client)}</span>
					${c.priority && c.priority !== 'Normal' ? `<span class="tc-pri tc-pri-${esc(c.priority)}">${esc(c.priority)}</span>` : ''}</div>`;
			});
		} else { h += '<div class="tc-empty">Nessun caso attivo.</div>'; }
		h += '</div></div>';

		h += '</div>'; // cols

		// Grafico + flusso
		h += '<div class="tc-cols2">';
		h += '<div><div class="tc-section-t">Casi per stato</div><div class="tc-card"><div id="tc-chart-casi"></div></div></div>';
		h += '<div><div class="tc-section-t">Flusso operativo</div><div class="tc-flow">';
		(d.flow || []).forEach((f, i) => {
			if (i) h += '<div class="tc-flow-arrow">→</div>';
			h += `<div class="tc-flow-step" data-dt="${f.doctype}"><div class="tc-flow-n">${f.count}</div><div class="tc-flow-l">${f.label}</div></div>`;
		});
		h += '</div></div></div>';

		h += '<div class="tc-section-t">\ud83d\udcda Tutti gli strumenti</div><div class="tc-nav">';
		(d.nav || []).forEach(g => {
			h += `<div class="tc-nav-g"><div class="tc-nav-h">${esc(g.title)}</div>`;
			(g.items || []).forEach(it => { h += `<a class="tc-nav-l" data-kind="${esc(it.kind)}" data-to="${esc(it.to)}">${esc(it.label)}</a>`; });
			h += '</div>';
		});
		h += '</div>';

		$root.html(h);

		drawChart('#tc-chart-casi', d.casi_per_stato, ['#449CF0', '#8A909E', '#ECAD4B', '#29CD42', '#d05a5a']);

		// interazioni
		$root.find('.tc-kpi').on('click', function () { go.apply(null, kpis[$(this).data('kpi')][3]); });
		$root.find('.tc-tile').on('click', function () { tiles[$(this).data('tile')][2](); });
		$root.find('.tc-sg').on('click', function () { const r = (d.suggerimenti[$(this).data('sg')] || {}).route; if (r) go.apply(null, r); });
		$root.find('.tc-row').on('click', function () { const dt = $(this).data('dt'), ref = $(this).data('ref'); if (dt && ref) go('Form', dt, ref); });
		$root.find('.tc-flow-step').on('click', function () { go('List', $(this).data('dt')); });
		$root.find('.tc-nav-l').on('click', function () { const k = $(this).data('kind'), t = String($(this).data('to')); if (k === 'DocType') go('List', t); else if (t.indexOf('http') === 0 || t.indexOf('/') === 0) window.open(t, '_blank'); else go(t); });

		tcBrief($root);
	}

	function tcBrief($root) {
		const $b = $root.find('#tc-aibrief');
		if (!$b.length) return;
		frappe.call('thanatos_intel.thanatos_core.cockpit.ai_brief')
			.then(r => {
				const m = r.message || {};
				if (m.ok) {
					$b.html('<div class="tc-section-t">\ud83e\udde0 Intel \u2014 priorit\u00e0 di oggi</div>' + '<div class="tc-aibrief-card">' + frappe.utils.escape_html(m.text).replace(/\n/g, '<br>') + '</div>');
				} else { $b.html(''); }
			})
			.catch(() => $b.html(''));
	}

	function drawChart(sel, data, colors) {
		if (!data || !data.length) { $(sel).html('<div class="tc-empty">Nessun dato</div>'); return; }
		new frappe.Chart(sel, {
			data: { labels: data.map(x => x.label), datasets: [{ values: data.map(x => x.value) }] },
			type: 'donut', height: 220, colors: colors,
		});
	}

	function launchPractice() {
		frappe.call('thanatos_intel.workflow.api.available_blueprints').then(r => {
			const bps = r.message || [];
			if (!bps.length) { frappe.msgprint('Nessun blueprint attivo.'); return; }
			const byLabel = {};
			bps.forEach(b => byLabel[(b.blueprint_name || b.name)] = b.name);
			const d = new frappe.ui.Dialog({
				title: 'Nuova pratica guidata',
				fields: [
					{ fieldtype: 'Select', fieldname: 'bp', label: 'Servizio / Blueprint', options: Object.keys(byLabel).join('\n'), reqd: 1 },
					{ fieldtype: 'Data', fieldname: 'title', label: 'Titolo pratica', reqd: 1 },
					{ fieldtype: 'Small Text', fieldname: 'subject', label: 'Soggetto / obiettivo' },
				],
				primary_action_label: 'Crea e apri',
				primary_action(v) {
					frappe.call('thanatos_intel.workflow.api.open_practice',
						{ blueprint: byLabel[v.bp], case_title: v.title, subject: v.subject || '' }).then(rr => {
							const m = rr.message || {};
							if (m.case) { d.hide(); frappe.show_alert({ message: 'Pratica creata: ' + m.case, indicator: 'green' }); go('Form', 'Investigation Case', m.case); }
							else if (m.message) { frappe.msgprint(m.message); }
						});
				}
			});
			d.show();
		});
	}

	function injectCSS() {
		if (document.getElementById('tc-css')) return;
		const css = `
		.tc-wrap{padding:4px 2px 48px}
		.tc-loading,.tc-empty{color:var(--text-muted);padding:16px;font-size:13px}
		.tc-head{display:flex;justify-content:space-between;align-items:center;margin:6px 4px 2px}
		.tc-hi{font-size:22px;font-weight:700;color:var(--text-color)}
		.tc-sub{font-size:12px;color:var(--text-muted);margin-top:2px}
		.tc-section-t{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-muted);margin:22px 4px 10px;font-weight:600}
		.tc-sugg{display:flex;flex-wrap:wrap;gap:10px}
		.tc-sg{display:flex;align-items:center;gap:8px;padding:10px 14px;border-radius:8px;cursor:pointer;font-size:13px;border:1px solid var(--border-color);background:var(--card-bg);transition:transform .12s}
		.tc-sg:hover{transform:translateY(-2px)}
		.tc-sg-ic{font-size:16px}
		.tc-sg-warn{border-left:3px solid #ECAD4B}.tc-sg-info{border-left:3px solid #449CF0}.tc-sg-ok{border-left:3px solid #29CD42}
		.tc-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:4px}
		@media(max-width:1100px){.tc-kpis{grid-template-columns:repeat(3,1fr)}}
		.tc-kpi{background:var(--card-bg);border:1px solid var(--border-color);border-left:3px solid var(--c);border-radius:8px;padding:15px 16px;cursor:pointer;transition:transform .12s}
		.tc-kpi:hover{transform:translateY(-2px)}
		.tc-kpi-v{font-size:24px;font-weight:700;color:var(--c);line-height:1}
		.tc-kpi-l{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-top:6px}
		.tc-tiles{display:grid;grid-template-columns:repeat(10,1fr);gap:10px}
		@media(max-width:1100px){.tc-tiles{grid-template-columns:repeat(5,1fr)}}
		@media(max-width:600px){.tc-tiles{grid-template-columns:repeat(3,1fr)}}
		.tc-tile{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:14px 6px;text-align:center;cursor:pointer;transition:border-color .12s,transform .12s}
		.tc-tile:hover{border-color:#C8A96E;transform:translateY(-2px)}
		.tc-tile-ic{font-size:22px}.tc-tile-l{font-size:11px;margin-top:6px;color:var(--text-color);font-weight:500}
		.tc-cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
		@media(max-width:980px){.tc-cols{grid-template-columns:1fr}}
		.tc-cols2{display:grid;grid-template-columns:1fr 1.3fr;gap:20px;margin-top:4px}
		@media(max-width:980px){.tc-cols2{grid-template-columns:1fr}}
		.tc-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:8px}
		.tc-list .tc-row{display:flex;gap:9px;align-items:center;padding:9px 10px;border-bottom:1px solid var(--border-color);cursor:pointer;border-radius:6px}
		.tc-list .tc-row:last-child{border-bottom:0}.tc-list .tc-row:hover{background:var(--bg-color)}
		.tc-row-t{font-size:13px;color:var(--text-color);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
		.tc-when{font-size:11px;color:#C8A96E;font-weight:600;white-space:nowrap;min-width:78px}
		.tc-ic{font-size:14px}
		.tc-mut{font-size:11px;color:var(--text-muted);white-space:nowrap}
		.tc-tag{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);border:1px solid var(--border-color);padding:2px 6px;border-radius:3px;white-space:nowrap}
		.tc-st{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#fff;padding:2px 7px;border-radius:3px;white-space:nowrap;background:#8A909E}
		.tc-st-Open,.tc-st-InProgress{background:#449CF0}.tc-st-Blocked{background:#d05a5a}.tc-st-AwaitingClient{background:#ECAD4B}.tc-st-Done{background:#29CD42}.tc-st-Review{background:#761ECE}
		.tc-pri{font-size:10px;text-transform:uppercase;padding:2px 7px;border-radius:3px;color:#fff;white-space:nowrap;background:#8A909E}
		.tc-pri-Alta,.tc-pri-High{background:#ECAD4B}.tc-pri-Critica,.tc-pri-Urgent{background:#d05a5a}
		.tc-flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:16px}
		.tc-flow-step{text-align:center;cursor:pointer;padding:8px 12px;border-radius:8px;transition:background .12s}
		.tc-flow-step:hover{background:var(--bg-color)}
		.tc-flow-n{font-size:22px;font-weight:700;color:#C8A96E}.tc-flow-l{font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px}
		.tc-flow-arrow{color:var(--text-muted);font-size:16px}
		.tc-aibrief{margin-top:6px}
		.tc-aibrief-load{color:var(--text-muted);font-size:12px;padding:6px 2px}
		.tc-aibrief-card{background:var(--card-bg);border:1px solid #C8A96E;border-radius:8px;padding:14px;font-size:13px;line-height:1.6;color:var(--text-color);margin-top:6px}
		.tc-nav{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
		@media(max-width:1100px){.tc-nav{grid-template-columns:repeat(2,1fr)}}
		@media(max-width:600px){.tc-nav{grid-template-columns:1fr}}
		.tc-nav-g{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:12px}
		.tc-nav-h{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#C8A96E;font-weight:600;margin-bottom:8px}
		.tc-nav-l{display:block;padding:5px 6px;font-size:12px;color:var(--text-color);text-decoration:none;border-radius:5px;cursor:pointer}
		.tc-nav-l:hover{background:var(--bg-color);color:#C8A96E}
		`;
		$('<style id="tc-css">').text(css).appendTo(document.head);
	}

	load();
};
