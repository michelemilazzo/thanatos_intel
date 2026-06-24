frappe.pages['thanatos-users'].on_page_load = function(wrapper){
  const page = frappe.ui.make_app_page({parent: wrapper, title: '👤 Ruoli & Utenti', single_column: true});
  const $body = $(wrapper).find('.layout-main-section');
  let DATA = {users:[], staff_roles:[], portal_roles:[]};

  const $search = page.add_field({fieldtype:'Data', fieldname:'q', label:'Cerca utente', placeholder:'nome o email…'});
  $search.$input.on('keyup', frappe.utils.debounce(()=>load($search.get_value()), 300));
  page.set_primary_action('Nuovo utente', ()=>frappe.new_doc('User'), 'add');

  $body.html(`<style>
  .tu-wrap{padding:6px 0 50px}
  .tu-intro{color:var(--text-muted,#888);font-size:13px;margin-bottom:16px;line-height:1.6}
  .tu-row{display:flex;align-items:center;gap:14px;padding:12px 14px;border:1px solid var(--border-color,#e3e3e3);border-radius:8px;margin-bottom:8px;background:var(--card-bg,#fff)}
  .tu-row.off{opacity:.5}
  .tu-id{flex:0 0 240px;min-width:0}
  .tu-id .nm{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .tu-id .em{font-size:11px;color:var(--text-muted,#888);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .tu-type{flex:0 0 92px;font-size:10px;text-transform:uppercase;letter-spacing:.5px;text-align:center;padding:3px 6px;border-radius:10px;border:1px solid var(--border-color,#ddd);color:var(--text-muted,#888)}
  .tu-type.staff{color:#1f6feb;border-color:#1f6feb}
  .tu-type.client{color:#8a6d1f;border-color:#caa64e}
  .tu-roles{flex:1;display:flex;flex-wrap:wrap;gap:5px}
  .tu-tag{font-size:11px;background:var(--bg-color,#f2f2f2);border:1px solid var(--border-color,#e0e0e0);border-radius:11px;padding:2px 9px}
  .tu-tag.none{color:var(--text-muted,#aaa);font-style:italic;background:transparent;border:none}
  .tu-edit{flex:0 0 auto}
  .tu-pop{padding:4px 2px;min-width:300px}
  .tu-pop h6{margin:8px 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted,#888)}
  .tu-pop label{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13px;cursor:pointer}
  .tu-empty{color:var(--text-muted,#999);font-style:italic;padding:24px;text-align:center}
  </style>
  <div class="tu-wrap">
    <div class="tu-intro">Definisci il ruolo di ogni utente. <b>Staff</b> = accesso al desk Thanatos Intel (System User). <b>Cliente/Affiliato</b> = solo portale. Modifica i ruoli con il pulsante a destra di ogni riga; vengono toccati solo i ruoli Thanatos/portale, gli altri restano invariati.</div>
    <div id="tu-list"><div class="tu-empty">Caricamento…</div></div>
  </div>`);

  function tag(label){ return `<span class="tu-tag">${frappe.utils.escape_html(label)}</span>`; }
  function roleLabel(r){
    const all=[...DATA.staff_roles,...DATA.portal_roles];
    const f=all.find(x=>x[0]===r); return f?f[1]:r;
  }

  function render(){
    const $l=$('#tu-list').empty();
    if(!DATA.users.length){ $l.html('<div class="tu-empty">Nessun utente.</div>'); return; }
    DATA.users.forEach(u=>{
      const tags = u.managed_roles.length ? u.managed_roles.map(r=>tag(roleLabel(r))).join('') : '<span class="tu-tag none">nessun ruolo Thanatos</span>';
      const typeCls = u.is_staff?'staff':(u.managed_roles.some(r=>DATA.portal_roles.find(p=>p[0]===r))?'client':'');
      const $row=$(`<div class="tu-row ${u.enabled?'':'off'}">
        <div class="tu-id"><div class="nm">${frappe.utils.escape_html(u.full_name||u.name)}</div><div class="em">${frappe.utils.escape_html(u.name)}</div></div>
        <div class="tu-type ${typeCls}">${u.is_staff?'Staff':'Portale'}</div>
        <div class="tu-roles">${tags}</div>
        <div class="tu-edit"></div>
      </div>`);
      const $btn=$(`<button class="btn btn-default btn-sm">Modifica ruoli</button>`).appendTo($row.find('.tu-edit'));
      $btn.on('click', ()=>openEditor(u, $btn));
      // apri scheda utente cliccando sull'identità
      $row.find('.tu-id').css('cursor','pointer').on('click', ()=>frappe.set_route('Form','User',u.name));
      $l.append($row);
    });
  }

  function openEditor(u, $btn){
    if(u.name==='Administrator'){ frappe.msgprint('Administrator non è modificabile da qui.'); return; }
    const cur=new Set(u.managed_roles);
    const grp=(title,list)=>`<h6>${title}</h6>`+list.map(([r,lab])=>
      `<label><input type="checkbox" data-r="${r}" ${cur.has(r)?'checked':''}> ${frappe.utils.escape_html(lab)}</label>`).join('');
    const $c=$(`<div class="tu-pop">${grp('Staff (desk)',DATA.staff_roles)}${grp('Portale',DATA.portal_roles)}</div>`);
    const d=new frappe.ui.Dialog({
      title:`Ruoli — ${u.full_name||u.name}`, size:'small',
      primary_action_label:'Salva',
      primary_action:()=>{
        const roles=$c.find('input:checked').map((i,el)=>$(el).data('r')).get();
        frappe.call({method:'thanatos_intel.admin_users.set_user_roles', args:{user:u.name, roles:JSON.stringify(roles)}, freeze:true})
          .then(r=>{ d.hide(); const m=r.message||{}; frappe.show_alert({message:`Ruoli aggiornati (${m.user_type})`,indicator:'green'}); load($search.get_value()); });
      }
    });
    d.$body.append($c);
    d.show();
  }

  function load(q){
    $('#tu-list').html('<div class="tu-empty">Caricamento…</div>');
    frappe.call({method:'thanatos_intel.admin_users.list_users', args:{search:q||''}})
      .then(r=>{ DATA=r.message||DATA; render(); })
      .catch(()=>$('#tu-list').html('<div class="tu-empty">Errore o permessi insufficienti.</div>'));
  }
  load();
};
