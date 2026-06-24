frappe.pages['seo-analytics'].on_page_load = function(wrapper){
  const page = frappe.ui.make_app_page({parent: wrapper, title: '📊 SEO & Analytics', single_column: true});
  const $body = $(wrapper).find('.layout-main-section');
  let days = 30;

  page.set_secondary_action('Aggiorna da Google', () => {
    frappe.show_alert('Recupero posizioni da Search Console…');
    frappe.call({method:'thanatos_intel.gsc.fetch_rankings', freeze:true, freeze_message:'Google Search Console…'})
      .then(r=>{const m=r.message||{}; m.ok?frappe.show_alert({message:`${m.rows} query aggiornate`,indicator:'green'}):frappe.msgprint(m.reason||'Errore'); load();});
  }, 'refresh');
  page.add_menu_item('Genera keyword dalle news', () => {
    frappe.call({method:'thanatos_intel.analytics.extract_from_news', freeze:true})
      .then(r=>{const m=r.message||{}; frappe.show_alert({message:`${m.created||0} keyword generate`,indicator:'green'}); load();});
  });
  page.add_menu_item('Gestisci parole chiave', () => frappe.set_route('List','SEO Keyword'));

  const $period = $(`<div class="sa-period"></div>`).appendTo(page.custom_actions || page.page_actions);
  [7,30,90].forEach(d=>{
    $(`<button class="btn btn-default btn-sm sa-pb ${d===days?'sa-on':''}" data-d="${d}">${d}g</button>`)
      .appendTo($period).on('click', function(){ days=+$(this).data('d'); $('.sa-pb').removeClass('sa-on'); $(this).addClass('sa-on'); load(); });
  });

  $body.html(`<style>
  .sa-period{display:inline-flex;gap:4px;margin-left:8px}
  .sa-pb.sa-on{background:var(--primary,#1f6feb);color:#fff;border-color:var(--primary,#1f6feb)}
  .sa-wrap{padding:4px 0 40px}
  .sa-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
  .sa-kpi{background:var(--card-bg,#fff);border:1px solid var(--border-color,#e3e3e3);border-radius:8px;padding:16px}
  .sa-kpi .v{font-size:28px;font-weight:600;line-height:1}
  .sa-kpi .v small{font-size:13px;color:var(--text-muted,#888)}
  .sa-kpi .l{color:var(--text-muted,#888);font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-top:6px}
  .sa-box{background:var(--card-bg,#fff);border:1px solid var(--border-color,#e3e3e3);border-radius:8px;padding:18px;margin-bottom:18px}
  .sa-box h3{font-size:14px;margin:0 0 14px;font-weight:600}
  .sa-cols{display:grid;grid-template-columns:1fr 1fr;gap:24px}
  @media(max-width:900px){.sa-cols{grid-template-columns:1fr}}
  .sa-bars{display:flex;align-items:flex-end;gap:3px;height:110px;margin:4px 0 6px}
  .sa-bars .b{flex:1;background:linear-gradient(180deg,var(--primary,#1f6feb),rgba(31,111,235,.25));border-radius:3px 3px 0 0;min-height:2px}
  .sa-rl{list-style:none;margin:0;padding:0;font-size:13px}
  .sa-rl li{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border-color,#eee)}
  .sa-rl li:last-child{border-bottom:none}
  .sa-rl .lab{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .sa-rl .bar{flex:0 0 34%;height:6px;background:var(--bg-color,#f0f0f0);border-radius:3px;overflow:hidden}
  .sa-rl .bar i{display:block;height:100%;background:var(--primary,#1f6feb)}
  .sa-rl .n{flex:0 0 50px;text-align:right;color:var(--text-muted,#888);font-variant-numeric:tabular-nums}
  .sa-rl .hd{color:var(--text-muted,#888);font-size:10px;text-transform:uppercase;letter-spacing:.5px}
  .sa-muted{color:var(--text-muted,#888);font-size:12px;line-height:1.6}
  .sa-badge{font-size:10px;padding:2px 8px;border-radius:10px;border:1px solid var(--border-color,#ccc);color:var(--text-muted,#888);margin-left:6px}
  .sa-badge.ok{color:#2e7d32;border-color:#2e7d32}
  .sa-chips{display:flex;flex-wrap:wrap;gap:6px}
  .sa-chip{background:var(--bg-color,#f4f4f4);border:1px solid var(--border-color,#e3e3e3);border-radius:12px;padding:4px 10px;font-size:12px}
  .sa-empty{color:var(--text-muted,#999);font-size:13px;font-style:italic}
  </style><div class="sa-wrap" id="sa-root"><div class="sa-empty" style="padding:30px">Caricamento…</div></div>`);

  function rows(list, withbar){
    if(!list || !list.length) return '<li class="sa-empty">Nessun dato.</li>';
    const max = Math.max(...list.map(r=>r.count||0)) || 1;
    return list.map(r=>`<li><span class="lab" title="${frappe.utils.escape_html(r.label||'')}">${frappe.utils.escape_html(r.label||'—')}</span>${withbar?`<span class="bar"><i style="width:${(r.count/max*100)}%"></i></span>`:''}<span class="n">${r.count||0}</span></li>`).join('');
  }

  function render(d){
    const tr = d.traffic||{}, kw=d.keywords||{}, ct=d.content||{}, intl=d.internal||{}, gsc=d.gsc||{}, gs=gsc.summary||{};
    const maxd = tr.by_date && tr.by_date.length ? Math.max(...tr.by_date.map(p=>p.count||0)) : 0;
    const bars = (tr.by_date||[]).map(p=>`<div class="b" title="${p.label}: ${p.count}" style="height:${maxd?(p.count/maxd*100):0}%"></div>`).join('');
    const html = `
    <div class="sa-kpis">
      <div class="sa-kpi"><div class="v">${tr.configured?(tr.total||0):'—'}</div><div class="l">Visite (${d.days||days}g)</div></div>
      <div class="sa-kpi"><div class="v">${kw.total||0}</div><div class="l">Keyword attive</div></div>
      <div class="sa-kpi"><div class="v">${ct.articles||0}</div><div class="l">Articoli</div></div>
      <div class="sa-kpi"><div class="v">${gs.queries?gs.avg_position:'—'}</div><div class="l">Pos. media Google</div></div>
    </div>

    <div class="sa-box"><h3>Traffico sito <span class="sa-muted">— Cloudflare Web Analytics</span></h3>
      ${!tr.configured?'<div class="sa-empty">Web Analytics non configurato.</div>':tr.error?'<div class="sa-empty">Dati non disponibili al momento.</div>':`
      <div class="sa-bars">${bars}</div>
      <div class="sa-muted">Totale ${tr.total||0} visite negli ultimi ${d.days||days} giorni.</div>
      <div class="sa-cols" style="margin-top:18px">
        <div><div class="sa-rl hd" style="padding-bottom:6px">Pagine più viste</div><ul class="sa-rl">${rows(tr.top_pages,true)}</ul></div>
        <div>
          <div class="sa-rl hd" style="padding-bottom:6px">Provenienza</div><ul class="sa-rl">${rows(tr.top_referrers,true)}</ul>
          <div class="sa-rl hd" style="padding:14px 0 6px">Paesi</div><ul class="sa-rl">${rows(tr.top_countries,true)}</ul>
        </div>
      </div>`}
    </div>

    <div class="sa-box"><h3>Posizionamento su Google <span class="sa-badge ${gsc.connected?'ok':''}">${gsc.connected?'Connesso':(gsc.configured?'Configurato':'Da connettere')}</span></h3>
      ${gs.queries?`
      <div class="sa-kpis" style="grid-template-columns:repeat(4,1fr)">
        <div class="sa-kpi"><div class="v">${gs.avg_position}</div><div class="l">Posizione media</div></div>
        <div class="sa-kpi"><div class="v">${gs.top10}<small>/${gs.queries}</small></div><div class="l">In top 10</div></div>
        <div class="sa-kpi"><div class="v">${gs.clicks}</div><div class="l">Clic</div></div>
        <div class="sa-kpi"><div class="v">${gs.impressions}</div><div class="l">Impression</div></div>
      </div>
      <div class="sa-muted" style="margin:2px 0 12px">Parole chiave trovate su Google al ${gs.date} (posizione = ranking medio, più basso è meglio).</div>
      <ul class="sa-rl"><li class="hd"><span class="lab">Query</span><span class="n">Pos</span><span class="n">Imp</span><span class="n">Clic</span></li>
        ${(gsc.queries||[]).map(r=>`<li><span class="lab" title="${frappe.utils.escape_html(r.query||'')}">${frappe.utils.escape_html(r.query||'')}</span><span class="n">${r.position}</span><span class="n">${r.impressions}</span><span class="n">${r.clicks}</span></li>`).join('')}
      </ul>
      <div class="sa-muted" style="margin-top:8px">Proprietà: <code>${gsc.property||''}</code></div>`
      :`<div class="sa-muted">Qui appaiono le parole chiave per cui il sito viene trovato su Google, con posizione media, impression e click.<br>
      ${gsc.configured?'Service account presente — premi <b>Aggiorna da Google</b> per importare i dati.':'Manca il service account GSC con accesso alla proprietà.'}</div>`}
    </div>

    <div class="sa-cols">
      <div class="sa-box" style="margin-bottom:0"><h3>Contenuti pubblicati</h3>
        <div class="sa-kpis" style="grid-template-columns:1fr 1fr;margin-bottom:0">
          <div class="sa-kpi"><div class="v">${ct.articles||0}</div><div class="l">Articoli</div></div>
          <div class="sa-kpi"><div class="v">${ct.categories||0}</div><div class="l">Categorie</div></div>
        </div>
        <div class="sa-muted" style="margin-top:12px">Più articoli ottimizzati = più pagine indicizzate = più query intercettate.</div>
      </div>
      <div class="sa-box" style="margin-bottom:0"><h3>Ricerche interne nel portale</h3>
        <ul class="sa-rl">${rows((intl.top_searches||[]),true)}</ul>
        <div class="sa-muted" style="margin-top:8px">Cosa cercano gli utenti: spunti per nuovi articoli e keyword. ${intl.page_views||0} page view totali.</div>
      </div>
    </div>

    <div class="sa-box"><h3>Parole chiave attive (${kw.total||0})</h3>
      <div class="sa-chips">${(kw.top||[]).map(k=>`<span class="sa-chip">${frappe.utils.escape_html(k.keyword)} <span class="sa-muted">${(k.origin||'').toLowerCase()}</span></span>`).join('') || '<span class="sa-empty">Nessuna keyword.</span>'}</div>
      <div class="sa-muted" style="margin-top:10px">Entrano nei <code>&lt;meta keywords&gt;</code> delle pagine pubbliche. Usa il menu per gestirle o generarle dalle news.</div>
    </div>`;
    $('#sa-root').html(html);
  }

  function load(){
    $('#sa-root').html('<div class="sa-empty" style="padding:30px">Caricamento…</div>');
    frappe.call({method:'thanatos_intel.seo_dashboard.get_dashboard', args:{days:days}})
      .then(r=>render(r.message||{}))
      .catch(()=>$('#sa-root').html('<div class="sa-empty" style="padding:30px">Errore nel caricamento.</div>'));
  }
  load();
};
