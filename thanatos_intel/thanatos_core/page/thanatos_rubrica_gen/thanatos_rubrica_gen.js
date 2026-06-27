frappe.pages['thanatos-rubrica-gen'].on_page_load = function(wrapper){
  const page = frappe.ui.make_app_page({parent: wrapper, title: '👥 Rubrica generale', single_column: true});
  const $b = $(wrapper).find('.layout-main-section');
  let STAFF = [];
  const $s = page.add_field({fieldtype:'Data', fieldname:'q', label:'Cerca', placeholder:'nome, email, azienda…'});
  $s.$input.on('keyup', frappe.utils.debounce(()=>load($s.get_value()), 280));

  $b.html(`<style>
  .rg-wrap{padding:6px 0 50px}
  .rg-intro{color:var(--text-muted,#888);font-size:13px;margin-bottom:14px}
  table.rg{width:100%;font-size:13px;border-collapse:collapse}
  table.rg th{text-align:left;color:var(--text-muted,#888);font-weight:600;border-bottom:1px solid var(--border-color,#e3e3e3);padding:6px 8px}
  table.rg td{border-bottom:1px solid var(--border-color,#eee);padding:6px 8px;vertical-align:middle}
  table.rg tr:hover{background:var(--bg-color,#f7f8fa)}
  .rg-nm{font-weight:600;cursor:pointer}
  .rg-sub{font-size:11px;color:var(--text-muted,#888)}
  .rg-sel{border:1px solid var(--border-color,#ddd);border-radius:6px;padding:3px 6px;font-size:12px;background:var(--control-bg,#fff);max-width:150px}
  .rg-empty{color:var(--text-muted,#999);font-style:italic;padding:24px;text-align:center}
  .rg-mgr{font-size:12px}
  </style>
  <div class="rg-wrap">
    <div class="rg-intro">Tutti i contatti, con <b>assegnazione</b> a un operatore, flag <b>condiviso</b> col team e il <b>gestore</b> della pratica collegata.</div>
    <table class="rg"><thead><tr><th>Contatto</th><th>Telefono</th><th>Azienda</th><th>Assegnato a</th><th>Cond.</th><th>Gestore pratica</th></tr></thead>
    <tbody id="rg-body"><tr><td colspan="6" class="rg-empty">Caricamento…</td></tr></tbody></table>
  </div>`);

  function staffOptions(sel){
    let o='<option value="">—</option>';
    STAFF.forEach(u=>{ o+='<option value="'+u.name+'"'+(u.name===sel?' selected':'')+'>'+frappe.utils.escape_html(u.full_name||u.name)+'</option>'; });
    return o;
  }
  function render(rows){
    const $t=$('#rg-body').empty();
    if(!rows.length){ $t.html('<tr><td colspan="6" class="rg-empty">Nessun contatto.</td></tr>'); return; }
    rows.forEach(c=>{
      const $tr=$('<tr></tr>');
      $tr.append('<td><div class="rg-nm">'+frappe.utils.escape_html(c.display)+'</div><div class="rg-sub">'+frappe.utils.escape_html(c.email||'')+'</div></td>');
      $tr.append('<td>'+frappe.utils.escape_html(c.phone||'')+'</td>');
      $tr.append('<td>'+frappe.utils.escape_html(c.company||'')+'</td>');
      const $sel=$('<select class="rg-sel">'+staffOptions(c.assigned_to)+'</select>');
      $sel.on('change',function(){ save(c.name,{assigned_to:this.value}); });
      const $td1=$('<td></td>').append($sel); $tr.append($td1);
      const $chk=$('<input type="checkbox" '+(c.is_shared?'checked':'')+'>');
      $chk.on('change',function(){ save(c.name,{is_shared:this.checked?1:0}); });
      $tr.append($('<td></td>').append($chk));
      $tr.append('<td class="rg-mgr">'+(c.manager?(frappe.utils.escape_html(c.manager)+(c.case?(' <span class="rg-sub">('+c.case+')</span>'):'')):'<span class="rg-sub">—</span>')+'</td>');
      $tr.find('.rg-nm').on('click',()=>frappe.set_route('Form','Contact',c.name));
      $t.append($tr);
    });
  }
  function save(contact,args){
    frappe.call({method:'thanatos_intel.api.rubrica_general.set_assignment',args:Object.assign({contact:contact},args)})
      .then(()=>frappe.show_alert({message:'Salvato',indicator:'green'}));
  }
  function load(q){
    $('#rg-body').html('<tr><td colspan="6" class="rg-empty">Caricamento…</td></tr>');
    frappe.call({method:'thanatos_intel.api.rubrica_general.list_contacts',args:{search:q||''}})
      .then(r=>render(r.message||[]));
  }
  frappe.call({method:'thanatos_intel.api.rubrica_general.staff_users'}).then(r=>{ STAFF=r.message||[]; load(''); });
};
