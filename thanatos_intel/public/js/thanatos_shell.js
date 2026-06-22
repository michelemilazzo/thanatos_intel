
// Thanatos Top Nav — sticky bar persistente su tutto il desk
frappe.provide('frappe.thanatos');

frappe.thanatos.SECTIONS = [
	{key:'cockpit', label:'🏠 Cockpit', route:['thanatos-cockpit']},
	{key:'comunicazioni', label:'💬 Comunicazioni', route:['comunicazioni']},
	{key:'casi', label:'📂 Casi', route:['List','Investigation Case']},
	{key:'ddd', label:'🪪 DDD', route:['List','Diplomatic Eligibility Case']},
	{key:'mandati', label:'📜 Mandati', route:['List','Agency Mandate']},
	{key:'firme', label:'🖊 Firme', route:['List','Signature Request']},
	{key:'billing', label:'💶 Billing', route:['List','Diplomatic Proforma']},
	{key:'rubrica', label:'👥 Rubrica', route:['List','Customer']},
	{key:'intelligence', label:'🔍 Intelligence', route:['List','OSINT Job']},
	{key:'antifrode', label:'🛡 Antifrode', route:['List','Blacklist Entry']},
	{key:'compliance', label:'📋 Compliance', route:['List','Risk Score']},
	{key:'architetto', label:'🤖 AI', route:['thanatos-ai-architect']},
];

frappe.thanatos._injectCSS = function () {
	if (document.getElementById('tnav-css')) return;
	const css = `
	#tnav-bar{position:sticky;top:0;z-index:100;background:#0a0e1a;color:#fff;padding:6px 16px;display:flex;gap:4px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #1f2742;font-family:inherit}
	#tnav-bar .tnav-logo{display:flex;align-items:center;gap:8px;color:#C8A96E;font-weight:bold;letter-spacing:.5px;padding-right:14px;border-right:1px solid #1f2742;margin-right:8px}
	#tnav-bar .tnav-logo img{height:22px}
	#tnav-bar .tnav-i{font-size:12px;color:#9aa3b8;text-decoration:none;padding:6px 10px;border-radius:6px;cursor:pointer;white-space:nowrap;transition:background .12s,color .12s}
	#tnav-bar .tnav-i:hover{background:#1f2742;color:#fff}
	#tnav-bar .tnav-i.act{background:#C8A96E;color:#0A0E1A;font-weight:600}
	#tnav-bar .tnav-spacer{flex:1}
	.layout-main-section, .page-container > .page-content{padding-top:0 !important}
	`;
	const s = document.createElement('style');
	s.id = 'tnav-css'; s.textContent = css; document.head.appendChild(s);
};

frappe.thanatos._renderBar = function () {
	frappe.thanatos._injectCSS();
	const r = frappe.get_route() || [];
	const head = r[0] || '';
	const second = r[1] || '';
	let active = '';
	frappe.thanatos.SECTIONS.forEach(s => {
		const [h, sec] = s.route;
		if (h === head && (!sec || sec === second)) active = s.key;
	});
	// Skip su pagine specifiche (login, setup-wizard)
	if (['login','setup-wizard','update-password'].includes(head)) {
		$('#tnav-bar').remove(); return;
	}
	let html = `
	<div id="tnav-bar">
	  <span class="tnav-logo">
	    <img src="/assets/thanatos_intel/images/thanatos-icon-192.png" alt="T" onerror="this.style.display='none'">
	    THANATOS
	  </span>`;
	frappe.thanatos.SECTIONS.forEach(s => {
		html += `<a class="tnav-i ${s.key===active?'act':''}" data-route='${JSON.stringify(s.route)}'>${s.label}</a>`;
	});
	html += `<span class="tnav-spacer"></span>
	  <a class="tnav-i" href="/mail" target="_blank">📧 Webmail</a>
	  <a class="tnav-i" href="https://thanatos.agency" target="_blank">🌐 Sito</a>
	</div>`;
	$('#tnav-bar').remove();
	$('header.navbar').after(html);
	$('#tnav-bar .tnav-i[data-route]').on('click', function () {
		try { frappe.set_route.apply(null, JSON.parse($(this).attr('data-route'))); } catch (e) { }
	});
};

// Auto-inject su ogni cambio route
$(document).ready(function () {
	if (!window.frappe || !frappe.router) return;
	frappe.thanatos._renderBar();
	frappe.router.on('change', frappe.thanatos._renderBar);
	// Backup compat: vecchia API
	frappe.thanatos.nav = function () { /* no-op, replaced by sticky bar */ };
});
