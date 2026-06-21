// Scheletro di navigazione condiviso del backend Thanatos.
// Ogni pagina desk Thanatos chiama frappe.thanatos.nav(page, '<sezione>')
// per avere la stessa barra a sezioni in cima → un'unica app coerente.
frappe.provide('frappe.thanatos');

frappe.thanatos.SECTIONS = [
	['cockpit', '🏠 Cockpit', ['thanatos-cockpit']],
	['casi', '📂 Casi', ['List', 'Investigation Case']],
	['rubrica', '👥 Rubrica', ['thanatos-rubrica']],
	['architetto', '🤖 Architetto AI', ['thanatos-ai-architect']],
	['intelligence', '🔍 Intelligence', ['List', 'OSINT Job']],
	['antifrode', '🛡 Antifrode', ['List', 'Blacklist Entry']],
	['ddd', '🪪 DDD', ['List', 'Agency Mandate']],
	['billing', '🧾 Billing', ['List', 'Sales Invoice']],
	['compliance', '📋 Compliance', ['List', 'Compliance Policy']],
];

frappe.thanatos._css = function () {
	if (document.getElementById('tnav-css')) return;
	const css = `
	.tnav{display:flex;gap:4px;flex-wrap:wrap;padding:6px 0 14px;margin:0 0 8px;border-bottom:1px solid var(--border-color)}
	.tnav-i{font-size:12px;letter-spacing:.3px;color:var(--text-muted);text-decoration:none;padding:6px 12px;border-radius:6px;cursor:pointer;white-space:nowrap;transition:background .12s,color .12s}
	.tnav-i:hover{background:var(--bg-color);color:var(--text-color)}
	.tnav-i.act{background:#C8A96E;color:#0A0E1A;font-weight:600}
	`;
	$('<style id="tnav-css">').text(css).appendTo(document.head);
};

frappe.thanatos.nav = function (page, active) {
	try {
		if (!page || !page.body) return;
		const $b = $(page.body);
		if ($b.find('.tnav').length) return;
		frappe.thanatos._css();
		let h = '<div class="tnav">';
		frappe.thanatos.SECTIONS.forEach(s => {
			h += `<a class="tnav-i ${s[0] === active ? 'act' : ''}" data-route='${JSON.stringify(s[2])}'>${s[1]}</a>`;
		});
		h += '</div>';
		$b.prepend(h);
		$b.find('.tnav-i').on('click', function () {
			try { frappe.set_route.apply(null, JSON.parse($(this).attr('data-route'))); } catch (e) { }
		});
	} catch (e) { }
};
