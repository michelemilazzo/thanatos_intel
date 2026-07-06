// Anteprima del documento del vault (PDF/immagine) in un pannello a destra del form.
frappe.ui.form.on('Client Vault Item', {
	refresh(frm) {
		const $main = frm.$wrapper.find('.layout-main-section-wrapper').first();
		if (!$main.length) return;
		$main.find('.cvi-preview').remove();
		const url = frm.doc.file;
		if (!url) { $main.css('display', ''); return; }
		const enc = encodeURI(url);
		const ext = (url.split('.').pop() || '').toLowerCase().split('?')[0];
		let inner = '';
		if (ext === 'pdf') {
			inner = `<iframe src="${enc}" style="width:100%;height:72vh;border:0"></iframe>`;
		} else if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) {
			inner = `<div style="max-height:72vh;overflow:auto"><img src="${enc}" style="max-width:100%;display:block;margin:auto"></div>`;
		} else {
			inner = `<div class="text-muted" style="padding:10px">Nessuna anteprima per .${frappe.utils.escape_html(ext)} — <a href="${enc}" target="_blank">apri il file ↗</a></div>`;
		}
		$main.css({ display: 'flex', gap: '16px', 'align-items': 'flex-start', 'flex-wrap': 'wrap' });
		$main.children('.layout-main-section').css({ flex: '1 1 460px', 'min-width': '360px' });
		$main.append(`<div class="cvi-preview" style="flex:1 1 420px;min-width:340px;position:sticky;top:60px;border:1px solid var(--border-color);border-radius:8px;overflow:hidden;background:var(--bg-color)">
			<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 10px;border-bottom:1px solid var(--border-color);font-size:11.5px;color:var(--text-muted)">
				<span>👁 Anteprima documento</span><a href="${enc}" target="_blank">apri in una scheda ↗</a>
			</div>${inner}</div>`);
	}
});
