
// Thanatos Top Nav v3 — sticky bar SU OGNI pagina desk, multi-fallback
(function(){
  if (window.__tnav_loaded) return;
  window.__tnav_loaded = true;

  const SECTIONS = [
    {key:'cockpit', label:'🏠 Cockpit', route:['thanatos-cockpit']},
    {key:'comunicazioni', label:'💬 Comunicazioni', route:['comunicazioni']},
    {key:'casi', label:'📂 Casi', route:['List','Investigation Case']},
    {key:'ddd', label:'🪪 DD', route:['List','Diplomatic Eligibility Case']},
    {key:'mandati', label:'📜 Mandati', route:['List','Agency Mandate']},
    {key:'firme', label:'🖊 Firme', route:['List','Signature Request']},
    {key:'billing', label:'💶 Billing', route:['List','Diplomatic Proforma']},
    {key:'rubrica', label:'👥 Rubrica', route:['List','Customer']},
    {key:'intelligence', label:'🔍 Intelligence', route:['List','OSINT Job']},
    {key:'antifrode', label:'🛡 Antifrode', route:['List','Blacklist Entry']},
    {key:'compliance', label:'📋 Compliance', route:['List','Risk Score']},
    {key:'seo', label:'🔍 SEO', route:['List','SEO Keyword']},
    {key:'architetto', label:'🤖 AI', route:['thanatos-ai-architect']},
  ];

  function injectCSS(){
    if (document.getElementById('tnav-css')) return;
    const css = document.createElement('style');
    css.id = 'tnav-css';
    css.textContent = `
      #tnav-bar{position:fixed;top:0;left:0;right:0;z-index:1001;background:#0a0e1a;color:#fff;padding:8px 16px;display:flex;gap:4px;align-items:center;flex-wrap:nowrap;overflow-x:auto;height:46px;box-sizing:border-box;border-bottom:2px solid #C8A96E;font-family:inherit;font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.15)}
      #tnav-bar::-webkit-scrollbar{height:0}
      #tnav-bar .tnav-logo{display:flex;align-items:center;gap:8px;color:#C8A96E;font-weight:bold;letter-spacing:.5px;padding-right:14px;border-right:1px solid #1f2742;margin-right:8px;font-size:13px}
      #tnav-bar .tnav-logo img{height:22px}
      #tnav-bar .tnav-i{font-size:12px;color:#9aa3b8;text-decoration:none;padding:6px 10px;border-radius:6px;cursor:pointer;white-space:nowrap;transition:background .12s,color .12s}
      #tnav-bar .tnav-i:hover{background:#1f2742;color:#fff;text-decoration:none}
      #tnav-bar .tnav-i.act{background:#C8A96E;color:#0A0E1A;font-weight:600}
      #tnav-bar .tnav-spacer{flex:1}
      body{padding-top:46px !important}
      /* Nascondi la vecchia .tnav dentro le Page (cockpit ne aveva una) */
      .layout-main-section .tnav, .page-body .tnav{display:none !important}
      /* Toolbar Frappe SEMPRE sotto la top-nav (liste E schede): evita che la barra
         azioni finisca coperta/tagliata dalla top-nav fissa. */
      .page-head{top:46px !important}
      /* La barra azioni non deve ritagliare bottoni/menu */
      .page-actions{overflow:visible !important;max-width:none !important;flex-wrap:wrap !important}
    `;
    document.head.appendChild(css);
  }

  function build(){
    injectCSS();
    let active = '';
    try {
      const r = (window.frappe && frappe.get_route && frappe.get_route()) || [];
      const head = r[0] || '', second = r[1] || '';
      SECTIONS.forEach(s => {
        const [h, sec] = s.route;
        if (h === head && (!sec || sec === second)) active = s.key;
      });
      if (['login','setup-wizard','update-password'].includes(head)){
        const e = document.getElementById('tnav-bar'); if (e) e.remove();
        return;
      }
    } catch(e){}

    const old = document.getElementById('tnav-bar');
    if (old) old.remove();

    const bar = document.createElement('div');
    bar.id = 'tnav-bar';
    bar.innerHTML = `
      <span class="tnav-logo">
        <img src="/assets/thanatos_intel/images/thanatos-icon-192.png" onerror="this.style.display='none'">
        THANATOS
      </span>
      ${SECTIONS.map(s => `<a class="tnav-i ${s.key===active?'act':''}" data-route='${JSON.stringify(s.route)}'>${s.label}</a>`).join('')}
      <span class="tnav-spacer"></span>
      <a class="tnav-i" href="/mail" target="_blank">📧 Webmail</a>
      <a class="tnav-i" href="https://thanatos.agency" target="_blank">🌐 Sito</a>
    `;
    bar.addEventListener('click', e => {
      const a = e.target.closest('.tnav-i[data-route]');
      if (!a) return;
      e.preventDefault();
      try { frappe.set_route.apply(null, JSON.parse(a.getAttribute('data-route'))); } catch(_){}
    });

    // Insert: prova diversi target, fallback body
    const targets = ['header.navbar','.navbar.navbar-expand','nav.navbar','#navbar-breadcrumbs'];
    let inserted = false;
    for (const sel of targets){
      const el = document.querySelector(sel);
      if (el){
        el.parentNode.insertBefore(bar, el.nextSibling);
        inserted = true; break;
      }
    }
    if (!inserted){
      // fallback: prepend al primo .container-fluid o body
      const container = document.querySelector('.main-section, .container, #body, body');
      if (container) container.insertBefore(bar, container.firstChild);
    }
  }

  

  // Custom Sidebar: aggiunge sezioni Thanatos alla sidebar del desk
  const SIDEBAR_GROUPS = [
    {label:'🎯 Operativo', items:[
      {l:'🏠 Home', r:['Workspaces','Thanatos Intel']},
      {l:'💬 Comunicazioni', r:['comunicazioni']},
      {l:'🏠 Cockpit', r:['thanatos-cockpit']},
    ]},
    {label:'👤 Anagrafiche', items:[
      {l:'Customer', r:['List','Customer']},
      {l:'Contact', r:['List','Contact']},
      {l:'Applicant Profile', r:['List','Applicant Profile']},
      {l:'Intel Lead', r:['List','Intel Lead']},
    ]},
    {label:'📋 Pratiche', items:[
      {l:'Investigation Case', r:['List','Investigation Case']},
      {l:'DD / DDD Case', r:['List','Diplomatic Eligibility Case']},
      {l:'KYB Check', r:['List','KYB Check']},
      {l:'KYC Check', r:['List','KYC Check']},
      {l:'OSINT Job', r:['List','OSINT Job']},
    ]},
    {label:'📜 Mandati & Billing', items:[
      {l:'Agency Mandate', r:['List','Agency Mandate']},
      {l:'Diplomatic Proforma', r:['List','Diplomatic Proforma']},
      {l:'Sales Invoice', r:['List','Sales Invoice']},
      {l:'Quotation', r:['List','Quotation']},
    ]},
    {label:'🖊 Firme', items:[
      {l:'Signature Request', r:['List','Signature Request']},
      {l:'Signature Template', r:['List','Signature Template']},
      {l:'Mandate Clause', r:['List','Mandate Clause']},
    ]},
    {label:'🛡 Compliance', items:[
      {l:'Risk Score', r:['List','Risk Score']},
      {l:'Risk Indicator', r:['List','Risk Indicator']},
      {l:'Blacklist Entry', r:['List','Blacklist Entry']},
      {l:'Chain Of Custody', r:['List','Chain Of Custody Event']},
    ]},
    {label:'📁 Evidence', items:[
      {l:'Investigation Entity', r:['List','Investigation Entity']},
      {l:'Investigation Evidence', r:['List','Investigation Evidence']},
      {l:'Investigation Report', r:['List','Investigation Report']},
    ]},
    {label:'🔍 SEO & Analytics', items:[
      {l:'SEO Keyword', r:['List','SEO Keyword']},
      {l:'Email Template', r:['List','Email Template']},
      {l:'Web Page View', r:['List','Web Page View']},
    ]},
    {label:'🛠 Setup', items:[
      {l:'Setup', r:['Workspaces','Thanatos Setup']},
      {l:'Insight', r:['Workspaces','Thanatos Insight']},
      {l:'Email Account', r:['List','Email Account']},
      {l:'Billing Entity', r:['List','Billing Entity']},
    ]},
  ];

  function buildSidebar(){
    const targets = ['.desk-sidebar', '.layout-side-section', '#sidebar', '.sidebar-padding'];
    let host = null;
    for (const s of targets){ host = document.querySelector(s); if (host) break; }
    if (!host) return;
    if (host.querySelector('.tnav-sidebar')) return; // già fatto

    const wrap = document.createElement('div');
    wrap.className = 'tnav-sidebar';
    wrap.innerHTML = SIDEBAR_GROUPS.map(g => `
      <div class="tnav-sb-grp" data-grp="${g.label}">
        <div class="tnav-sb-h">${g.label}</div>
        <div class="tnav-sb-items">
          ${g.items.map(i => `<a class="tnav-sb-i" data-route='${JSON.stringify(i.r)}'>${i.l}</a>`).join('')}
        </div>
      </div>`).join('');

    // CSS
    if (!document.getElementById('tnav-sb-css')){
      const c = document.createElement('style'); c.id = 'tnav-sb-css';
      c.textContent = `
        .tnav-sidebar{padding:12px 8px;font-size:12px;border-top:1px solid #e3e3e3;margin-top:12px}
        .tnav-sb-h{color:#666;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px;padding:8px 6px 4px;margin-top:6px}
        .tnav-sb-i{display:block;padding:5px 12px;color:#333;text-decoration:none;border-radius:4px;font-size:12px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .tnav-sb-i:hover{background:#f0f4ff;color:#1f6feb;text-decoration:none}
      `;
      document.head.appendChild(c);
    }
    host.appendChild(wrap);
    wrap.addEventListener('click', e => {
      const a = e.target.closest('.tnav-sb-i[data-route]');
      if (!a) return;
      try { frappe.set_route.apply(null, JSON.parse(a.getAttribute('data-route'))); } catch(_){}
    });
  }


  function setup(){
    build(); buildSidebar();
    // Re-render ad ogni navigazione
    if (window.frappe && frappe.router && frappe.router.on){
      try { frappe.router.on('change', build); } catch(_){}
    }
    // Hash change fallback
    window.addEventListener('hashchange', build);
    // Mutation observer per safety net (se DOM viene riscritto)
    // Heartbeat aggressivo: ogni 800ms verifica presenza barra
    setInterval(() => {
      if (!document.getElementById('tnav-bar')) build(); buildSidebar();
    }, 800);
    // MutationObserver come safety net su tutto subtree
    let lastRender = Date.now();
    const obs = new MutationObserver(() => {
      if (!document.getElementById('tnav-bar') && Date.now() - lastRender > 500){
        lastRender = Date.now();
        build();
      }
    });
    obs.observe(document.body, {childList:true, subtree:true});
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }

  // Expose legacy API (no-op safe)
  if (window.frappe){
    frappe.provide && frappe.provide('frappe.thanatos');
    frappe.thanatos = frappe.thanatos || {};
    frappe.thanatos.nav = function(){};
    frappe.thanatos.SECTIONS = SECTIONS;
  }
})();
