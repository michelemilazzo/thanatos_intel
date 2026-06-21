frappe.pages['thanatos-ai-architect'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper, title: '🤖 Architetto AI del caso', single_column: true,
	});
	injectCSS();
	const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
	let PLAN = null, CLIENT = null;

	const $w = $(`<div class="ar-wrap">
		<div class="ar-intro">Descrivi il bisogno del cliente con parole tue. L'AI progetta il percorso su misura:
			step, documenti, servizi, <b>cosa ci manca</b> (e quale app Frappe usare) e il preventivo. Poi crei il caso con un click.</div>
		<div class="ar-input">
			<textarea id="ar-req" rows="4" placeholder="Es: un cliente vuole una chat protetta e cifrata per scambiare documenti del suo caso…"></textarea>
			<div class="ar-row"><div id="ar-client"></div>
			<button class="btn btn-primary" id="ar-go">Progetta percorso</button></div>
		</div>
		<div id="ar-out"></div>
	</div>`).appendTo(page.body);

	// selettore cliente (opzionale)
	const clientField = frappe.ui.form.make_control({
		df: { fieldtype: 'Link', options: 'Investigation Client', label: '', placeholder: 'Cliente (opzionale)' },
		parent: $w.find('#ar-client'), render_input: true,
	});
	clientField.refresh();
	clientField.$input.on('change', () => { CLIENT = clientField.get_value(); });

	$w.find('#ar-go').on('click', run);
	$w.find('#ar-req').on('keydown', e => { if (e.ctrlKey && e.key === 'Enter') run(); });

	function run() {
		const req = $w.find('#ar-req').val().trim();
		if (!req) { frappe.show_alert({ message: 'Scrivi il bisogno del cliente', indicator: 'orange' }); return; }
		$w.find('#ar-out').html('<div class="ar-load">🤖 L\'AI sta progettando il percorso…</div>');
		frappe.call('thanatos_intel.ai.case_architect.plan_from_request', { request: req, client: CLIENT })
			.then(r => {
				const m = r.message || {};
				if (!m.ok) { $w.find('#ar-out').html('<div class="ar-err">' + esc(m.error || 'AI non disponibile') + (m.raw ? '<pre>' + esc(m.raw) + '</pre>' : '') + '</div>'); return; }
				PLAN = m.plan; renderPlan(m.plan);
			})
			.catch(() => $w.find('#ar-out').html('<div class="ar-err">Errore nella chiamata AI.</div>'));
	}

	function renderPlan(p) {
		let h = `<div class="ar-card ar-head"><div class="ar-title">${esc(p.case_title || 'Caso')}</div>
			<div class="ar-sum">${esc(p.summary || '')}</div></div>`;

		h += '<div class="ar-sec">🧭 Percorso passo-passo</div><div class="ar-card">';
		(p.steps || []).forEach((s, i) => {
			h += `<div class="ar-step"><span class="ar-n">${i + 1}</span>
				<span class="ar-st-l">${esc(s.label)}</span>
				<span class="ar-chip ${s.actor === 'cliente' ? 'ar-cli' : ''}">${esc(s.actor || 'operatore')}</span>
				${s.service_code ? `<span class="ar-chip ar-svc">${esc(s.service_code)}</span>` : ''}
				<span class="ar-act">${esc(s.action || '')}</span></div>`;
		});
		h += '</div>';

		if ((p.capability_gaps || []).length) {
			h += '<div class="ar-sec">⚠️ Ci manca (capacità da acquisire) — prima cerchiamo su Frappe</div><div class="ar-card ar-gaps">';
			p.capability_gaps.forEach(g => {
				h += `<div class="ar-gap"><div><b>${esc(g.need)}</b> → app Frappe: <b class="ar-app">${esc(g.suggested_frappe_app || '—')}</b></div>
					<div class="ar-gap-n">${esc(g.note || '')}</div></div>`;
			});
			h += '</div>';
		}

		const cols = (arr, render) => '<div class="ar-card">' + ((arr || []).length ? (arr.map(render).join('')) : '<div class="ar-mut">—</div>') + '</div>';
		h += '<div class="ar-2col">';
		h += '<div><div class="ar-sec">📄 Documenti da produrre</div>' + cols(p.documents, d => `<div class="ar-li">${esc(d)}</div>`) + '</div>';
		h += '<div><div class="ar-sec">🧰 Servizi dal catalogo</div>' + cols(p.services, s => `<div class="ar-li">${esc(s)}</div>`) + '</div>';
		h += '</div>';

		let tot = 0;
		h += '<div class="ar-sec">💶 Preventivo indicativo</div><div class="ar-card">';
		(p.quote || []).forEach(q => { tot += (q.amount_eur || 0); h += `<div class="ar-q"><span>${esc(q.item)}</span><span>€${esc(q.amount_eur || 0)}</span></div>`; });
		h += `<div class="ar-q ar-tot"><span>Totale</span><span>€${tot}</span></div></div>`;

		h += `<div class="ar-actions">
			<button class="btn btn-primary" id="ar-create">✓ Crea caso da questo piano</button>
			<button class="btn btn-default" id="ar-copy">Copia piano (JSON)</button></div>`;

		$w.find('#ar-out').html(h);
		$w.find('#ar-create').on('click', createCase);
		$w.find('#ar-copy').on('click', () => { frappe.utils.copy_to_clipboard(JSON.stringify(PLAN, null, 2)); });
	}

	function createCase() {
		frappe.confirm('Creo un Investigation Case con questi step?', () => {
			frappe.call('thanatos_intel.ai.case_architect.create_case_from_plan',
				{ plan: JSON.stringify(PLAN), client: CLIENT })
				.then(r => {
					const m = r.message || {};
					if (m.ok) { frappe.show_alert({ message: 'Caso creato: ' + m.case, indicator: 'green' }); frappe.set_route('Form', 'Investigation Case', m.case); }
				});
		});
	}

	function injectCSS() {
		if (document.getElementById('ar-css')) return;
		const css = `
		.ar-wrap{padding:6px 2px 50px;max-width:980px}
		.ar-intro{color:var(--text-muted);font-size:13px;margin:2px 2px 14px;line-height:1.5}
		.ar-input textarea{width:100%;border:1px solid var(--border-color);border-radius:8px;padding:12px;background:var(--card-bg);color:var(--text-color);font-size:14px}
		.ar-row{display:flex;align-items:center;gap:12px;margin-top:10px}
		.ar-row #ar-client{flex:1;max-width:320px}
		.ar-load,.ar-mut{color:var(--text-muted);font-size:13px;padding:14px}
		.ar-err{color:#d05a5a;font-size:13px;padding:14px}.ar-err pre{white-space:pre-wrap;font-size:11px;color:var(--text-muted)}
		.ar-sec{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-muted);margin:22px 4px 8px;font-weight:600}
		.ar-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:14px}
		.ar-head{border-left:3px solid #C8A96E}
		.ar-title{font-size:18px;font-weight:700;color:var(--text-color)}.ar-sum{font-size:13px;color:var(--text-muted);margin-top:6px;line-height:1.5}
		.ar-step{display:flex;align-items:center;gap:10px;padding:8px 4px;border-bottom:1px solid var(--border-color);flex-wrap:wrap}
		.ar-step:last-child{border-bottom:0}
		.ar-n{width:22px;height:22px;border-radius:50%;background:#C8A96E;color:#0A0E1A;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
		.ar-st-l{font-size:13px;color:var(--text-color);font-weight:500}
		.ar-act{font-size:12px;color:var(--text-muted);flex:1 1 100%;margin-left:32px}
		.ar-chip{font-size:10px;text-transform:uppercase;letter-spacing:.5px;padding:2px 8px;border-radius:10px;background:var(--bg-color);color:var(--text-muted);border:1px solid var(--border-color)}
		.ar-cli{color:#ECAD4B;border-color:#ECAD4B}.ar-svc{color:#449CF0;border-color:#449CF0}
		.ar-gaps{border-left:3px solid #ECAD4B}
		.ar-gap{padding:8px 4px;border-bottom:1px dashed var(--border-color)}.ar-gap:last-child{border-bottom:0}
		.ar-app{color:#29CD42}.ar-gap-n{font-size:12px;color:var(--text-muted);margin-top:3px}
		.ar-2col{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:760px){.ar-2col{grid-template-columns:1fr}}
		.ar-li{font-size:13px;color:var(--text-color);padding:5px 2px;border-bottom:1px solid var(--border-color)}.ar-li:last-child{border-bottom:0}
		.ar-q{display:flex;justify-content:space-between;font-size:13px;padding:6px 2px;border-bottom:1px solid var(--border-color)}
		.ar-tot{font-weight:700;color:#C8A96E;border-bottom:0}
		.ar-actions{margin-top:20px;display:flex;gap:10px}
		`;
		$('<style id="ar-css">').text(css).appendTo(document.head);
	}
};
