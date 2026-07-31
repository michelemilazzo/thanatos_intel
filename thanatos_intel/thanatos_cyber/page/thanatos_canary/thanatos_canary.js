frappe.pages['thanatos-canary'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: '🎯 Canary — Attribuzione', single_column: true });
	const $body = $(wrapper).find('.layout-main-section');
	const API = 'thanatos_intel.thanatos_cyber.canary.';
	let DATA = { base: '', tokens: [] };
	let SIG = '';
	const OPEN = {};   // ref -> pannello aperto ('hits' | 'dossier' | null)

	const $case = page.add_field({
		fieldtype: 'Link', options: 'Investigation Case', fieldname: 'case',
		label: 'Filtra per pratica', placeholder: 'tutte le pratiche…',
	});
	$case.$input && $case.$input.on('change', () => load());

	page.set_primary_action('Nuova esca', () => newEsca(), 'add');
	page.add_menu_item('Aggiorna hit dal worker (backfill)', () => {
		frappe.xcall(API + 'pull_hits', {}).then(r => {
			frappe.show_alert({ message: `Backfill: ${r.new || 0} nuovi hit`, indicator: r.error ? 'orange' : 'green' });
			load();
		});
	});

	$body.html(`<style>
	.cn-wrap{padding:6px 0 60px}
	.cn-intro{color:var(--text-muted,#888);font-size:13px;margin-bottom:16px;line-height:1.6}
	.cn-card{border:1px solid var(--border-color,#e3e3e3);border-radius:9px;margin-bottom:10px;background:var(--card-bg,#fff);overflow:hidden}
	.cn-card.off{opacity:.55}
	.cn-head{display:flex;align-items:center;gap:12px;padding:12px 14px;cursor:pointer}
	.cn-head:hover{background:var(--bg-color,#f7f7f7)}
	.cn-id{flex:1;min-width:0}
	.cn-id .nm{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
	.cn-id .sub{font-size:11px;color:var(--text-muted,#888);margin-top:2px}
	.cn-type{flex:0 0 auto;font-size:10px;text-transform:uppercase;letter-spacing:.5px;padding:3px 8px;border-radius:10px;border:1px solid var(--border-color,#ddd);color:var(--text-muted,#888)}
	.cn-badge{flex:0 0 auto;font-size:11px;padding:2px 9px;border-radius:11px;background:var(--bg-color,#f2f2f2);border:1px solid var(--border-color,#e0e0e0)}
	.cn-badge.hot{color:#b02a2a;border-color:#e0a0a0;background:rgba(224,160,160,.12)}
	.cn-badge.vpn{color:#8a5a1f;border-color:#caa64e}
	.cn-body{padding:0 14px 14px;border-top:1px solid var(--border-color,#eee)}
	.cn-link{display:flex;gap:8px;align-items:center;margin:12px 0;font-family:var(--font-stack-mono,monospace);font-size:12px;background:var(--bg-color,#f6f6f6);border:1px solid var(--border-color,#e5e5e5);border-radius:7px;padding:8px 10px}
	.cn-link .u{flex:1;overflow:auto;white-space:nowrap}
	.cn-actions{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
	.cn-actions .btn{font-size:12px}
	table.cn-tbl{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
	table.cn-tbl td,table.cn-tbl th{border:1px solid var(--border-color,#e6e6e6);padding:4px 7px;text-align:left;vertical-align:top}
	table.cn-tbl th{background:var(--bg-color,#f4f4f4);font-weight:600}
	tr.cn-vpn td{background:rgba(202,166,78,.10)}
	.cn-doss{margin-top:12px}
	.cn-doss h6{margin:14px 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted,#888)}
	.cn-guess{padding:12px 14px;border:1px solid #7fbf7f;border-radius:8px;background:rgba(127,191,127,.10);margin:6px 0 4px}
	.cn-guess .ip{font-family:var(--font-stack-mono,monospace);font-size:16px;font-weight:700}
	.cn-guess .src{font-size:11px;color:var(--text-muted,#777)}
	.cn-kpis{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
	.cn-kpi{flex:0 0 auto;font-size:11px;padding:4px 10px;border-radius:8px;border:1px solid var(--border-color,#e0e0e0);background:var(--bg-color,#f6f6f6)}
	.cn-kpi b{font-size:14px}
	.cn-empty{color:var(--text-muted,#999);font-style:italic;padding:28px;text-align:center}
	.cn-mono{font-family:var(--font-stack-mono,monospace)}
	</style>
	<div class="cn-wrap">
	  <div class="cn-intro"><b>Attribuzione — chi apre l'esca.</b> Crea un'esca legata a una pratica, manda il <b>link de-anon</b> (pagina civetta: cattura fingerprint device + WebRTC, rivela l'IP reale <b>anche dietro VPN</b>). Ogni apertura arriva in tempo reale. Il <b>Dossier de-anon</b> consolida IP residenziale vs VPN, IP reali da WebRTC, device e GPS.</div>
	  <div id="cn-list"><div class="cn-empty">Caricamento…</div></div>
	</div>`);

	const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
	const ago = ts => ts ? frappe.datetime.comment_when(ts) : '—';

	function copy(text) { frappe.utils.copy_to_clipboard(text); }

	function load() {
		const c = $case.get_value();
		frappe.xcall(API + 'dashboard', { investigation_case: c || undefined }).then(d => {
			DATA.base = d.base; DATA.tokens = d.tokens || [];
			DATA._recent = d.recent_hits || [];
			render();
		});
	}

	function sigOf() {
		return DATA.tokens.map(t => `${t.ref}:${t.hit_count}:${t.last_hit}:${t.status}`).join('|') +
			'#' + Object.keys(OPEN).filter(k => OPEN[k]).join(',');
	}

	function render() {
		const $list = $body.find('#cn-list');
		if (!DATA.tokens.length) {
			$list.html('<div class="cn-empty">Nessuna esca. Crea la prima con «Nuova esca».</div>');
			SIG = sigOf(); return;
		}
		$list.empty();
		DATA.tokens.forEach(t => $list.append(card(t)));
		SIG = sigOf();
		// riapri i pannelli espansi
		DATA.tokens.forEach(t => { if (OPEN[t.ref] === 'hits') renderHits(t.ref); else if (OPEN[t.ref] === 'dossier') renderDossier(t.ref); });
	}

	function card(t) {
		const isHp = t.token_type === 'Credenziale-esca' || t.token_type === 'Endpoint honeypot';
		const primary = isHp && t.planted
			? (t.token_type === 'Credenziale-esca' ? t.planted.credential.login_url : t.planted.honeypot.api_url)
			: ((t.links && t.links.page) || '');
		const off = t.status !== 'Attivo' ? ' off' : '';
		const hot = t.hit_count ? `<span class="cn-badge hot">${t.hit_count} hit</span>` : '<span class="cn-badge">0 hit</span>';
		const sub = [t.investigation_case ? '📁 ' + esc(t.investigation_case) : '', t.recipient ? '👤 ' + esc(t.recipient) : '', 'ref ' + esc(t.ref)].filter(Boolean).join(' · ');
		const $c = $(`<div class="cn-card${off}" data-ref="${esc(t.ref)}">
		  <div class="cn-head">
		    <div class="cn-id"><div class="nm">${esc(t.label)}</div><div class="sub">${sub} · ultimo ${ago(t.last_hit)}</div></div>
		    <span class="cn-type">${esc(t.token_type || '')}</span>
		    ${hot}
		  </div>
		  <div class="cn-body" style="display:none">
		    <div class="cn-link"><span class="u cn-mono">${esc(primary)}</span>
		      <button class="btn btn-xs btn-default cn-copy">${isHp ? 'Copia URL honeypot' : 'Copia link de-anon'}</button></div>
		    <div class="cn-actions">
		      <button class="btn btn-xs btn-primary cn-doss-btn">📋 Dossier de-anon</button>
		      ${isHp ? '<button class="btn btn-xs btn-default cn-planted">🔑 Credenziali piantate</button>' : ''}
		      <button class="btn btn-xs btn-default cn-hits-btn">Hit grezzi</button>
		      ${isHp ? '' : '<button class="btn btn-xs btn-default cn-copyother">Altri vettori…</button>'}
		      ${t.status === 'Attivo' ? '<button class="btn btn-xs btn-default cn-disable">Disattiva</button>' : ''}
		    </div>
		    <div class="cn-panel"></div>
		  </div>
		</div>`);
		$c.find('.cn-planted').on('click', e => { e.stopPropagation(); plantedDialog(t.token_type, t.planted); });
		$c.find('.cn-head').on('click', () => {
			const $b = $c.find('.cn-body'); const vis = $b.is(':visible'); $b.toggle(!vis);
			if (vis) { OPEN[t.ref] = null; }
		});
		$c.find('.cn-copy').on('click', e => { e.stopPropagation(); copy(primary); frappe.show_alert({ message: 'Copiato', indicator: 'green' }); });
		$c.find('.cn-doss-btn').on('click', e => { e.stopPropagation(); OPEN[t.ref] = 'dossier'; renderDossier(t.ref); });
		$c.find('.cn-hits-btn').on('click', e => { e.stopPropagation(); OPEN[t.ref] = 'hits'; renderHits(t.ref); });
		$c.find('.cn-copyother').on('click', e => { e.stopPropagation(); otherVectors(t); });
		$c.find('.cn-disable').on('click', e => {
			e.stopPropagation();
			frappe.confirm('Disattivare questa esca?', () => frappe.xcall(API + 'disable', { ref: t.ref }).then(() => load()));
		});
		return $c;
	}

	function panelOf(ref) {
		const $c = $body.find(`.cn-card[data-ref="${$.escapeSelector(ref)}"]`);
		$c.find('.cn-body').show();
		return $c.find('.cn-panel');
	}

	function renderHits(ref) {
		const $p = panelOf(ref); $p.html('<div class="cn-empty">Caricamento hit…</div>');
		frappe.xcall(API + 'hits', { ref }).then(rows => {
			if (!rows.length) { $p.html('<div class="cn-empty">Nessun hit ancora.</div>'); return; }
			const tr = rows.map(h => `<tr class="${h.suspect_net ? 'cn-vpn' : ''}">
			  <td>${esc(h.hit_ts)}</td><td>${esc(h.hit_type)}${h.via ? '/' + esc(h.via) : ''}</td>
			  <td class="cn-mono">${esc(h.ip)}${h.suspect_net ? ' ⚠' : ''}</td>
			  <td>${esc(h.country || '')} ${esc(h.city || '')}</td><td>${esc(h.org || '')}</td>
			  <td class="cn-mono">${esc(h.fp || '')}</td><td class="cn-mono">${esc(h.webrtc || '')}</td>
			  <td title="${esc(h.ua)}">${esc((h.ua || '').slice(0, 30))}</td></tr>`).join('');
			$p.html(`<table class="cn-tbl"><tr><th>quando (UTC)</th><th>tipo</th><th>IP</th><th>geo</th><th>rete</th><th>fp</th><th>WebRTC</th><th>UA</th></tr>${tr}</table>`);
		});
	}

	function renderDossier(ref) {
		const $p = panelOf(ref); $p.html('<div class="cn-empty">Composizione dossier…</div>');
		frappe.xcall(API + 'dossier', { ref }).then(d => {
			const s = d.summary || {};
			const guess = s.best_guess_ip
				? `<div class="cn-guess"><div class="ip">${esc(s.best_guess_ip)}</div>
				   <div class="src">IP reale più probabile — fonte: <b>${esc(s.best_guess_source)}</b>${s.best_guess_source === 'webrtc' ? ' (WebRTC, VPN-proof)' : ''}
				   ${s.behind_vpn ? ' · ⚠ il target naviga dietro VPN/datacenter' : ''}</div></div>`
				: '<div class="cn-empty">Ancora nessun segnale de-anon per questa esca.</div>';
			const kpi = (n, l) => `<div class="cn-kpi"><b>${n}</b> ${l}</div>`;
			const kpis = `<div class="cn-kpis">${kpi(s.total_hits || 0, 'hit')}${kpi(s.residential_ips || 0, 'IP residenziali')}${kpi(s.datacenter_vpn_ips || 0, 'IP VPN/DC')}${kpi(s.webrtc_public_ips || 0, 'WebRTC reali')}${kpi(s.devices || 0, 'device')}${s.cross_case_devices ? kpi(s.cross_case_devices, 'cross-caso') : ''}${s.gps_points ? kpi(s.gps_points, 'GPS') : ''}</div>`;
			const ipTbl = (arr, cls) => arr && arr.length
				? `<table class="cn-tbl">${arr.map(x => `<tr class="${cls || ''}"><td class="cn-mono">${esc(x.ip)}</td><td>${x.hits} hit</td><td>${esc(x.country || '')} ${esc(x.city || '')}</td><td>${esc(x.org || '')}${x.asn ? ' (AS' + esc(x.asn) + ')' : ''}</td></tr>`).join('')}</table>`
				: '<div class="cn-empty">—</div>';
			const wrtc = d.webrtc_public_ips && d.webrtc_public_ips.length
				? `<table class="cn-tbl">${d.webrtc_public_ips.map(x => `<tr><td class="cn-mono">${esc(x.ip)}</td><td>${x.hits} volte</td></tr>`).join('')}</table>`
				: '<div class="cn-empty">Nessun IP reale trapelato via WebRTC.</div>';
			const dev = d.devices && d.devices.length
				? `<table class="cn-tbl"><tr><th>fingerprint</th><th>hit</th><th>IP visti</th><th>cross-caso</th><th>UA</th></tr>${d.devices.map(f => `<tr class="${f.cross_case ? 'cn-vpn' : ''}"><td class="cn-mono">${esc(f.fp)}</td><td>${f.hits}</td><td class="cn-mono">${esc((f.ips || []).join(', '))}</td><td>${f.cross_case ? '⚠ ' + esc((f.also_cases || []).join(', ')) : '—'}</td><td title="${esc(f.ua)}">${esc((f.ua || '').slice(0, 26))}</td></tr>`).join('')}</table>`
				: '<div class="cn-empty">Nessun fingerprint (l\'esca non ha ancora caricato b.js: usa il link pagina).</div>';
			const gps = d.gps && d.gps.length
				? `<table class="cn-tbl"><tr><th>coordinate</th><th>±m</th><th>quando</th><th></th></tr>${d.gps.map(g => `<tr><td class="cn-mono">${esc(g.lat)}, ${esc(g.lon)}</td><td>${g.acc ? Math.round(g.acc) : ''}</td><td>${esc(g.ts)}</td><td><a href="https://maps.google.com/?q=${esc(g.lat)},${esc(g.lon)}" target="_blank">mappa</a></td></tr>`).join('')}</table>`
				: '';
			const att = d.credential_attempts && d.credential_attempts.length
				? `<h6>⚠ Tentativi credenziali / honeypot (device compromesso?)</h6><table class="cn-tbl"><tr><th>quando</th><th>tipo</th><th>utente/chiave</th><th>segreto provato</th><th>IP</th><th>rete</th></tr>${d.credential_attempts.map(a => `<tr class="cn-vpn"><td>${esc(a.ts)}</td><td>${esc(a.type)}</td><td class="cn-mono">${esc(a.user || '')}</td><td class="cn-mono">${esc(a.secret || '')}</td><td class="cn-mono">${esc(a.ip)}${a.suspect_net ? ' ⚠' : ''}</td><td>${esc(a.org || '')}</td></tr>`).join('')}</table>`
				: '';
			$p.html(`<div class="cn-doss">${guess}${kpis}${att}
			  <h6>IP residenziali (probabile identità reale)</h6>${ipTbl(d.residential_ips)}
			  <h6>WebRTC — IP pubblici reali (VPN-proof)</h6>${wrtc}
			  <h6>IP datacenter / VPN (dietro cui si nasconde)</h6>${ipTbl(d.datacenter_vpn_ips, 'cn-vpn')}
			  <h6>Device (fingerprint)</h6>${dev}
			  ${gps ? '<h6>Posizione GPS</h6>' + gps : ''}</div>`);
		}).catch(e => $p.html('<div class="cn-empty">Errore dossier.</div>'));
	}

	function otherVectors(t) {
		const L = t.links || {};
		const rows = [
			['Pixel (immagine)', L.pixel], ['Email pixel (HTML)', L.email_pixel],
			['PDF', L.pdf], ['Word .docx', L.docx], ['Excel .xlsx', L.xlsx],
			['Redirect-esca (/l)', L.link], ['QR target', L.qr_target], ['Sottodominio DNS', L.dns_host],
		].filter(r => r[1]);
		const d = new frappe.ui.Dialog({ title: 'Altri vettori — ' + t.label, size: 'large' });
		d.$body.html(`<div style="padding:4px 2px">${rows.map((r, i) => `<div style="margin-bottom:10px">
		  <div style="font-size:11px;color:var(--text-muted,#888);text-transform:uppercase;letter-spacing:.5px">${esc(r[0])}</div>
		  <div style="display:flex;gap:8px;align-items:center"><code style="flex:1;overflow:auto;white-space:nowrap;font-size:12px">${esc(r[1])}</code>
		  <button class="btn btn-xs btn-default cn-cp" data-i="${i}">Copia</button></div></div>`).join('')}</div>`);
		d.$body.find('.cn-cp').on('click', function () { copy(rows[$(this).data('i')][1]); frappe.show_alert({ message: 'Copiato', indicator: 'green' }); });
		d.show();
	}

	function plantedDialog(type, planted) {
		if (!planted) return;
		const creds = type === 'Credenziale-esca' ? planted.credential : planted.honeypot;
		const note = type === 'Credenziale-esca'
			? 'Pianta queste credenziali sul device del cliente (password manager, file config, note). Se il device è compromesso e un malware le esfiltra e le <b>prova</b> al login, l\'apertura viene loggata e attribuita a questa esca.'
			: 'Pianta questa chiave/endpoint API sul device (file .env, config). Ogni <b>uso</b> della chiave contro l\'endpoint honeypot viene loggato = segnale di device/credenziali compromesse.';
		const rows = Object.keys(creds).map(k => `<div style="margin-bottom:10px">
		  <div style="font-size:11px;color:var(--text-muted,#888);text-transform:uppercase;letter-spacing:.5px">${esc(k)}</div>
		  <div style="display:flex;gap:8px;align-items:center"><code style="flex:1;overflow:auto;white-space:nowrap;font-size:12px">${esc(creds[k])}</code>
		  <button class="btn btn-xs btn-default cn-cp" data-v="${encodeURIComponent(creds[k])}">Copia</button></div></div>`).join('');
		const d = new frappe.ui.Dialog({ title: '🔑 Credenziali-esca da piantare', size: 'large' });
		d.$body.html(`<div style="padding:4px 2px"><div style="font-size:12px;color:var(--text-muted,#888);line-height:1.6;margin-bottom:14px">${note}</div>${rows}</div>`);
		d.$body.find('.cn-cp').on('click', function () { copy(decodeURIComponent($(this).data('v'))); frappe.show_alert({ message: 'Copiato', indicator: 'green' }); });
		d.show();
	}

	function newEsca() {
		const d = new frappe.ui.Dialog({
			title: 'Nuova esca',
			fields: [
				{ fieldtype: 'Data', fieldname: 'label', label: 'Etichetta', reqd: 1, description: 'Nome interno dell\'esca' },
				{ fieldtype: 'Link', fieldname: 'investigation_case', label: 'Pratica', options: 'Investigation Case', default: $case.get_value() || '' },
				{ fieldtype: 'Select', fieldname: 'token_type', label: 'Tipo', default: 'Link / Pagina', options: ['Link / Pagina', 'Immagine (pixel)', 'Email (pixel)', 'PDF', 'Word (.docx)', 'Excel (.xlsx)', 'QR code', 'Redirect-esca', 'Sottodominio DNS', 'Credenziale-esca', 'Endpoint honeypot'].join('\n') },
				{ fieldtype: 'Data', fieldname: 'recipient', label: 'Destinatario', description: 'A chi la mandi (utile per attribuire fughe: un ref per copia)' },
				{ fieldtype: 'Section Break', label: 'Redirect-esca (solo se tipo = Redirect-esca)' },
				{ fieldtype: 'Data', fieldname: 'redir_url', label: 'URL destinazione', description: 'La pagina genuina attesa dal target (il link previewa e ci reindirizza dopo la cattura)' },
				{ fieldtype: 'Data', fieldname: 'redir_title', label: 'Titolo anteprima' },
			],
			primary_action_label: 'Crea',
			primary_action(v) {
				frappe.xcall(API + 'generate', {
					label: v.label, token_type: v.token_type, investigation_case: v.investigation_case || undefined,
					recipient: v.recipient || undefined, redir_url: v.redir_url || undefined, redir_title: v.redir_title || undefined,
				}).then(res => {
					d.hide();
					OPEN[res.ref] = null;
					if (res.planted) { plantedDialog(v.token_type, res.planted); frappe.show_alert({ message: 'Esca honeypot creata', indicator: 'green' }); }
					else { copy(res.links.page); frappe.show_alert({ message: 'Esca creata — link de-anon copiato', indicator: 'green' }); }
					load();
				});
			},
		});
		d.show();
	}

	load();
	setInterval(() => {
		if (document.hidden) return;
		frappe.xcall(API + 'dashboard', { investigation_case: $case.get_value() || undefined }).then(d => {
			const nd = { base: d.base, tokens: d.tokens || [], _recent: d.recent_hits || [] };
			const oldTokens = DATA.tokens; DATA.tokens = nd.tokens;
			const ns = sigOf(); DATA.tokens = oldTokens;
			if (ns !== SIG) { DATA = nd; render(); }
		});
	}, 20000);
};
