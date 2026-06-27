// Thanatos Shell v4 — solo pulsante "Cockpit" nel sidebar sinistro.
// Nessuna barra fissa in cima: layout Frappe nativo (navbar al suo posto, niente overlap).
(function(){
  if (window.__tnav_loaded) return;
  window.__tnav_loaded = true;

  function injectCSS(){
    if (document.getElementById('tnav-css')) return;
    const c = document.createElement('style'); c.id = 'tnav-css';
    c.textContent = `
      .tnav-cockpit-btn{display:flex;align-items:center;justify-content:center;gap:8px;
        margin:10px 10px 6px;padding:9px 12px;background:#0A0E1A;color:#C8A96E;
        border:1px solid #C8A96E;border-radius:8px;font-weight:600;font-size:13px;
        letter-spacing:.3px;cursor:pointer;text-decoration:none;white-space:nowrap;
        transition:background .12s,color .12s}
      .tnav-cockpit-btn:hover{background:#C8A96E;color:#0A0E1A;text-decoration:none}
      .tnav-cockpit-btn img{height:18px}
    `;
    document.head.appendChild(c);
  }

  function cleanupLegacy(){
    // rimuovi residui della vecchia top-bar / gruppi sidebar
    const bar = document.getElementById('tnav-bar'); if (bar) bar.remove();
    document.querySelectorAll('.tnav-sidebar').forEach(e => e.remove());
    document.body.style.removeProperty('padding-top');
  }

  function ensureButton(){
    cleanupLegacy();
    injectCSS();
    if (document.querySelector('.tnav-cockpit-btn')) return; // già presente
    const targets = ['.sidebar-items', '.body-sidebar-top', '.body-sidebar',
                     '.standard-items-sections', '.desk-sidebar', '#sidebar'];
    let host = null;
    for (const s of targets){ host = document.querySelector(s); if (host) break; }
    if (!host) return;

    const btn = document.createElement('a');
    btn.className = 'tnav-cockpit-btn';
    btn.title = 'Vai al Cockpit Thanatos';
    btn.innerHTML = `<img src="/assets/thanatos_intel/images/thanatos-icon-192.png" onerror="this.style.display='none'"> THANATOS · Cockpit`;
    btn.addEventListener('click', e => {
      e.preventDefault();
      try { frappe.set_route('thanatos-cockpit'); } catch(_){}
    });
    host.insertBefore(btn, host.firstChild);
  }

  function setup(){
    ensureButton();
    if (window.frappe && frappe.router && frappe.router.on){
      try { frappe.router.on('change', ensureButton); } catch(_){}
    }
    window.addEventListener('hashchange', ensureButton);
    setInterval(ensureButton, 1200);
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', setup);
  } else { setup(); }
})();
