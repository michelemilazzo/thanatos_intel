// Anteprima inline del documento del vault (PDF/immagine) sotto il campo File.
frappe.ui.form.on('Client Vault Item', {
	refresh(frm) {
		const $w = frm.fields_dict.file && frm.fields_dict.file.$wrapper;
		if (!$w) return;
		$w.find('.cvi-preview').remove();
		const url = frm.doc.file;
		if (!url) return;
		const enc = encodeURI(url);
		const ext = (url.split('.').pop() || '').toLowerCase().split('?')[0];
		let inner = '';
		if (ext === 'pdf') {
			inner = `<iframe src="${enc}" style="width:100%;height:520px;border:0"></iframe>`;
		} else if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) {
			inner = `<img src="${enc}" style="max-width:100%;max-height:520px;display:block;margin:auto">`;
		} else {
			inner = `<div class="text-muted" style="padding:10px">Nessuna anteprima per .${frappe.utils.escape_html(ext)} — <a href="${enc}" target="_blank">apri il file ↗</a></div>`;
		}
		$w.append(`<div class="cvi-preview" style="margin-top:8px;border:1px solid var(--border-color);border-radius:8px;overflow:hidden;background:var(--bg-color)">
			<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 10px;border-bottom:1px solid var(--border-color);font-size:11.5px;color:var(--text-muted)">
				<span>👁 Anteprima documento</span><a href="${enc}" target="_blank">apri in una scheda ↗</a>
			</div>${inner}</div>`);
	}
});
