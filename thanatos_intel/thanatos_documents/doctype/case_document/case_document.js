frappe.ui.form.on('Case Document', {
	refresh(frm) {
		if (frm.is_new()) return;
		const badge = {Bozza:'orange','In Revisione':'yellow',Certificato:'blue',Inviato:'green',Archiviato:'darkgrey'};
		if (frm.doc.status) frm.page.set_indicator(frm.doc.status, badge[frm.doc.status] || 'grey');

		// genera bozza dai report
		if (frm.doc.status === 'Bozza' || !frm.doc.editable_docx) {
			frm.add_custom_button(__('Genera bozza dai report'), () => {
				const d = new frappe.ui.Dialog({
					title: __('Seleziona i report da includere'),
					fields: [
						{fieldname:'kyb',fieldtype:'Check',label:'Report KYB'},
						{fieldname:'blockchain',fieldtype:'Check',label:'Report Blockchain'},
						{fieldname:'osint',fieldtype:'Check',label:'Report OSINT'},
						{fieldname:'recovery',fieldtype:'Check',label:'Piano di Recupero'},
						{fieldname:'full',fieldtype:'Check',label:'Dossier Completo'}
					],
					primary_action_label: __('Genera docx'),
					primary_action(v) {
						const kinds = Object.keys(v).filter(k => v[k]);
						if (!kinds.length) { frappe.msgprint(__('Seleziona almeno un report.')); return; }
						frappe.call({method:'generate_from_reports', doc:frm.doc, args:{kinds:kinds.join(',')},
							freeze:true, freeze_message:__('Generazione docx…'),
							callback(r){ d.hide(); frappe.show_alert({message:__('Bozza docx creata ({0} sezioni)',[r.message.sections]),indicator:'green'}); frm.reload_doc(); }});
					}
				});
				d.show();
			}, __('Documento'));
		}

		// certifica
		if (frm.doc.editable_docx && frm.doc.status !== 'Inviato') {
			frm.add_custom_button(__('Certifica (PDF + SHA-256)'), () => {
				frappe.confirm(__('Bloccare questa versione e generare il PDF certificato?'), () => {
					frappe.call({method:'certify', doc:frm.doc, freeze:true, freeze_message:__('Certificazione…'),
						callback(r){ frappe.show_alert({message:__('Certificato v{0} — SHA-256 {1}…',[r.message.version, (r.message.sha256||'').slice(0,12)]),indicator:'blue'}); frm.reload_doc(); }});
				});
			}, __('Documento'));
		}

		// nuova versione
		if (['Certificato','Inviato','Archiviato'].includes(frm.doc.status)) {
			frm.add_custom_button(__('Nuova versione'), () => {
				frappe.call({method:'new_version', doc:frm.doc, callback(r){ frappe.show_alert({message:__('Versione {0} — torna in bozza',[r.message.version]),indicator:'orange'}); frm.reload_doc(); }});
			}, __('Documento'));
		}

		// protocollo
		if (!frm.doc.protocol_number) {
			frm.add_custom_button(__('Protocolla'), () => {
				frappe.prompt([{fieldname:'direction',fieldtype:'Select',label:__('Direzione'),options:'Interno\nUscita\nEntrata',default:'Uscita',reqd:1}],
					(v) => frappe.call({method:'assign_protocol', doc:frm.doc, args:{direction:v.direction}, callback(r){ frappe.show_alert({message:__('Protocollo {0}',[r.message.protocol_number]),indicator:'green'}); frm.reload_doc(); }}),
					__('Protocollo'), __('Assegna'));
			}, __('Protocollo'));
		}

		// invio
		if (frm.doc.status === 'Certificato') {
			frm.add_custom_button(__('Segna come inviato'), () => {
				frappe.prompt([
					{fieldname:'channel',fieldtype:'Select',label:__('Canale'),options:'Email\nPEC\nConsegna a mano',default:'Email',reqd:1},
					{fieldname:'recipient',fieldtype:'Data',label:__('Destinatario')}
				], (v) => frappe.call({method:'mark_sent', doc:frm.doc, args:{channel:v.channel, recipient:v.recipient}, callback(){ frm.reload_doc(); }}),
				__('Invio'), __('Conferma'));
			}, __('Protocollo'));

			frm.add_custom_button(__('Invia a DocuSeal (firma)'), () => {
				frappe.prompt([
					{fieldname:'signer_email',fieldtype:'Data',label:__('Email firmatario')},
					{fieldname:'signer_name',fieldtype:'Data',label:__('Nome firmatario')}
				], (v) => frappe.call({method:'send_docuseal', doc:frm.doc, args:{signer_email:v.signer_email, signer_name:v.signer_name}, freeze:true, freeze_message:__('Invio…'),
					callback(r){ if(r.message&&r.message.ok){ frappe.show_alert({message:__('Inviato per firma'),indicator:'green'}); if(r.message.signing_url) window.open(r.message.signing_url,'_blank'); frm.reload_doc(); } }}),
				__('Firma DocuSeal'), __('Invia'));
			}, __('Protocollo'));
		}
	}
});
