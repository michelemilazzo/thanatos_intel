
// PCU Global Floating Widget — accessibile da ogni pagina desk
frappe.ready(function(){ if(window.__pcu_global_loaded) return; window.__pcu_global_loaded = true;

function injectStyle(){
  if(document.getElementById('pcu-g-style')) return;
  const s = document.createElement('style'); s.id='pcu-g-style';
  s.textContent = `
    #pcu-g-fab{position:fixed;right:20px;bottom:20px;width:54px;height:54px;border-radius:50%;
      background:linear-gradient(135deg,#1f6feb,#22863a);color:#fff;border:0;cursor:pointer;
      box-shadow:0 6px 24px rgba(0,0,0,.25);z-index:9999;font-size:24px;display:flex;
      align-items:center;justify-content:center;transition:transform .2s}
    #pcu-g-fab:hover{transform:scale(1.1)}
    #pcu-g-fab .badge{position:absolute;top:-4px;right:-4px;background:#e54;color:#fff;
      border-radius:10px;padding:2px 6px;font-size:10px;font-weight:bold;min-width:18px;display:none}
    .pcu-g-modal-fs .modal-dialog{max-width:90vw;width:90vw;margin:3vh auto}
    .pcu-g-modal-fs .modal-content{min-height:88vh}
  `;
  document.head.appendChild(s);
}

function fab(){
  injectStyle();
  if(document.getElementById('pcu-g-fab')) return;
  const btn = document.createElement('button');
  btn.id = 'pcu-g-fab';
  btn.title = 'Pannello comunicazioni globale';
  btn.innerHTML = '✉<span class="badge" id="pcu-g-badge">0</span>';
  btn.addEventListener('click', openDialog);
  document.body.appendChild(btn);
}

async function openDialog(){
  const senders = await frappe.call({method:'thanatos_intel.api.comm_pane.get_senders'}).then(r=>r.message||[]);
  const wa = await frappe.call({method:'thanatos_intel.api.comm_pane.get_wa_senders'}).then(r=>r.message||[]);
  const tpls = await frappe.db.get_list('Email Template',{filters:[['name','like','Thanatos %']],fields:['name'],limit:50});

  const d = new frappe.ui.Dialog({
    title: '✉ Pannello Comunicazioni Globale',
    size: 'extra-large',
    fields: [
      {fieldname:'channel', fieldtype:'Select', label:'Canale', options:'📧 Email\n💬 WhatsApp', default:'📧 Email', reqd:1},
      {fieldname:'from_email', fieldtype:'Select', label:'Da (sender)',
       options: senders.length ? senders.map(s=>s.label).join('\n') : '',
       default: (senders.find(s=>s.default)||senders[0]||{}).label,
       depends_on:'eval:doc.channel=="📧 Email"'},
      {fieldname:'from_wa', fieldtype:'Select', label:'Da (numero WhatsApp)',
       options: wa.length ? wa.map(s=>s.label).join('\n') : 'nessun numero configurato',
       depends_on:'eval:doc.channel=="💬 WhatsApp"'},
      {fieldname:'cb1', fieldtype:'Column Break'},
      {fieldname:'recipient_dt', fieldtype:'Link', label:'Destinatario (cerca anagrafica)',
       options:'Contact', description:'Cerca per nome — autocompila email/telefono'},
      {fieldname:'recipient_value', fieldtype:'Data', label:'Email / Telefono', reqd:1,
       description:'Indirizzo email o numero WhatsApp (con prefisso)'},
      {fieldname:'sb2', fieldtype:'Section Break'},
      {fieldname:'subject', fieldtype:'Data', label:'Oggetto (email)',
       depends_on:'eval:doc.channel=="📧 Email"'},
      {fieldname:'template', fieldtype:'Select', label:'Template',
       options: ['']+tpls.map(t=>t.name).join('\n'),
       depends_on:'eval:doc.channel=="📧 Email"'},
      {fieldname:'sb3', fieldtype:'Section Break', label:'Messaggio'},
      {fieldname:'body', fieldtype:'Text Editor', label:'', reqd:1},
      {fieldname:'sb4', fieldtype:'Section Break', label:'Aggancia a documento (opzionale)'},
      {fieldname:'ref_doctype', fieldtype:'Link', label:'Tipo documento', options:'DocType'},
      {fieldname:'ref_name', fieldtype:'Dynamic Link', label:'Documento', options:'ref_doctype'},
    ],
    primary_action_label: '▸ Invia',
    async primary_action(values){
      const ch = values.channel==='📧 Email' ? 'email':'whatsapp';
      const refDt = values.ref_doctype || 'User';
      const refName = values.ref_name || frappe.session.user;
      try{
        if(ch==='email'){
          // Estrai email da label "Name <email@x>"
          const m = (values.from_email||'').match(/<([^>]+)>/);
          const sender = m ? m[1] : null;
          await frappe.call({method:'thanatos_intel.api.comm_pane.send_email',
            args:{doctype:refDt, name:refName, recipients:values.recipient_value,
                  subject:values.subject||'Comunicazione', content:values.body,
                  template:values.template||null, from_email:sender}});
        } else {
          await frappe.call({method:'thanatos_intel.api.comm_pane.send_whatsapp',
            args:{doctype:refDt, name:refName, to:values.recipient_value, content:values.body}});
        }
        frappe.show_alert({message:'Inviato ✓',indicator:'green'});
        d.hide();
      }catch(e){ frappe.msgprint('Errore: '+e.message); }
    },
  });
  d.$wrapper.addClass('pcu-g-modal-fs');
  d.show();

  // Autocompila destinatario da Contact selezionato
  d.fields_dict.recipient_dt.df.onchange = async ()=>{
    const v = d.get_value('recipient_dt');
    if(!v) return;
    const c = await frappe.db.get_doc('Contact', v).catch(()=>null);
    if(!c) return;
    const ch = d.get_value('channel');
    const val = ch==='📧 Email' ? (c.email_id||c.email_ids?.[0]?.email_id||'') : (c.mobile_no||c.phone_nos?.[0]?.phone||'');
    d.set_value('recipient_value', val);
  };
}

fab();
});
