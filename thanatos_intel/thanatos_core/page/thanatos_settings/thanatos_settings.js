frappe.pages['thanatos-settings'].on_page_load = function(wrapper){
  const page = frappe.ui.make_app_page({parent: wrapper, title: '⚙️ Impostazioni di sistema', single_column: true});
  const $body = $(wrapper).find('.layout-main-section');

  const GROUPS = [
    {t:'Utenti & accessi', items:[
      {l:'Ruoli & Utenti', d:'Definisci il ruolo di ogni utente', page:'thanatos-users', icon:'👤'},
      {l:'Role Profile', d:'Profili di ruolo predefiniti', list:'Role Profile', icon:'🎭'},
      {l:'Permessi (Role Permission)', d:'Permessi per DocType', route:['permission-manager'], icon:'🔐'},
    ]},
    {t:'Sistema', items:[
      {l:'Impostazioni di sistema', d:'Fuso, lingua, sicurezza, sessioni', single:'System Settings', icon:'🖥️'},
      {l:'Impostazioni sito web', d:'Home, brand, SEO di base', single:'Website Settings', icon:'🌐'},
      {l:'Barra di navigazione', d:'Voci navbar desk', single:'Navbar Settings', icon:'📑'},
      {l:'Stampa', d:'Formati e intestazioni PDF', single:'Print Settings', icon:'🖨️'},
      {l:'Valuta / cambio', d:'EUR + controvalore RON', single:'Currency Exchange Settings', icon:'💱'},
    ]},
    {t:'Comunicazione', items:[
      {l:'Account email', d:'Caselle in entrata/uscita', list:'Email Account', icon:'✉️'},
      {l:'WhatsApp (WABA)', d:'Numero e token Meta', single:'WABA Settings', icon:'💬'},
      {l:'Google', d:'OAuth, Search Console, Maps', single:'Google Settings', icon:'🔗'},
    ]},
    {t:'Fatturazione', items:[
      {l:'Thanatos Billing', d:'Entità fatturante, tariffe', single:'Thanatos Billing Settings', icon:'💶'},
      {l:'Fatturazione elettronica', d:'SDI / e-invoice IT', single:'E Invoice Settings', icon:'🧾'},
      {l:'Abbonamenti', d:'Subscription Stripe', single:'Subscription Settings', icon:'🔁'},
    ]},
    {t:'SEO & contenuti', items:[
      {l:'SEO & Analytics', d:'Traffico, posizioni Google, keyword', page:'seo-analytics', icon:'📊'},
      {l:'Parole chiave SEO', d:'Gestione keyword', list:'SEO Keyword', icon:'🔍'},
      {l:'Articoli (News)', d:'Contenuti pubblici', list:'News Article', icon:'📰'},
    ]},
  ];

  $body.html(`<style>
  .ts-wrap{padding:6px 0 50px}
  .ts-status{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:24px}
  .ts-st{background:var(--card-bg,#fff);border:1px solid var(--border-color,#e3e3e3);border-radius:8px;padding:12px 14px;display:flex;align-items:center;gap:10px}
  .ts-dot{width:9px;height:9px;border-radius:50%;background:#c9302c;flex:0 0 auto}
  .ts-dot.ok{background:#2e9e44}
  .ts-st .nm{font-size:12px;font-weight:600}
  .ts-st .dt{font-size:11px;color:var(--text-muted,#888);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ts-grp{margin-bottom:26px}
  .ts-grp h3{font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted,#888);margin:0 0 12px;font-weight:600}
  .ts-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
  .ts-card{display:flex;gap:12px;align-items:flex-start;background:var(--card-bg,#fff);border:1px solid var(--border-color,#e3e3e3);border-radius:8px;padding:14px;cursor:pointer;transition:.12s}
  .ts-card:hover{border-color:var(--primary,#1f6feb);box-shadow:0 2px 8px rgba(0,0,0,.06)}
  .ts-ic{font-size:22px;line-height:1;flex:0 0 auto}
  .ts-card .l{font-weight:600;font-size:13px}
  .ts-card .d{font-size:11px;color:var(--text-muted,#888);margin-top:3px;line-height:1.4}
  </style>
  <div class="ts-wrap">
    <div class="ts-status" id="ts-status"></div>
    <div id="ts-groups"></div>
  </div>`);

  // launcher
  const $g=$('#ts-groups');
  GROUPS.forEach(grp=>{
    const $blk=$(`<div class="ts-grp"><h3>${grp.t}</h3><div class="ts-cards"></div></div>`);
    const $cards=$blk.find('.ts-cards');
    grp.items.forEach(it=>{
      const $c=$(`<div class="ts-card"><div class="ts-ic">${it.icon||'⚙️'}</div><div><div class="l">${frappe.utils.escape_html(it.l)}</div><div class="d">${frappe.utils.escape_html(it.d||'')}</div></div></div>`);
      $c.on('click', ()=>{
        if(it.single) frappe.set_route('Form', it.single, it.single);
        else if(it.list) frappe.set_route('List', it.list);
        else if(it.page) frappe.set_route(it.page);
        else if(it.route) frappe.set_route(it.route);
      });
      $cards.append($c);
    });
    $g.append($blk);
  });

  // status
  frappe.call({method:'thanatos_intel.admin_settings.system_status'}).then(r=>{
    const s=r.message||{}; const $s=$('#ts-status').empty();
    const card=(nm,o)=>`<div class="ts-st"><span class="ts-dot ${o&&o.ok?'ok':''}"></span><div style="min-width:0"><div class="nm">${nm}</div><div class="dt">${frappe.utils.escape_html((o&&o.detail)||'—')}</div></div></div>`;
    $s.append(card('Google Search Console', s.gsc));
    $s.append(card('Cloudflare Analytics', s.cloudflare));
    $s.append(card('Email in uscita', s.mail));
    $s.append(card('Stripe', s.stripe));
    if(s.users) $s.append(`<div class="ts-st"><span class="ts-dot ok"></span><div><div class="nm">Utenti</div><div class="dt">${s.users.staff} staff · ${s.users.portal} portale</div></div></div>`);
  }).catch(()=>{});
};
