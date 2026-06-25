frappe.pages['thanatos-mail-prov'].on_page_load = function(wrapper){
  const page = frappe.ui.make_app_page({parent: wrapper, title: '📬 Provisioning Webmail', single_column: true});
  const $b = $(wrapper).find('.layout-main-section');

  $b.html(`<style>
  .mp-wrap{padding:6px 0 50px;max-width:760px}
  .mp-intro{color:var(--text-muted,#888);font-size:13px;margin-bottom:18px;line-height:1.6}
  .mp-box{background:var(--card-bg,#fff);border:1px solid var(--border-color,#e3e3e3);border-radius:8px;padding:18px;margin-bottom:18px}
  .mp-row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
  .mp-f{flex:1;min-width:200px}
  .mp-f label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted,#888);margin-bottom:5px}
  .mp-f input{width:100%;padding:8px 10px;border:1px solid var(--border-color,#ddd);border-radius:6px;background:var(--control-bg,#fff)}
  .mp-plan{margin-top:14px;font-size:13px;background:var(--bg-color,#f7f8fa);border:1px solid var(--border-color,#eee);border-radius:6px;padding:12px;display:none}
  .mp-plan .ok{color:#2e7d32}.mp-plan .warn{color:#b9770e}
  .mp-msg{font-size:13px;margin-top:10px;min-height:16px}
  .mp-tag{display:inline-block;font-size:11px;background:var(--bg-color,#f0f0f0);border:1px solid var(--border-color,#e0e0e0);border-radius:11px;padding:3px 10px;margin:3px}
  .mp-list{display:flex;flex-wrap:wrap}
  .mp-empty{color:var(--text-muted,#999);font-style:italic;font-size:13px}
  </style>
  <div class="mp-wrap">
    <div class="mp-intro">Crea la casella <b>@thanatos.agency</b> di un utente e abilita la webmail generando una <b>app-password dedicata</b> (usata dal login SSO). Operazione sul mailserver: usa prima <b>Anteprima</b>.</div>
    <div class="mp-box">
      <div class="mp-row">
        <div class="mp-f"><label>Utente (facoltativo)</label><input id="mp-user" placeholder="email utente Frappe…"></div>
        <div class="mp-f"><label>Casella</label><input id="mp-mbox" placeholder="nome@thanatos.agency"></div>
        <button class="btn btn-default" id="mp-prev">Anteprima</button>
        <button class="btn btn-primary" id="mp-go" disabled>Provisiona</button>
      </div>
      <div class="mp-plan" id="mp-plan"></div>
      <div class="mp-msg" id="mp-msg"></div>
    </div>
    <div class="mp-box">
      <h3 style="font-size:14px;margin:0 0 12px">Caselle abilitate alla webmail</h3>
      <div class="mp-list" id="mp-enabled"><span class="mp-empty">Caricamento…</span></div>
    </div>
  </div>`);

  const $user=$('#mp-user'), $mbox=$('#mp-mbox'), $plan=$('#mp-plan'), $msg=$('#mp-msg'), $go=$('#mp-go');
  let lastPlan=null;

  $('#mp-prev').on('click', ()=>{
    const mb=($mbox.val()||'').trim().toLowerCase();
    if(!mb){ $msg.html('<span style="color:#c0392b">Inserisci la casella.</span>'); return; }
    $msg.text('Verifica…'); $plan.hide(); $go.prop('disabled',true);
    frappe.call({method:'thanatos_intel.api.mail_provisioning.preview',args:{user:$user.val()||'',mailbox:mb}})
      .then(r=>{ const p=r.message; lastPlan=p; $msg.text('');
        $plan.show().html(
          `Casella <b>${p.mailbox}</b><br>`+
          (p.account_exists?'<span class="ok">✓ account già esistente</span>':'<span class="warn">＋ verrà creato l\\'account</span>')+'<br>'+
          (p.already_webmail_enabled?'<span class="warn">↻ webmail già abilitata: verrà rigenerata l\\'app-password</span>':'<span class="ok">＋ verrà generata l\\'app-password webmail</span>'));
        $go.prop('disabled',false);
      }).catch(e=>{ $msg.html('<span style="color:#c0392b">'+(e.message||'Errore')+'</span>'); });
  });

  $go.on('click', ()=>{
    if(!lastPlan) return;
    frappe.confirm(`Provisionare <b>${lastPlan.mailbox}</b> sul mailserver?`, ()=>{
      $msg.text('Provisioning…'); $go.prop('disabled',true);
      frappe.call({method:'thanatos_intel.api.mail_provisioning.provision',
        args:{user:$user.val()||'',mailbox:lastPlan.mailbox},freeze:true,freeze_message:'Mailserver…'})
        .then(r=>{ const m=r.message;
          frappe.show_alert({message:`${m.mailbox} ${m.account_created?'creata e ':''}abilitata alla webmail`,indicator:'green'});
          $msg.html('<span style="color:#2e7d32">Fatto.</span>'); $plan.hide(); loadEnabled();
        }).catch(e=>{ $msg.html('<span style="color:#c0392b">'+(e.message||'Errore')+'</span>'); $go.prop('disabled',false); });
    });
  });

  function loadEnabled(){
    frappe.call({method:'thanatos_intel.api.mail_provisioning.list_enabled'}).then(r=>{
      const a=r.message||[]; const $e=$('#mp-enabled').empty();
      if(!a.length){ $e.html('<span class="mp-empty">Nessuna casella ancora abilitata.</span>'); return; }
      a.forEach(m=>$e.append(`<span class="mp-tag">✉️ ${frappe.utils.escape_html(m)}</span>`));
    });
  }
  loadEnabled();
};
