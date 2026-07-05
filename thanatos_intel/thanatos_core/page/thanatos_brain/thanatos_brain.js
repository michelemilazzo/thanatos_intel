frappe.pages['thanatos-brain'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper, title: '🧠 Cervello Thanatos', single_column: true,
	});
	frappe.thanatos && frappe.thanatos.nav(page, 'cervello');
	injectCSS();
	const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));

	let SESSION = frappe.utils.get_random(12);
	let BUSY = false;

	const $w = $(`<div class="tb-wrap">
		<div class="tb-intro">Assistente operativo con accesso a tutta la struttura: casi, clienti, entità, lead,
			reperti e strumenti (screening KYC/PEP, UBO, visure, dossier, proforma…). Stesso cervello del
			centralino WhatsApp e della Switchboard.</div>
		<div class="tb-thread" id="tb-thread"></div>
		<div class="tb-input">
			<div id="tb-case" title="Caso di contesto: gli allegati diventano reperti di questo caso"></div>
			<textarea id="tb-msg" rows="2" placeholder="Es: a che punto è il caso Bomax? / fai screening sanzioni su…"></textarea>
			<button class="btn" id="tb-attach" title="Allega file">📎</button>
			<button class="btn btn-primary" id="tb-send">Invia</button>
			<button class="btn" id="tb-new" title="Nuova conversazione">↺</button>
			<input type="file" id="tb-file" multiple style="display:none">
		</div>
	</div>`).appendTo(page.body);

	const $thread = $w.find('#tb-thread');
	const $msg = $w.find('#tb-msg');

	function bubble(role, html) {
		const cls = role === 'user' ? 'tb-user' : 'tb-ai';
		const $b = $(`<div class="tb-bubble ${cls}"></div>`).html(html);
		$thread.append($b);
		$thread.scrollTop($thread[0].scrollHeight);
		return $b;
	}

	function md(text) {
		let h = esc(text);
		h = h.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
		h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
		h = h.replace(/\b(CASE-\d{4}-\d{4})\b/g,
			'<a href="/app/investigation-case/$1">$1</a>');
		h = h.replace(/\n/g, '<br>');
		return h;
	}

	function send() {
		const text = ($msg.val() || '').trim();
		if (!text || BUSY) return;
		BUSY = true;
		$msg.val('');
		bubble('user', esc(text));
		const $wait = bubble('ai', '<span class="tb-dots">Sto ragionando…</span>');
		frappe.call({
			method: 'thanatos_intel.ai.ops_brain.ask',
			args: { message: text, session_id: SESSION },
			callback: r => $wait.html(md((r.message || {}).reply || '(nessuna risposta)')),
			error: () => $wait.html('<span class="tb-err">Errore — riprova.</span>'),
			always: () => { BUSY = false; $msg.focus(); },
		});
	}

	// caso di contesto (opzionale) — gli allegati diventano reperti
	let CASE = null;
	const caseField = frappe.ui.form.make_control({
		df: { fieldtype: 'Link', options: 'Investigation Case', label: '', placeholder: 'Caso (opz.)' },
		parent: $w.find('#tb-case'), render_input: true,
	});
	caseField.refresh();
	caseField.$input.on('change', () => { CASE = caseField.get_value(); });

	function uploadFiles(files) {
		Array.from(files).forEach(f => {
			const $wait = bubble('user', `📎 <i>${esc(f.name)}</i> — carico…`);
			const fd = new FormData();
			fd.append('file', f);
			fd.append('is_private', '1');
			if (CASE) { fd.append('doctype', 'Investigation Case'); fd.append('docname', CASE); }
			fetch('/api/method/upload_file', {
				method: 'POST', body: fd,
				headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token },
			}).then(r => r.json()).then(r => {
				const fu = (r.message || {}).file_url;
				if (!fu) throw new Error('upload fallito');
				return frappe.call({
					method: 'thanatos_intel.ai.ops_brain.chat_upload',
					args: { file_url: fu, file_name: f.name, content_type: f.type,
						case: CASE, session_id: SESSION },
				}).then(res => {
					const ev = (res.message || {}).evidence;
					$wait.html(`📎 <b>${esc(f.name)}</b>` +
						(ev ? ` → reperto <a href="/app/investigation-evidence/${ev}">${ev}</a>` : ' caricato'));
					const $ai = bubble('ai', '<span class="tb-dots">Analizzo l\'allegato…</span>');
					frappe.call({
						method: 'thanatos_intel.ai.ops_brain.ask',
						args: { message: `Ho allegato il file "${f.name}" (${fu})` +
							(CASE ? ` sul caso ${CASE}` : '') + '. Dimmi cosa contiene e cosa fare.',
							session_id: SESSION },
						callback: rr => $ai.html(md((rr.message || {}).reply || '(nessuna risposta)')),
						error: () => $ai.html('<span class="tb-err">Errore analisi.</span>'),
					});
				});
			}).catch(() => $wait.html(`📎 <span class="tb-err">${esc(f.name)} — errore upload</span>`));
		});
	}

	$w.find('#tb-attach').on('click', () => $w.find('#tb-file').trigger('click'));
	$w.find('#tb-file').on('change', function () { uploadFiles(this.files); this.value = ''; });
	$thread.on('dragover', e => { e.preventDefault(); $thread.addClass('tb-drop'); });
	$thread.on('dragleave drop', e => { e.preventDefault(); $thread.removeClass('tb-drop'); });
	$thread.on('drop', e => {
		const files = e.originalEvent.dataTransfer && e.originalEvent.dataTransfer.files;
		if (files && files.length) uploadFiles(files);
	});

	$w.find('#tb-send').on('click', send);
	$msg.on('keydown', e => {
		if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
	});
	$w.find('#tb-new').on('click', () => {
		SESSION = frappe.utils.get_random(12);
		$thread.empty();
		bubble('ai', 'Nuova conversazione. Dimmi pure.');
		$msg.focus();
	});

	bubble('ai', 'Ciao — sono il cervello operativo Thanatos. Chiedimi dei casi, dei clienti o lancia uno strumento.');
	$msg.focus();

	function injectCSS() {
		if (document.getElementById('tb-css')) return;
		const c = document.createElement('style'); c.id = 'tb-css';
		c.textContent = `
		.tb-wrap{max-width:860px;margin:0 auto;display:flex;flex-direction:column;height:calc(100vh - 140px)}
		.tb-intro{color:var(--text-muted);font-size:12.5px;margin:6px 0 10px}
		.tb-thread{flex:1;overflow-y:auto;border:1px solid var(--border-color);border-radius:10px;
			padding:14px;background:var(--card-bg);display:flex;flex-direction:column;gap:10px}
		.tb-bubble{max-width:82%;padding:9px 13px;border-radius:12px;font-size:13.5px;line-height:1.55;word-wrap:break-word}
		.tb-user{align-self:flex-end;background:#C8A96E22;border:1px solid #C8A96E55}
		.tb-ai{align-self:flex-start;background:var(--control-bg);border:1px solid var(--border-color)}
		.tb-input{display:flex;gap:8px;margin-top:10px;align-items:flex-end}
		.tb-input textarea{flex:1;resize:vertical}
		.tb-input #tb-case{width:190px}
		.tb-input #tb-case .form-group{margin:0}
		.tb-drop{outline:2px dashed #C8A96E;outline-offset:-6px}
		.tb-dots{color:var(--text-muted);font-style:italic}
		.tb-err{color:var(--red-500)}
		.tb-bubble code{background:var(--control-bg);padding:1px 5px;border-radius:4px}`;
		document.head.appendChild(c);
	}
};
