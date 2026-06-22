
// Thanatos Top Nav v3 — sticky bar SU OGNI pagina desk, multi-fallback
(function(){
  if (window.__tnav_loaded) return;
  window.__tnav_loaded = true;

  const SECTIONS = [
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
    {key:'seo', label:'🔍 SEO', route:['List','SEO Keyword']},
    {key:'architetto', label:'🤖 AI', route:['thanatos-ai-architect']},
  ];

  function injectCSS(){
    if (document.getElementById('tnav-css')) return;
    const css = document.createElement('style');
    css.id = 'tnav-css';
    css.textContent = `
      #tnav-bar{position:sticky;top:0;z-index:99;background:#0a0e1a;color:#fff;padding:8px 16px;display:flex;gap:4px;align-items:center;flex-wrap:wrap;border-bottom:2px solid #C8A96E;font-family:inherit;font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.15)}
      #tnav-bar .tnav-logo{display:flex;align-items:center;gap:8px;color:#C8A96E;font-weight:bold;letter-spacing:.5px;padding-right:14px;border-right:1px solid #1f2742;margin-right:8px;font-size:13px}
      #tnav-bar .tnav-logo img{height:22px}
      #tnav-bar .tnav-i{font-size:12px;color:#9aa3b8;text-decoration:none;padding:6px 10px;border-radius:6px;cursor:pointer;white-space:nowrap;transition:background .12s,color .12s}
      #tnav-bar .tnav-i:hover{background:#1f2742;color:#fff;text-decoration:none}
      #tnav-bar .tnav-i.act{background:#C8A96E;color:#0A0E1A;font-weight:600}
      #tnav-bar .tnav-spacer{flex:1}
      /* Nascondi la vecchia .tnav dentro le Page (cockpit ne aveva una) */
      .layout-main-section .tnav, .page-body .tnav{display:none !important}
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

  function setup(){
    build();
    // Re-render ad ogni navigazione
    if (window.frappe && frappe.router && frappe.router.on){
      try { frappe.router.on('change', build); } catch(_){}
    }
    // Hash change fallback
    window.addEventListener('hashchange', build);
    // Mutation observer per safety net (se DOM viene riscritto)
    let lastRender = Date.now();
    const obs = new MutationObserver(() => {
      if (!document.getElementById('tnav-bar') && Date.now() - lastRender > 1000){
        lastRender = Date.now();
        build();
      }
    });
    obs.observe(document.body, {childList:true, subtree:false});
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
