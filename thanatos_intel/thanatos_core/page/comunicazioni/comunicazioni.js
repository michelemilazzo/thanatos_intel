
frappe.pages['comunicazioni'].on_page_load = function(wrapper){
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: '💬 Console Comunicazioni',
    single_column: true
  });

  const $body = $(wrapper).find('.layout-main-section');
  $body.html(`
<style>
  .cc-grid{display:grid;grid-template-columns:280px 1fr 380px;gap:0;height:calc(100vh - 180px);border:1px solid #e3e3e3;border-radius:8px;overflow:hidden;background:#fff}
  .cc-side{border-right:1px solid #e3e3e3;background:#fafafa;display:flex;flex-direction:column}
  .cc-search{padding:10px;border-bottom:1px solid #e3e3e3}
  .cc-search input{width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:6px}
  .cc-list{flex:1;overflow:auto}
  .cc-item{padding:10px 14px;border-bottom:1px solid #eee;cursor:pointer}
  .cc-item:hover{background:#f0f7ff}
  .cc-item.active{background:#e3f0ff;border-left:3px solid #1f6feb}
  .cc-item .who{font-weight:bold;font-size:13px}
  .cc-item .snippet{font-size:11px;color:#666;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
  .cc-item .meta{font-size:10px;color:#999;margin-top:2px}
  .cc-thread{flex:1;display:flex;flex-direction:column;background:#fff}
  .cc-thread-hd{padding:12px 16px;border-bottom:1px solid #e3e3e3;background:#fafafa}
  .cc-msgs{flex:1;overflow:auto;padding:14px 18px;background:#f5f5f5}
  .cc-msg{margin:8px 0;padding:10px 12px;border-radius:8px;max-width:80%;background:#fff;border:1px solid #e3e3e3}
  .cc-msg.out{margin-left:auto;background:#dcf8c6;border-color:#c0e8a4}
  .cc-msg .head{font-size:10px;color:#666;margin-bottom:4px}
  .cc-side-right{border-left:1px solid #e3e3e3;background:#fafafa;display:flex;flex-direction:column}
  .cc-composer{padding:12px;display:flex;flex-direction:column;gap:8px;height:100%;overflow:auto}
  .cc-composer label{font-size:11px;color:#666;font-weight:bold;text-transform:uppercase;letter-spacing:.5px}
  .cc-composer input,.cc-composer select,.cc-composer textarea{padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:12px;width:100%;box-sizing:border-box}
  .cc-composer textarea{min-height:140px;font-family:inherit;resize:vertical}
  .cc-att{display:flex;flex-wrap:wrap;gap:4px;padding:6px;border:1px dashed #bbb;border-radius:6px;min-height:40px;background:#fff;font-size:11px}
  .cc-att .chip{background:#eee;padding:3px 8px;border-radius:10px;font-size:10px}
  .cc-att .chip .x{cursor:pointer;margin-left:6px;color:#999}
  .cc-send{background:#1f6feb;color:#fff;border:0;padding:8px;border-radius:6px;cursor:pointer;font-weight:bold;font-size:13px}
  .cc-send:hover{background:#1656c0}
  .cc-empty{padding:40px;text-align:center;color:#999;font-style:italic}
  .cc-tab{display:flex;gap:0;border-bottom:1px solid #e3e3e3}
  .cc-tab button{flex:1;padding:8px;border:0;background:#fff;cursor:pointer;font-size:12px;border-bottom:2px solid transparent}
  .cc-tab button.active{border-bottom-color:#1f6feb;font-weight:bold;color:#1f6feb}
</style>

<div class="cc-grid">

  <!-- SIDEBAR -->
  <div class="cc-side">
    <div class="cc-search">
      <input id="cc-search" type="text" placeholder="🔍 Cerca conversazione…">
      <div style="font-size:10px;color:#888;margin-top:4px"><span id="cc-count">0</span> conversazioni</div>
    </div>
    <div class="cc-list" id="cc-list">
      <div class="cc-empty">Carico…</div>
    </div>
  </div>

  <!-- THREAD -->
  <div class="cc-thread">
    <div class="cc-thread-hd" id="cc-thread-hd">
      <b id="cc-thread-who">— Seleziona una conversazione —</b>
      <div style="font-size:11px;color:#666" id="cc-thread-meta"></div>
    </div>
    <div class="cc-msgs" id="cc-msgs">
      <div class="cc-empty">Nessuna conversazione selezionata</div>
    </div>
  </div>

  <!-- COMPOSER -->
  <div class="cc-side-right">
    <div class="cc-tab">
      <button class="active" data-tab="new">✉ Nuovo</button>
      <button data-tab="dossier">📦 Dossier</button>
      <button data-tab="map">🗺 Mappa</button>
    </div>
    <div class="cc-composer" id="cc-pane-new">
      <label>Canale</label>
      <select id="cc-ch"><option value="email">📧 Email</option><option value="whatsapp">💬 WhatsApp</option></select>

      <label>Da (mittente)</label>
      <select id="cc-from"></select>

      <label>A (destinatario)</label>
      <input id="cc-to" type="text" placeholder="email/numero — digita per cercare" autocomplete="off">
      <div id="cc-to-sugg" style="display:none;border:1px solid #ddd;border-radius:6px;background:#fff;max-height:160px;overflow:auto;font-size:11px"></div>

      <label>Oggetto</label>
      <input id="cc-subj" type="text" placeholder="Oggetto email">

      <label>Template</label>
      <select id="cc-tpl"><option value="">— vuoto —</option></select>

      <label>Allegati (clicca per aggiungere)</label>
      <div class="cc-att" id="cc-att"><span style="color:#999;font-size:11px">Trascina qui o clicca "+" sotto</span></div>
      <button class="btn btn-xs btn-default" id="cc-att-add">+ Aggiungi documento</button>

      <label>Testo messaggio</label>
      <textarea id="cc-body" placeholder="Scrivi qui…"></textarea>

      <label>Lingue d'invio (multi-select)</label>
      <select id="cc-langs" multiple size="4">
        <option value="it" selected>🇮🇹 Italiano</option>
        <option value="en">🇬🇧 English</option>
        <option value="ro">🇷🇴 Română</option>
        <option value="bg">🇧🇬 Български</option>
        <option value="de">🇩🇪 Deutsch</option>
        <option value="fr">🇫🇷 Français</option>
        <option value="es">🇪🇸 Español</option>
      </select>

      <label>Aggancia a documento (opzionale)</label>
      <div style="display:flex;gap:4px">
        <select id="cc-ref-dt" style="flex:1"><option value="">—</option>
          <option>Investigation Case</option><option>Agency Mandate</option><option>Diplomatic Eligibility Case</option>
          <option>Diplomatic Proforma</option><option>Customer</option><option>Intel Lead</option>
        </select>
        <input id="cc-ref-name" type="text" placeholder="ID doc" style="flex:1">
      </div>

      <button class="cc-send" id="cc-send">📨 Invia ▸</button>
    </div>

    <div class="cc-composer" id="cc-pane-dossier" style="display:none">
      <h4 style="margin:0">📦 Invio Dossier completo</h4>
      <small style="color:#666">Genera mail bilingue con tutti i mandati, proforme, link firma e PDF tradotti — già pronto.</small>
      <label>Caso master</label>
      <input id="cc-d-case" type="text" placeholder="CASE-2026-XXXX">
      <label>Destinatario</label>
      <input id="cc-d-rec" type="text">
      <label>Lingue dossier</label>
      <select id="cc-d-langs" multiple size="4">
        <option value="it" selected>🇮🇹 IT</option>
        <option value="en" selected>🇬🇧 EN</option>
        <option value="ro">🇷🇴 RO</option><option value="bg">🇧🇬 BG</option>
      </select>
      <label>Da</label>
      <select id="cc-d-from"></select>
      <button class="cc-send" id="cc-d-send">📨 Componi e invia dossier</button>
      <div id="cc-d-result" style="font-size:11px;color:#666;margin-top:8px"></div>
    </div>

    <div class="cc-composer" id="cc-pane-map" style="display:none">
      <h4 style="margin:0">🗺 Mappa feature Thanatos</h4>
      <div id="cc-map-list" style="font-size:12px"></div>
    </div>
  </div>
</div>
  `);

  let allConvs = [];
  let activeKey = null;
  let attachments = [];

  // Carica lista conversazioni: unione Communication + WABA grouped by recipient
  function load_conversations(){
    frappe.call({
      method:'thanatos_intel.api.comm_pane.list_conversations',
      args:{limit:200}
    }).then(r=>{
      allConvs = r.message || [];
      render_list();
    });
  }

  function render_list(){
    const q = ($('#cc-search').val()||'').toLowerCase();
    const filtered = allConvs.filter(c=>!q || (c.who+' '+c.snippet+' '+c.addr).toLowerCase().includes(q));
    $('#cc-count').text(filtered.length);
    if(!filtered.length){ $('#cc-list').html('<div class="cc-empty">Nessuna conversazione</div>'); return; }
    $('#cc-list').html(filtered.map(c=>`
      <div class="cc-item ${activeKey===c.key?'active':''}" data-key="${frappe.utils.escape_html(c.key)}">
        <div class="who">${c.icon||''} ${frappe.utils.escape_html(c.who||c.addr)}</div>
        <div class="snippet">${frappe.utils.escape_html(c.snippet||'')}</div>
        <div class="meta">${c.ts||''} · ${c.count} msg${c.unread?` · <b style="color:#e54">${c.unread} nuovi</b>`:''}</div>
      </div>`).join(''));
    $('#cc-list .cc-item').on('click', function(){
      activeKey = $(this).data('key');
      render_list();
      load_thread(activeKey);
    });
  }

  function load_thread(key){
    $('#cc-msgs').html('<div class="cc-empty">Carico…</div>');
    frappe.call({method:'thanatos_intel.api.comm_pane.conversation_thread', args:{key}})
      .then(r=>{
        const msgs = r.message?.messages || [];
        const info = r.message?.info || {};
        $('#cc-thread-who').text(info.who || key);
        $('#cc-thread-meta').text(`${info.addr||''} · ${msgs.length} messaggi`);
        $('#cc-to').val(info.addr || '');
        $('#cc-ref-dt').val(info.ref_doctype || '');
        $('#cc-ref-name').val(info.ref_name || '');
        if(!msgs.length){ $('#cc-msgs').html('<div class="cc-empty">Nessun messaggio</div>'); return; }
        $('#cc-msgs').html(msgs.map(m=>`
          <div class="cc-msg ${m.direction==='out'?'out':''}">
            <div class="head">${m.channel==='email'?'📧':'💬'} ${m.direction==='in'?'← ricevuto':'→ inviato'} · ${m.ts} ${m.status?'· '+m.status:''}</div>
            ${m.subject?`<b>${frappe.utils.escape_html(m.subject)}</b><br>`:''}
            <div>${m.text||''}</div>
          </div>`).join(''));
        $('#cc-msgs').scrollTop($('#cc-msgs')[0].scrollHeight);
      });
  }

  // Tabs
  $('.cc-tab button').on('click', function(){
    $('.cc-tab button').removeClass('active'); $(this).addClass('active');
    const t = $(this).data('tab');
    $('#cc-pane-new, #cc-pane-dossier, #cc-pane-map').hide();
    $(`#cc-pane-${t}`).show();
    if(t==='map') load_map();
  });

  // Carica mittenti
  frappe.call({method:'thanatos_intel.api.comm_pane.get_senders'}).then(r=>{
    const opts = (r.message||[]).map(s=>`<option value="${s.value}" ${s.default?'selected':''}>${frappe.utils.escape_html(s.label)}</option>`).join('');
    $('#cc-from, #cc-d-from').html(opts);
  });
  // Email Template
  frappe.db.get_list('Email Template',{filters:[['name','like','Thanatos %']],fields:['name'],limit:50}).then(rows=>{
    rows.forEach(r=>$('#cc-tpl').append(`<option>${r.name}</option>`));
  });

  // Autocomplete destinatario
  let tmr;
  $('#cc-to').on('input focus', function(){
    clearTimeout(tmr);
    const q = $(this).val().trim();
    const ch = $('#cc-ch').val();
    tmr = setTimeout(async()=>{
      const items = await frappe.call({method:'thanatos_intel.api.comm_pane.search_recipients',args:{query:q,channel:ch,limit:15}}).then(r=>r.message||[]);
      if(!items.length){ $('#cc-to-sugg').hide(); return; }
      $('#cc-to-sugg').html(items.map(i=>`<div data-v="${frappe.utils.escape_html(i.value)}" style="padding:6px 10px;cursor:pointer;border-bottom:1px solid #f0f0f0"><b>${frappe.utils.escape_html(i.label)}</b><span style="float:right;color:#999;font-size:10px">${i.source}</span></div>`).join('')).show();
    },250);
  });
  $('#cc-to-sugg').on('click','div', function(){ $('#cc-to').val($(this).data('v')); $('#cc-to-sugg').hide(); });
  $('#cc-to').on('blur', ()=>setTimeout(()=>$('#cc-to-sugg').hide(),200));

  // Allegati: dialog file picker
  $('#cc-att-add').on('click', ()=>{
    new frappe.ui.FileUploader({
      doctype: $('#cc-ref-dt').val() || 'User',
      docname: $('#cc-ref-name').val() || frappe.session.user,
      on_success: file => {
        attachments.push({file_url: file.file_url, file_name: file.file_name||file.file_url});
        render_attachments();
      }
    });
  });
  function render_attachments(){
    if(!attachments.length){ $('#cc-att').html('<span style="color:#999;font-size:11px">Trascina qui o clicca "+" sotto</span>'); return; }
    $('#cc-att').html(attachments.map((a,i)=>`<span class="chip">📎 ${frappe.utils.escape_html(a.file_name)}<span class="x" data-i="${i}">✕</span></span>`).join(''));
  }
  $('#cc-att').on('click','.x', function(){ attachments.splice($(this).data('i'),1); render_attachments(); });

  // Send
  $('#cc-send').on('click', async()=>{
    const ch = $('#cc-ch').val();
    const langs = $('#cc-langs').val() || ['it'];
    const tpl = $('#cc-tpl').val();
    const to = $('#cc-to').val().trim();
    const body = $('#cc-body').val().trim();
    const subj = $('#cc-subj').val() || 'Comunicazione';
    const from_email = $('#cc-from').val();
    const ref_dt = $('#cc-ref-dt').val() || 'User';
    const ref_name = $('#cc-ref-name').val() || frappe.session.user;
    if(!to || (!body && !tpl)) return frappe.msgprint('Compila destinatario e testo (o template)');
    try{
      if(ch==='email'){
        if(langs.length > 1){
          await frappe.call({method:'thanatos_intel.api.comm_pane.send_email_multilang',
            args:{doctype:ref_dt,name:ref_name,recipients:to,subject:subj,content:body,langs:langs.join(','),from_email}});
          frappe.show_alert({message:`Inviato in ${langs.length} lingue`,indicator:'green'});
        } else {
          await frappe.call({method:'thanatos_intel.api.comm_pane.send_email',
            args:{doctype:ref_dt,name:ref_name,recipients:to,subject:subj,content:body,template:tpl||null,attachments:JSON.stringify(attachments),from_email}});
          frappe.show_alert({message:'Email inviata',indicator:'green'});
        }
      } else {
        await frappe.call({method:'thanatos_intel.api.comm_pane.send_whatsapp',
          args:{doctype:ref_dt,name:ref_name,to,content:body}});
        frappe.show_alert({message:'WhatsApp inviato',indicator:'green'});
      }
      $('#cc-body').val(''); $('#cc-subj').val(''); attachments=[]; render_attachments();
      load_conversations();
    }catch(e){ frappe.msgprint('Errore: '+e.message); }
  });

  // Dossier send
  $('#cc-d-send').on('click', async()=>{
    const case_name = $('#cc-d-case').val().trim();
    const rec = $('#cc-d-rec').val().trim();
    const langs = ($('#cc-d-langs').val()||['it']).join(',');
    const from_email = $('#cc-d-from').val();
    if(!case_name || !rec) return frappe.msgprint('Case e destinatario richiesti');
    $('#cc-d-result').text('Generazione PDF e invio…');
    try{
      const r = await frappe.call({method:'thanatos_intel.api.comm_pane.send_dossier_email',
        args:{case_name, recipient:rec, langs, from_email, send:1}}).then(r=>r.message);
      if(r.ok){
        $('#cc-d-result').html(`✅ Inviato: ${r.pdf_count} PDF allegati · ${r.sign_links} link firma · comm ${r.communication}`);
        frappe.show_alert({message:'Dossier inviato',indicator:'green'});
      } else $('#cc-d-result').html(`❌ ${r.error||'Errore'}`);
    }catch(e){ $('#cc-d-result').html(`❌ ${e.message}`); }
  });

  // Mappa feature
  function load_map(){
    $('#cc-map-list').html(`
      <h5>📨 Messaggistica</h5>
      <ul>
        <li>📋 PCU compatto su ogni form (40+ DocType)</li>
        <li>✉ Widget globale floating (basso-dx, ogni pagina)</li>
        <li>🌐 Multi-lingua send (8 lingue)</li>
        <li>🔍 Autocomplete destinatario (Contact/Customer/Applicant/User)</li>
      </ul>
      <h5>📜 Mandati & Firme</h5>
      <ul>
        <li><a href="/app/agency-mandate">Agency Mandate</a> — 4 firme sequenziali</li>
        <li><a href="/app/signature-request">Signature Request</a> + anteprima PDF inline + share</li>
        <li><a href="/app/signature-template">Signature Template</a> (5 template)</li>
        <li><a href="/app/mandate-clause">Mandate Clause</a> — libreria 10 clausole + editor full-screen</li>
        <li>🌐 Traduci PDF (15 lingue, cache 30gg)</li>
      </ul>
      <h5>💶 Fatturazione</h5>
      <ul>
        <li><a href="/app/diplomatic-proforma">Diplomatic Proforma</a> + Stripe + accettazione firma</li>
        <li><a href="/app/billing-entity">Billing Entity</a> (ARES + Thanatos) + linked Email Account</li>
      </ul>
      <h5>📁 Pratiche</h5>
      <ul>
        <li><a href="/app/investigation-case">Investigation Case</a> — Pipeline cliccabile + ←/→</li>
        <li><a href="/app/diplomatic-eligibility-case">DDD Case</a> — Timeline + AI suggest 🤖</li>
        <li><a href="/app/kyb-check">KYB Check</a> · <a href="/app/kyc-check">KYC Check</a></li>
      </ul>
      <h5>🛠 Setup</h5>
      <ul>
        <li><a href="/app/thanatos-setup">🛠 Thanatos Setup</a></li>
        <li><a href="/app/thanatos-operativo">📋 Thanatos Operativo</a></li>
        <li><a href="/app/thanatos-insight">📊 Thanatos Insight</a></li>
      </ul>
      <h5>🤖 AI & monitoring</h5>
      <ul>
        <li>Gateway: 10.10.0.4:8800 (Claude Sonnet 4.5)</li>
        <li>URL monitor flotta (cron 5min, alert email)</li>
        <li>WhatsApp auto-link inbound</li>
      </ul>
      <p style="color:#888;font-size:10px;margin-top:10px">📍 Esempio Foglio/Petterson: <a href="/app/investigation-case/CASE-2026-0013">CASE-2026-0013</a></p>
    `);
  }

  $('#cc-search').on('input', render_list);

  load_conversations();
};
