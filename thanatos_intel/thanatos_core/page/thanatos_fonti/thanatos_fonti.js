frappe.pages['thanatos-fonti'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: '🧰 Fonti & Chiavi OSINT', single_column: true });
	const $body = $(wrapper).find('.layout-main-section');
	injectCss();
	$body.html('<div id="tf-keys"></div><div id="tf-cat" style="margin-top:24px"></div>');
	page.set_primary_action('↻ Aggiorna', () => { loadKeys(); loadCatalog(); });
	loadKeys();
	loadCatalog();

	function esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }

	function loadKeys() {
		const $k = $body.find('#tf-keys').html('<div class="tf-mut">Carico fonti con chiave…</div>');
		frappe.call('thanatos_intel.osint.api_keys.key_sources').then(r => {
			const srcs = r.message || [];
			const conf = srcs.filter(s => s.configured).length;
			let h = '<div class="tf-h">🔑 Chiavi API <span class="tf-mut">(' + conf + '/' + srcs.length + ' configurate · gratis, senza carta)</span></div>';
			h += '<div class="tf-grid">';
			srcs.forEach(s => {
				const ck = s.config_key || (s.keys && s.keys[0] && s.keys[0].config_key) || '';
				const reg = s.register_url || s.signup || s.url || '';
				const ok = s.configured;
				h += '<div class="tf-card">'
					+ '<div class="tf-card-h"><span class="tf-name">' + esc(s.name) + '</span>'
					+ '<span class="tf-badge ' + (ok ? 'tf-on' : 'tf-off') + '">' + (ok ? 'configurata' : 'mancante') + '</span></div>'
					+ (s.category ? '<div class="tf-mut tf-cat-l">' + esc(s.category) + '</div>' : '')
					+ (reg ? '<a href="' + esc(reg) + '" target="_blank" rel="noopener" class="tf-reg">↗ Registrati (free)</a>' : '')
					+ '<div class="tf-row"><input class="form-control input-sm tf-key" data-ck="' + esc(ck) + '" placeholder="' + (ok ? '•••• già salvata, reinserisci per cambiare' : esc(ck)) + '">'
					+ '<button class="btn btn-xs btn-primary tf-save" data-ck="' + esc(ck) + '">Salva</button></div>'
					+ '</div>';
			});
			h += '</div>';
			$k.html(h);
			$k.find('.tf-save').on('click', function () {
				const ck = $(this).data('ck');
				const val = $k.find('.tf-key[data-ck="' + ck + '"]').val().trim();
				if (!val) { frappe.show_alert({ message: 'Inserisci la chiave', indicator: 'orange' }); return; }
				frappe.call({ method: 'thanatos_intel.osint.api_keys.save_api_key', args: { config_key: ck, value: val },
					callback: () => { frappe.show_alert({ message: ck + ' salvata', indicator: 'green' }); loadKeys(); } });
			});
		});
	}

	function loadCatalog() {
		const $c = $body.find('#tf-cat').html('<div class="tf-mut">Carico catalogo…</div>');
		frappe.call('thanatos_intel.osint.tool_catalog.catalogo_completo').then(r => {
			const c = r.message || {}; const st = c.stats || {}; const mb = c.modello || {};
			let h = '<div class="tf-h">📚 Catalogo strumenti <span class="tf-mut">(' + (st.capacita || 0) + ' capacità · '
				+ (st.fonti_totali || 0) + ' fonti, <b style="color:#1a8a2e">' + (st.fonti_gratuite || 0) + ' gratuite</b> · '
				+ (st.famiglie_openapi || 0) + ' famiglie openapi)</span></div>';
			if (mb.principio) h += '<div class="tf-bill">💶 ' + esc(mb.catena) + ' — <b>' + esc(mb.principio) + '</b></div>';
			h += '<table class="tf-tbl"><thead><tr><th>Capacità</th><th>🟢 Gratis dà</th><th>🔴 Paid aggiunge</th><th>⚠ Manca nel free</th></tr></thead><tbody>';
			(c.capacita || []).forEach(x => {
				const cons = x.consiglio === 'free' ? '<span class="tf-t-free">usa free</span>' : (x.consiglio === 'paid' ? '<span class="tf-t-paid">paid</span>' : '<span class="tf-t-mix">misto</span>');
				h += '<tr><td><b>' + esc(x.capacita) + '</b> ' + cons + '</td>'
					+ '<td class="' + ((x.free || []).length ? 'tf-ok' : '') + '">' + esc(x.free_dati || '—') + '</td>'
					+ '<td>' + esc(x.paid_dati || '—') + '</td>'
					+ '<td class="tf-gap">' + esc(x.gap || '—') + '</td></tr>';
			});
			h += '</tbody></table>';
			$c.html(h);
		});
	}

	function injectCss() {
		if (document.getElementById('tf-css')) return;
		const css = `
		#tf-keys,#tf-cat{font-size:13px}
		.tf-h{font-size:16px;font-weight:500;margin:8px 0 12px;color:var(--text-color)}
		.tf-mut{color:var(--text-muted);font-size:12.5px;font-weight:400}
		.tf-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
		.tf-card{border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);padding:12px 14px}
		.tf-card-h{display:flex;justify-content:space-between;align-items:center;gap:8px}
		.tf-name{font-weight:500;color:var(--text-color)}
		.tf-cat-l{margin:2px 0 6px;text-transform:capitalize}
		.tf-badge{font-size:10px;border-radius:8px;padding:1px 7px;white-space:nowrap}
		.tf-on{color:#1a8a2e;border:1px solid #29CD42}
		.tf-off{color:#a33;border:1px solid #e0879a}
		.tf-reg{display:inline-block;margin:2px 0 8px;font-size:12px;color:#C8A96E}
		.tf-row{display:flex;gap:6px}
		.tf-row .tf-key{flex:1}
		.tf-bill{background:var(--bg-color);border:1px solid #ECAD4B;border-radius:8px;padding:8px 10px;margin-bottom:12px;font-size:12px;line-height:1.5}
		.tf-tbl{width:100%;border-collapse:collapse;font-size:12.5px}
		.tf-tbl th{text-align:left;padding:7px 9px;border-bottom:1px solid var(--border-color);color:var(--text-muted);font-weight:500}
		.tf-tbl td{padding:8px 9px;border-bottom:1px solid var(--border-color);vertical-align:top}
		.tf-tbl td.tf-ok{color:#1a8a2e}
		.tf-tbl td.tf-gap{color:#a33}
		.tf-t-free{font-size:10px;color:#1a8a2e;border:1px solid #29CD42;border-radius:8px;padding:1px 6px;margin-left:4px}
		.tf-t-paid{font-size:10px;color:#a33;border:1px solid #e0879a;border-radius:8px;padding:1px 6px;margin-left:4px}
		.tf-t-mix{font-size:10px;color:#9a7d2e;border:1px solid #ECAD4B;border-radius:8px;padding:1px 6px;margin-left:4px}
		`;
		$('<style id="tf-css">').text(css).appendTo(document.head);
	}
};
