frappe.pages['thanatos-changelog'].on_page_load = function(wrapper){
  const page = frappe.ui.make_app_page({parent: wrapper, title: '📋 Aggiornamenti', single_column: true});
  const $body = $(wrapper).find('.layout-main-section');
  let DATA = {updates:[], areas:[]};
  let filter = null;

  const AREA_ICON = {SEO:'📈', Desk:'🖥️', Portale:'🌐', Profilo:'👤', Fatturazione:'💶', Sicurezza:'🔐', Comunicazione:'✉️', Sistema:'⚙️', Altro:'•'};
  const MONTHS = ['gen','feb','mar','apr','mag','giu','lug','ago','set','ott','nov','dic'];

  $body.html(`<style>
  .cl-wrap{padding:6px 0 60px;max-width:820px}
  .cl-intro{color:var(--text-muted,#888);font-size:13px;margin-bottom:18px;line-height:1.6}
  .cl-filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:22px}
  .cl-fb{font-size:12px;border:1px solid var(--border-color,#ddd);background:var(--card-bg,#fff);border-radius:999px;padding:5px 13px;cursor:pointer;color:var(--text-muted,#666)}
  .cl-fb.on{background:var(--primary,#1f6feb);color:#fff;border-color:var(--primary,#1f6feb)}
  .cl-day{margin-bottom:26px}
  .cl-date{font-size:12px;font-weight:600;color:var(--text-muted,#888);text-transform:uppercase;letter-spacing:.5px;margin:0 0 12px;padding-bottom:6px;border-bottom:1px solid var(--border-color,#eee)}
  .cl-item{display:flex;gap:14px;padding:12px 0}
  .cl-ic{flex:0 0 34px;height:34px;border-radius:8px;background:var(--bg-color,#f3f5f9);display:flex;align-items:center;justify-content:center;font-size:16px}
  .cl-body{flex:1;min-width:0}
  .cl-t{font-weight:600;font-size:14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .cl-star{color:#e0a93b}
  .cl-d{font-size:13px;color:var(--text-muted,#777);margin-top:3px;line-height:1.55}
  .cl-meta{display:flex;gap:6px;margin-top:6px}
  .cl-badge{font-size:10px;text-transform:uppercase;letter-spacing:.4px;padding:2px 8px;border-radius:10px;border:1px solid var(--border-color,#e0e0e0);color:var(--text-muted,#888)}
  .cl-badge.aud-Cliente{color:#8a6d1f;border-color:#caa64e}
  .cl-badge.aud-Staff,.cl-badge.aud-Interno{color:#1f6feb;border-color:#9cc0fb}
  .cl-empty{color:var(--text-muted,#999);font-style:italic;padding:30px;text-align:center}
  </style>
  <div class="cl-wrap">
    <div class="cl-intro">Tutte le novità rilasciate su Thanatos, generate automaticamente dalla cronologia di sviluppo. Filtra per area.</div>
    <div class="cl-filters" id="cl-filters"></div>
    <div id="cl-list"><div class="cl-empty">Caricamento…</div></div>
  </div>`);

  function fmtDate(iso){
    const p=(iso||'').split('-'); if(p.length<3) return iso;
    return `${parseInt(p[2],10)} ${MONTHS[parseInt(p[1],10)-1]||''} ${p[0]}`;
  }

  function renderFilters(){
    const $f=$('#cl-filters').empty();
    const mk=(label,val)=>$(`<span class="cl-fb ${filter===val?'on':''}">${label}</span>`).on('click',()=>{filter=val;render();});
    $f.append(mk('Tutte', null));
    DATA.areas.forEach(a=>$f.append(mk(a, a)));
  }

  function render(){
    renderFilters();
    const items = DATA.updates.filter(u=>!filter || u.area===filter);
    const $l=$('#cl-list').empty();
    if(!items.length){ $l.html('<div class="cl-empty">Nessun aggiornamento.</div>'); return; }
    let curDate=null, $day=null;
    items.forEach(u=>{
      if(u.date!==curDate){
        curDate=u.date;
        $day=$(`<div class="cl-day"><div class="cl-date">${fmtDate(u.date)}</div></div>`);
        $l.append($day);
      }
      const aud=u.audience||'';
      $day.append(`<div class="cl-item">
        <div class="cl-ic">${AREA_ICON[u.area]||'•'}</div>
        <div class="cl-body">
          <div class="cl-t">${u.highlight?'<span class="cl-star">★</span>':''}${frappe.utils.escape_html(u.title)}</div>
          <div class="cl-d">${frappe.utils.escape_html(u.desc||'')}</div>
          <div class="cl-meta"><span class="cl-badge">${frappe.utils.escape_html(u.area)}</span>${aud?`<span class="cl-badge aud-${aud}">${aud}</span>`:''}${u.hash?`<span class="cl-badge" style="font-family:monospace;opacity:.6">${u.hash}</span>`:''}</div>
        </div>
      </div>`);
    });
  }

  frappe.call({method:'thanatos_intel.changelog_data.get_updates'})
    .then(r=>{ DATA=r.message||DATA; page.set_indicator(`${DATA.count} aggiornamenti`, 'blue'); render(); })
    .catch(()=>$('#cl-list').html('<div class="cl-empty">Errore nel caricamento.</div>'));
};
