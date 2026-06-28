frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        ThanatosPipeline.render(frm, 'get_case_pipeline');

        // Badge stato caso
        const colors = {
            'Open': 'blue', 'In Progress': 'yellow', 'Completed': 'green',
            'Closed': 'darkgrey', 'Archived': 'darkgrey', 'On Hold': 'orange'
        };
        if (frm.doc.status) {
            frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || 'grey');
        }

        thanatos_set_monitor_operators(frm);

        if (!frm.is_new()) {
            frm.add_custom_button(__("Registra Chiamata"), () => {
                window.thanatos && window.thanatos.logCall({
                    linked_case: frm.doc.name,
                    linked_client: frm.doc.client || "",
                    onSuccess() { frm.reload_doc(); },
                });
            }, __("Azioni"));
        }

        if (!frm.is_new() && frm.doc.drive_folder) {
            frm.add_custom_button(__('Apri Drive'), () => {
                window.open('/drive/folder/' + frm.doc.drive_folder, '_blank');
            }, __('File'));

            frm.add_custom_button(__('Organizza in Drive'), () => {
                frappe.call({
                    method: 'thanatos_intel.reporting.case_reports.organize_case_files_to_drive',
                    args: { case_name: frm.doc.name },
                    freeze: true, freeze_message: __('Smistamento allegati in Drive…'),
                    callback(r) {
                        const m = r.message || {};
                        frappe.show_alert({ message: __('{0} allegati organizzati in Drive', [m.in_drive]), indicator: 'green' }, 6);
                    }
                });
            }, __('File'));

            frm.add_custom_button(__('Genera delega AdE'), () => {
                const dl = new frappe.ui.Dialog({
                    title: __('Delega Agenzia delle Entrate'),
                    fields: [
                        { fieldname: 'delegato_nome', fieldtype: 'Data', label: 'Delegato / Studio (intermediario)', reqd: 1 },
                        { fieldname: 'delegato_cf', fieldtype: 'Data', label: 'C.F. delegato' },
                        { fieldname: 'legale_rappresentante', fieldtype: 'Data', label: 'Legale rappresentante del cliente' },
                        { fieldname: 'lr_cf', fieldtype: 'Data', label: 'C.F. legale rappresentante' },
                        { fieldname: 'lr_nato_a', fieldtype: 'Data', label: 'Nato a' },
                        { fieldname: 'lr_nato_il', fieldtype: 'Data', label: 'Nato il' },
                        { fieldname: 'sv_fatture', fieldtype: 'Check', label: 'Consultazione/acquisizione fatture elettroniche', default: 1 },
                        { fieldname: 'sv_cassetto', fieldtype: 'Check', label: 'Cassetto fiscale', default: 1 },
                        { fieldname: 'durata_anni', fieldtype: 'Int', label: 'Durata (anni)', default: 4 }
                    ],
                    primary_action_label: __('Genera PDF'),
                    primary_action(v) {
                        dl.hide();
                        const servizi = [];
                        if (v.sv_fatture) servizi.push('fatture');
                        if (v.sv_cassetto) servizi.push('cassetto');
                        frappe.call({
                            method: 'thanatos_intel.reporting.delega_ade.genera_delega',
                            args: { case: frm.doc.name, delegato_nome: v.delegato_nome, delegato_cf: v.delegato_cf,
                                    legale_rappresentante: v.legale_rappresentante, lr_cf: v.lr_cf,
                                    lr_nato_a: v.lr_nato_a, lr_nato_il: v.lr_nato_il,
                                    durata_anni: v.durata_anni, servizi: JSON.stringify(servizi) },
                            freeze: true, freeze_message: __('Genero la delega...'),
                            callback(r) {
                                const m = r.message || {};
                                if (m.file_url) { frappe.show_alert({ message: __('Delega generata.'), indicator: 'green' }, 6); window.open(m.file_url, '_blank'); }
                                frm.reload_doc();
                            }
                        });
                    }
                });
                dl.show();
            }, __('File'));

            frm.add_custom_button(__('Formulario investigativo'), () => {
                frappe.call({
                    method: 'thanatos_intel.reporting.formulario.genera_formulario',
                    args: { case: frm.doc.name },
                    freeze: true, freeze_message: __('Genero il formulario...'),
                    callback(r) {
                        const m = r.message || {};
                        if (m.file_url) { frappe.show_alert({ message: __('Formulario generato.'), indicator: 'green' }, 6); window.open(m.file_url, '_blank'); }
                        frm.reload_doc();
                    }
                });
            }, __('File'));

            frm.add_custom_button(__('Genera Fascicolo'), () => {
                frappe.call({
                    method: 'thanatos_intel.reporting.fascicolo.genera_fascicolo',
                    args: { case_name: frm.doc.name },
                    freeze: true, freeze_message: __('Composizione fascicolo del caso...'),
                    callback(r) {
                        const m = r.message || {};
                        frappe.show_alert({ message: __('Fascicolo pronto: {0} documenti, {1} pagine.', [m.documents, m.pages]), indicator: 'green' }, 8);
                        if (m.file_url) { window.open(m.file_url, '_blank'); }
                        else if (m.drive_url) { window.open(m.drive_url, '_blank'); }
                        frm.reload_doc();
                    }
                });
            }, __('File'));

            frm.add_custom_button(__('Genera fascicolo con custodia'), () => {
                frappe.call({
                    method: 'thanatos_intel.reporting.custody.generate_custody_dossier',
                    args: { case_name: frm.doc.name },
                    freeze: true, freeze_message: __('Composizione fascicolo + hash SHA-256…'),
                    callback(r) {
                        const m = r.message || {};
                        if (m.file_url) {
                            frappe.show_alert({ message: __('Fascicolo pronto: {0} doc uniti, {1} pag.', [m.merged, m.pages]), indicator: 'green' }, 7);
                            window.open(m.file_url, '_blank');
                        }
                    }
                });
            }, __('File'));

            frm.add_custom_button(__('Aggiungi alla Blacklist'), () => {
                frappe.call({
                    method: 'thanatos_intel.fraud_engine.blacklist_sync.sync_blacklist_from_case',
                    args: { case_name: frm.doc.name },
                    freeze: true, freeze_message: __('Aggiornamento blacklist…'),
                    callback(r) {
                        const m = r.message || {};
                        frappe.show_alert({ message: __('Blacklist: {0} nuove voci (totale {1})', [m.created, m.total_blacklist]), indicator: 'green' }, 6);
                    }
                });
            }, __('Intelligence'));

            frm.add_custom_button(__('Arricchisci con Arkham'), () => {
                frappe.call({
                    method: 'thanatos_intel.osint.arkham.enrich_case_with_arkham',
                    args: { case_name: frm.doc.name },
                    freeze: true, freeze_message: __('Attribution wallet via Arkham Intelligence…'),
                    callback(r) {
                        const m = r.message || {};
                        frappe.show_alert({ message: __('Arkham: {0}/{1} attribuiti — {2} exchange/VASP, {3} illeciti', [m.attributed, m.checked, m.cashout, m.illicit]), indicator: m.illicit ? 'red' : 'green' }, 8);
                        frm.reload_doc();
                    }
                });
            }, __('Intelligence'));

            frm.add_custom_button(__('Controlla wallet ora'), () => {
                frappe.call({
                    method: 'thanatos_intel.osint.wallet_monitor.snapshot_case_now',
                    args: { case_name: frm.doc.name },
                    freeze: true, freeze_message: __('Verifica saldi e attribuzioni in corso…'),
                    callback(r) {
                        const m = r.message || {};
                        frappe.show_alert({ message: __('Monitoraggio: {0} wallet, {1} variazioni rilevate', [m.wallets, m.changes]), indicator: m.changes ? 'red' : 'green' }, 7);
                        frm.reload_doc();
                    }
                });
            }, __('Intelligence'));
        }

        if (!frm.is_new() && !frm.doc.drive_folder) {
            frm.add_custom_button(__('Crea cartella Drive'), () => {
                frappe.call({
                    method: 'thanatos_intel.integrations.intel_inbox.ensure_case_folder_api',
                    args: { case_name: frm.doc.name },
                    callback(r) {
                        if (r.message && r.message.ok) {
                            frappe.show_alert({ message: 'Cartella Drive creata', indicator: 'green' });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('File'));
        }

        // Helpdesk tickets
        if (!frm.is_new()) {
            frm.add_custom_button(__('Apri Ticket'), () => {
                const d = new frappe.ui.Dialog({
                    title: 'Nuovo Ticket di Supporto',
                    fields: [
                        {fieldname: 'subject', fieldtype: 'Data', label: 'Oggetto', reqd: 1},
                        {fieldname: 'description', fieldtype: 'Text Editor', label: 'Descrizione', reqd: 1}
                    ],
                    primary_action_label: 'Crea Ticket',
                    primary_action(values) {
                        frappe.call({
                            method: 'thanatos_intel.integrations.helpdesk_bridge.create_ticket_for_case',
                            args: {case_name: frm.doc.name, subject: values.subject, description: values.description},
                            callback(r) {
                                if (r.message && r.message.ok) {
                                    frappe.show_alert({message: 'Ticket creato', indicator: 'green'});
                                    d.hide();
                                    window.open(r.message.url, '_blank');
                                }
                            }
                        });
                    }
                });
                d.show();
            }, __('Helpdesk'));

            frm.add_custom_button(__('Vedi Ticket'), () => {
                window.open(`/support?investigation_case=${frm.doc.name}`, '_blank');
            }, __('Helpdesk'));
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__('Calcola Risk Score'), () => {
                frappe.call({
                    method: 'thanatos_intel.thanatos_core.doctype.risk_score.risk_score.calculate_for_case',
                    args: { case_name: frm.doc.name },
                    freeze: true,
                    freeze_message: 'Calcolo in corso…',
                    callback(r) {
                        if (!r.exc && r.message) {
                            frappe.show_alert({
                                message: `Risk Score: <b>${r.message.score}</b> — <b>${r.message.classification}</b> (${r.message.matched} regole)`,
                                indicator: r.message.score >= 61 ? 'red' : r.message.score >= 31 ? 'orange' : 'green'
                            }, 6);
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Intelligence'));

            frm.add_custom_button(__('Fatture: ingerisci e riconcilia'), () => {
                frappe.call({
                    method: 'thanatos_intel.integrations.fatturapa.reconcile_invoices',
                    args: { case: frm.doc.name },
                    freeze: true, freeze_message: __('Parsing XML + riconciliazione...'),
                    callback(r) {
                        const m = r.message || {};
                        const flags = (m.flags || []);
                        frappe.msgprint({
                            title: __('Riconciliazione fatture') + ' — ' + (m.verdict || '-'),
                            indicator: (m.verdict === 'ALLARME') ? 'red' : (flags.length ? 'orange' : 'green'),
                            message: '<b>Dichiarate:</b> ' + (m.declared||0) + ' · <b>Reali (XML):</b> ' + (m.real||0) + ' · <b>mancanti:</b> ' + (m.missing||0) + '<br><br>' + (flags.length ? flags.map(frappe.utils.escape_html).join('<br>') : __('Nessuna discrepanza.'))
                        });
                        frm.reload_doc();
                    }
                });
            }, __('Intelligence'));

            frm.add_custom_button(__('✅ Checklist avanzamento'), () => {
                frappe.call({ method: 'thanatos_intel.ai.case_orchestrator.case_progress', args: { case: frm.doc.name, record: 0 },
                    callback(r) { const m = r.message || {}; frappe.msgprint({ title: __('Avanzamento') + ' ' + (m.done||0) + '/' + (m.total||0) + ' (' + (m.pct||0) + '%)', indicator: (m.pct>=80?'green':(m.pct>=50?'orange':'red')), message: '<pre style="white-space:pre-wrap;font-size:12px">' + frappe.utils.escape_html(m.text||'') + '</pre>' }); } });
            }, __('Intelligence'));
            frm.add_custom_button(__('▶ Analisi completa (tutto)'), () => {
                frappe.call({ method: 'thanatos_intel.ai.case_orchestrator.run_full_analysis_async', args: { case: frm.doc.name },
                    callback(r) { frappe.show_alert({ message: __('Pipeline avviata: screening, doppia cessione, domande, riconciliazione, fascicolo. Esito + checklist nelle attivita.'), indicator: 'blue' }, 9); } });
            }, __('Intelligence'));

            frm.add_custom_button(__('Verifica camerale (P.IVA)'), () => {
                const d = new frappe.ui.Dialog({
                    title: __('Verifica camerale Registro Imprese'),
                    fields: [{ fieldname: 'piva', fieldtype: 'Data', label: 'Partita IVA', reqd: 1 }],
                    primary_action_label: __('Verifica'),
                    primary_action(v) {
                        d.hide();
                        frappe.call({
                            method: 'thanatos_intel.osint.registro_imprese.verifica_impresa',
                            args: { piva: v.piva, investigation_case: frm.doc.name },
                            freeze: true, freeze_message: __('Verifica in corso...'),
                            callback(r) {
                                const m = r.message || {};
                                const c = m.checks || {};
                                let msg = '<b>P.IVA:</b> ' + (m.piva || '-') + '<br>'
                                    + '<b>Checksum:</b> ' + ((c.piva_checksum||{}).valid ? 'valido' : 'NON valido') + '<br>'
                                    + '<b>VIES:</b> ' + JSON.stringify((c.vies||{}).valid) + '<br>';
                                if (m.company) { msg += '<b>Denominazione:</b> ' + frappe.utils.escape_html(m.company.denominazione||'-') + '<br><b>Stato:</b> ' + frappe.utils.escape_html(m.company.stato||'-'); }
                                else if (m.manual_link) { msg += '<a href="' + m.manual_link + '" target="_blank">Apri visura su registroimprese.it (SPID)</a> e carica il PDF sul caso.'; }
                                if ((m.flags||[]).length) { msg += '<br><b style="color:#c0392b">Flag:</b> ' + m.flags.map(frappe.utils.escape_html).join('; '); }
                                frappe.msgprint({ title: __('Verifica camerale'), indicator: (m.flags||[]).length ? 'orange' : 'green', message: msg });
                                frm.reload_doc();
                            }
                        });
                    }
                });
                d.show();
            }, __('Intelligence'));

            frm.add_custom_button(__('Domande investigative'), () => {
                frappe.call({
                    method: 'thanatos_intel.ai.doc_questions.generate_questions_async',
                    args: { case: frm.doc.name },
                    callback(r) {
                        frappe.show_alert({ message: __('Investigatore digitale: genero le domande per ogni documento; le trovi nelle attivita del caso.'), indicator: 'blue' }, 8);
                    }
                });
            }, __('Intelligence'));

            frm.add_custom_button(__('Verifica doppia cessione'), () => {
                frappe.call({
                    method: 'thanatos_intel.ai.cession_recon.detect_double_cession_async',
                    args: { case: frm.doc.name },
                    callback(r) {
                        frappe.show_alert({ message: __('Analisi cessioni avviata: l\'esito comparira nelle attivita del caso e riceverai una notifica.'), indicator: 'blue' }, 8);
                    }
                });
            }, __('Intelligence'));
        }

        // ---- Comunicazioni al cliente (template email, dentro Thanatos) ----
        if (!frm.is_new()) {
            frm.add_custom_button(__('Email al cliente'), () => {
                frappe.call('thanatos_intel.integrations.client_comms.list_templates').then(r => {
                    const tpls = r.message || [];
                    if (!tpls.length) { frappe.msgprint(__('Nessun template disponibile. Crea un Email Template con nome "Thanatos - ...".')); return; }
                    const d = new frappe.ui.Dialog({
                        title: __('Email al cliente'),
                        fields: [{ fieldname: 'template', fieldtype: 'Select', label: __('Template'), reqd: 1, options: tpls.join('\n') }],
                        primary_action_label: __('Invia'),
                        primary_action(v) {
                            d.hide();
                            frappe.call({
                                method: 'thanatos_intel.integrations.client_comms.send_to_client',
                                args: { case: frm.doc.name, template: v.template },
                                freeze: true, freeze_message: __('Invio in corso...'),
                                callback(r2) {
                                    const m = r2.message || {};
                                    if (m.ok) frappe.show_alert({ message: __('Email accodata a {0}', [m.to]), indicator: 'green' }, 6);
                                }
                            });
                        }
                    });
                    d.show();
                });
            }, __('Comunicazioni'));
        }

        // ---- MMOS AI: ingest documenti (OCR + estrazione AI + reperto) ----
        if (!frm.is_new()) {
            frm.add_custom_button(__('Ingest documento'), () => {
                const files = (frm.get_files ? frm.get_files() : []);
                if (!files.length) { frappe.msgprint(__('Nessun allegato sul caso. Carica prima un documento.')); return; }
                const d = new frappe.ui.Dialog({
                    title: __('MMOS AI - Ingest documento'),
                    fields: [
                        { fieldname: 'file_url', fieldtype: 'Select', label: __('Documento'), reqd: 1,
                          options: files.map(f => f.file_url).join('\n') },
                        { fieldname: 'document_type', fieldtype: 'Select', label: __('Tipo'), default: 'generic',
                          options: ['generic','passport','id_card','company_doc','financial_doc','contract'].join('\n') }
                    ],
                    primary_action_label: __('Analizza con AI'),
                    primary_action(v) {
                        d.hide();
                        frappe.call({
                            method: 'thanatos_intel.ai.doc_ingest.ingest_document',
                            args: { file_url: v.file_url, investigation_case: frm.doc.name, document_type: v.document_type },
                            freeze: true, freeze_message: __('OCR + estrazione MMOS AI...'),
                            callback(r) {
                                const m = r.message || {};
                                const ex = m.extracted || {};
                                const ents = (ex.entities || []).map(e => e.name + (e.role ? ' ('+e.role+')' : '')).join(', ');
                                const flags = (ex.risk_flags || []).join('; ');
                                frappe.msgprint({
                                    title: __('Ingest completato'),
                                    indicator: flags ? 'orange' : 'green',
                                    message: '<b>Sintesi:</b> ' + frappe.utils.escape_html(ex.summary || '-') + '<br>' +
                                             '<b>Entita:</b> ' + frappe.utils.escape_html(ents || '-') + '<br>' +
                                             (flags ? '<b style="color:#c0392b">Red flag:</b> ' + frappe.utils.escape_html(flags) + '<br>' : '') +
                                             '<b>Reperto:</b> ' + (m.evidence || '-') + ' . OCR ' + (m.ocr ? m.ocr.provider : '-') +
                                             (m.ai_available ? '' : '<br><i>AI non raggiungibile - solo OCR</i>')
                                });
                                frm.reload_doc();
                            }
                        });
                    }
                });
                d.show();
            }, __('MMOS AI'));
        }

        // ---- Report: genera per tema, PDF in Drive con tag cliente, firma MMOS Sign ----
        if (!frm.is_new()) {
            const kinds = {
                'Report KYB': 'kyb', 'Report Blockchain': 'blockchain',
                'Report OSINT': 'osint', 'Piano di Recupero': 'recovery', 'Dossier Completo': 'full'
            };
            Object.keys(kinds).forEach((label) => {
                frm.add_custom_button(__(label), () => {
                    frappe.call({
                        method: 'thanatos_intel.reporting.case_reports.generate_case_report',
                        args: { case_name: frm.doc.name, kind: kinds[label] },
                        freeze: true, freeze_message: __('Generazione report…'),
                        callback(r) {
                            const m = r.message || {};
                            if (m.file_url) {
                                frappe.show_alert({ message: __('Report pronto ({0} sezioni){1}', [m.sections, m.drive ? ' — in Drive' : '']), indicator: 'green' });
                                window.open(m.file_url, '_blank');
                                frm.reload_doc();
                            }
                        }
                    });
                }, __('Report'));
            });

            frm.add_custom_button(__('Invia per firma (MMOS Sign)'), () => {
                const files = (frm.get_files ? frm.get_files() : []).filter(f => (f.file_url || '').toLowerCase().endsWith('.pdf'));
                const d = new frappe.ui.Dialog({
                    title: __('Invia report per firma'),
                    fields: [
                        { fieldname: 'file_url', fieldtype: 'Select', label: __('PDF da firmare'), reqd: 1,
                          options: files.map(f => f.file_url).join('\n') },
                        { fieldname: 'signer_email', fieldtype: 'Data', label: __('Email firmatario') },
                        { fieldname: 'signer_name', fieldtype: 'Data', label: __('Nome firmatario') }
                    ],
                    primary_action_label: __('Invia'),
                    primary_action(v) {
                        frappe.call({
                            method: 'thanatos_intel.reporting.case_reports.send_report_to_mmos_sign',
                            args: { file_url: v.file_url, case_name: frm.doc.name, signer_email: v.signer_email, signer_name: v.signer_name },
                            freeze: true, freeze_message: __('Invio in firma…'),
                            callback(r) {
                                if (r.message && r.message.ok) {
                                    frappe.show_alert({ message: __('Inviato per firma'), indicator: 'green' });
                                    d.hide();
                                    if (r.message.signing_url) window.open(r.message.signing_url, '_blank');
                                }
                            }
                        });
                    }
                });
                d.show();
            }, __('Report'));
        }
    },
    after_save(frm) {
        ThanatosPipeline.render(frm, 'get_case_pipeline');
    }
});


function thanatos_set_monitor_operators(frm) {
    // Popola la dropdown 'Operatore' dei destinatari alert con gli operatori
    // assegnati al caso (tecnico, CTU, legale, ...). Il valore conserva l'email
    // cosi' il backend la estrae direttamente.
    const grid = frm.fields_dict.monitor_recipients && frm.fields_dict.monitor_recipients.grid;
    if (!grid) return;
    const opts = [''];
    (frm.doc.case_assignments || []).forEach(a => {
        if (!a.assignee_email) return;
        const role = a.role_description ? ` ${a.role_description}` : '';
        opts.push(`${a.assignee || a.assignee_type} (${a.assignee_type}${role}) — ${a.assignee_email}`);
    });
    grid.update_docfield_property('operator', 'options', opts.join('\n'));
    grid.refresh();
}

frappe.ui.form.on('Case Assignment', {
    assignee_email(frm) { thanatos_set_monitor_operators(frm); },
    case_assignments_remove(frm) { thanatos_set_monitor_operators(frm); }
});


// ── Percorso guidato passo-passo (wizard sul Blueprint) ──────────────────────
frappe.ui.form.on('Investigation Case', {
	refresh(frm) {
		if (frm.is_new()) return;
		tcw_inject_css();
		if (!frm.dashboard || !frm.dashboard.add_section) return;
		frm.dashboard.add_section(
			'<div class="tcw-guide" id="tcw-guide"><div class="tcw-mut">Carico percorso guidato…</div></div>',
			__('Percorso guidato'));
		const $w = (frm.dashboard.wrapper && frm.dashboard.wrapper.find) ? frm.dashboard.wrapper.find('#tcw-guide')
		         : (frm.dashboard.parent ? $(frm.dashboard.parent).find('#tcw-guide') : null);
		if ($w && $w.length) tcw_load(frm, $w);
	},
});

function tcw_load(frm, $c) {
	frappe.call('thanatos_intel.workflow.api.board', { case_name: frm.doc.name })
		.then(r => tcw_render(frm, $c, r.message || {}))
		.catch(() => $c.html('<div class="tcw-mut">Percorso non disponibile.</div>'));
}

function tcw_render(frm, $c, b) {
	const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));

	if (!b.has_workflow) {
		if (frm.doc.blueprint) {
			$c.html('<div class="tcw-row"><span class="tcw-mut">Percorso non ancora avviato.</span> </div>');
			$('<button class="btn btn-xs btn-primary">▶ Avvia percorso guidato</button>')
				.appendTo($c.find('.tcw-row')).on('click', () => {
					frappe.call('thanatos_intel.workflow.engine.start', { case_name: frm.doc.name })
						.then(() => { frappe.show_alert({ message: 'Percorso avviato', indicator: 'green' }); frm.reload_doc(); });
				});
		} else {
			$c.html('<div class="tcw-mut">Nessun Blueprint impostato. Scegli un <b>Blueprint</b> per attivare il percorso guidato passo-passo.</div>');
		}
		return;
	}

	let h = `<div class="tcw-prog">
		<div class="tcw-bar"><div class="tcw-bar-f" style="width:${b.pct || 0}%"></div></div>
		<span class="tcw-pct">${b.done}/${b.total} · ${b.pct || 0}%</span>
		<button class="btn btn-xs btn-default tcw-ai">🤖 Cosa faccio ora?</button></div>`;
	h += '<div class="tcw-steps">';
	(b.steps || []).forEach(s => {
		const ic = s.status === 'done' ? '✓' : (s.status === 'current' ? '▶' : '○');
		const actor = s.actor === 'client' ? 'Cliente' : 'Operatore';
		h += `<div class="tcw-step tcw-${s.status}">
			<span class="tcw-ic">${ic}</span>
			<span class="tcw-lbl">${esc(s.label)}</span>
			<span class="tcw-chip">${actor}</span>
			${s.mode === 'GATE' ? '<span class="tcw-chip tcw-gate">GATE</span>' : ''}
			${s.status === 'current' ? tcw_action_btn(s) : ''}</div>`;
	});
	h += '</div><div class="tcw-aiout" style="display:none"></div>';
	$c.html(h);

	$c.find('[data-complete]').on('click', function () {
		const seq = $(this).data('complete');
		frappe.prompt([{ fieldtype: 'Small Text', label: 'Nota (opzionale)', fieldname: 'note' }], (v) => {
			frappe.call('thanatos_intel.workflow.api.complete_gate',
				{ case_name: frm.doc.name, seq: seq, note: v.note || '' })
				.then(() => { frappe.show_alert({ message: 'Step completato', indicator: 'green' }); frm.reload_doc(); });
		}, 'Completa step', 'Conferma');
	});

	$c.find('.tcw-ai').on('click', function () {
		const $o = $c.find('.tcw-aiout').show().html('<div class="tcw-mut">🤖 Sto pensando…</div>');
		frappe.call('thanatos_intel.workflow.ai_concierge.suggest_next', { case_name: frm.doc.name })
			.then(r => {
				const m = r.message || {};
				$o.html(m.ok
					? '<div class="tcw-ai-card">🤖 ' + esc(m.suggestion).replace(/\n/g, '<br>') + '</div>'
					: '<div class="tcw-mut">' + esc(m.error || 'AI non disponibile al momento.') + '</div>');
			})
			.catch(() => $o.html('<div class="tcw-mut">AI non disponibile.</div>'));
	});
}

function tcw_action_btn(s) {
	if (s.actor === 'client') return '<span class="tcw-wait">⏳ In attesa del cliente</span>';
	return `<button class="btn btn-xs btn-primary" data-complete="${s.seq}">✓ Completa</button>`;
}

function tcw_inject_css() {
	if (document.getElementById('tcw-css')) return;
	const css = `
	.tcw-guide{padding:4px 2px}
	.tcw-mut{color:var(--text-muted);font-size:13px;padding:4px 2px}
	.tcw-row{display:flex;align-items:center;gap:10px;padding:4px 2px}
	.tcw-prog{display:flex;align-items:center;gap:12px;margin-bottom:12px}
	.tcw-bar{flex:1;height:8px;background:var(--bg-color);border-radius:4px;overflow:hidden;border:1px solid var(--border-color)}
	.tcw-bar-f{height:100%;background:#C8A96E;transition:width .3s}
	.tcw-pct{font-size:12px;color:var(--text-muted);white-space:nowrap}
	.tcw-steps{display:flex;flex-direction:column;gap:4px}
	.tcw-step{display:flex;align-items:center;gap:10px;padding:9px 12px;border:1px solid var(--border-color);border-radius:6px;background:var(--card-bg)}
	.tcw-step.tcw-current{border-color:#C8A96E;box-shadow:inset 3px 0 0 #C8A96E;background:var(--bg-color)}
	.tcw-step.tcw-done{opacity:.6}
	.tcw-ic{width:20px;text-align:center;font-weight:700;color:#C8A96E}
	.tcw-done .tcw-ic{color:#29CD42}
	.tcw-lbl{flex:1;font-size:13px;color:var(--text-color)}
	.tcw-chip{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);border:1px solid var(--border-color);padding:2px 7px;border-radius:10px;white-space:nowrap}
	.tcw-gate{color:#ECAD4B;border-color:#ECAD4B}
	.tcw-wait{font-size:11px;color:#ECAD4B;white-space:nowrap}
	.tcw-aiout{margin-top:10px}
	.tcw-ai-card{background:var(--card-bg);border:1px solid #C8A96E;border-radius:8px;padding:12px;font-size:13px;color:var(--text-color);line-height:1.5}
	`;
	$('<style id="tcw-css">').text(css).appendTo(document.head);
}

// --- Genera fattura ARES (azione one-click) ---
frappe.ui.form.on("Investigation Case", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Genera fattura ARES"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Genera fattura ARES"),
                fields: [
                    {fieldname: "customer", fieldtype: "Link", options: "Customer",
                     label: __("Cliente (fatturazione)"), reqd: 1},
                    {fieldname: "amount", fieldtype: "Currency", label: __("Imponibile (EUR)"), reqd: 1},
                    {fieldname: "description", fieldtype: "Small Text", label: __("Descrizione riga"),
                     default: "Servizi di investigazione - " + (frm.doc.case_title || frm.doc.name)},
                ],
                primary_action_label: __("Crea bozza"),
                primary_action(values) {
                    frappe.call({
                        method: "thanatos_intel.billing.ares_invoice.create_ares_invoice",
                        args: {case: frm.doc.name, customer: values.customer,
                               amount: values.amount, description: values.description},
                        freeze: true,
                        freeze_message: __("Creazione fattura ARES..."),
                        callback(r) {
                            if (r.message) {
                                d.hide();
                                frappe.show_alert({message: __("Fattura {0} creata", [r.message]),
                                                   indicator: "green"});
                                frappe.set_route("Form", "Sales Invoice", r.message);
                            }
                        },
                    });
                },
            });
            d.show();
        }, __("Azioni"));
    },
});

// ── Pannello Avanzamento investigazione (checklist auto dallo stato reale) ──
frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        if (frm.is_new() || !frm.fields_dict.progress_panel) return;
        frappe.call({
            method: 'thanatos_intel.ai.case_orchestrator.case_progress',
            args: { case: frm.doc.name, record: 0 },
            callback(r) {
                const m = r.message; if (!m) return;
                const color = m.pct >= 80 ? '#27ae60' : (m.pct >= 50 ? '#e67e22' : '#c0392b');
                let h = '<div style="padding:10px 14px;border:1px solid #e0d7c0;border-radius:10px;background:#faf8f2;margin:6px 0">'
                    + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
                    + '<span style="font-weight:700;color:#0D1B3E">📋 Avanzamento investigazione</span>'
                    + '<span style="font-weight:700;color:' + color + '">' + m.done + '/' + m.total + ' · ' + m.pct + '%</span></div>'
                    + '<div style="height:9px;background:#eee;border-radius:5px;overflow:hidden;margin-bottom:10px"><div style="height:9px;width:' + m.pct + '%;background:' + color + '"></div></div>'
                    + '<div style="column-count:2;column-gap:24px;font-size:13px;line-height:1.7">';
                (m.items || []).forEach(function (it) {
                    h += '<div>' + (it.done ? '✅' : '⬜') + ' ' + frappe.utils.escape_html(it.label)
                        + (it.extra ? ' <span style="color:#999">— ' + frappe.utils.escape_html(it.extra) + '</span>' : '') + '</div>';
                });
                h += '</div>';
                const ext = (m.todo_external || []).filter(function (t) { return !t.done; }).map(function (t) { return frappe.utils.escape_html(t.label); });
                if (ext.length) h += '<div style="margin-top:8px;font-size:12.5px;color:#a33"><b>Da fare (sblocca la delega del cliente):</b> ' + ext.join(' · ') + '</div>';
                h += '</div>';
                frm.fields_dict.progress_panel.$wrapper.html(h);
            }
        });
    }
});

// ── Revisione guidata documenti (avanti/indietro + domande) + dossier/proforma ──
function _thanatosDocWalkthrough(frm) {
    frappe.call({
        method: 'thanatos_intel.ai.case_orchestrator.document_walkthrough',
        args: { case: frm.doc.name },
        freeze: true, freeze_message: 'Carico documenti...',
        callback(r) {
            const data = r.message;
            if (!data || !data.total) { frappe.msgprint(__('Nessun documento sul caso.')); return; }
            let idx = 0;
            const dlg = new frappe.ui.Dialog({ title: __('Revisione guidata documenti'), size: 'large',
                fields: [{ fieldtype: 'HTML', fieldname: 'body' }] });
            const COL = { 'Autentico': '#27ae60', 'Dubbio': '#e67e22', 'Manomesso': '#c0392b',
                'Contraffatto': '#c0392b', 'N/D': '#999', 'Non determinabile': '#999' };
            function render() {
                const dn = data.docs[idx];
                const ac = COL[dn.authenticity] || '#999';
                let h = '<div style="font-size:13px">'
                    + '<div style="display:flex;justify-content:space-between;align-items:center">'
                    + '<b>Documento ' + dn.idx + '/' + data.total + '</b>'
                    + '<span style="background:' + ac + ';color:#fff;padding:2px 9px;border-radius:10px;font-size:11px">' + dn.authenticity + '</span></div>'
                    + '<h4 style="margin:8px 0 4px">' + frappe.utils.escape_html(dn.name) + '</h4>'
                    + '<p style="color:#444;line-height:1.5">' + frappe.utils.escape_html(dn.summary || '—') + '</p>'
                    + '<div style="font-size:11px;color:#888">SHA-256: ' + (dn.hash || '—') + '</div>'
                    + '<hr><b>Domande investigative</b><ol style="margin-top:4px;padding-left:18px">';
                (dn.questions || []).forEach(function (q) {
                    h += '<li style="margin-bottom:5px">' + frappe.utils.escape_html(q.replace(/^\s*\d+\.\s*/, '')) + '</li>';
                });
                if (!(dn.questions || []).length) h += '<li style="color:#888">(usa il bottone "Domande investigative" per generarle)</li>';
                h += '</ol><div style="margin-top:12px;display:flex;gap:8px;align-items:center">'
                    + '<button class="btn btn-default btn-sm" id="wt-prev">&larr; ' + __('Indietro') + '</button>'
                    + '<button class="btn btn-default btn-sm" id="wt-next">' + __('Avanti') + ' &rarr;</button>'
                    + (dn.file_url ? '<a class="btn btn-primary btn-sm" href="' + dn.file_url + '" target="_blank">' + __('Apri documento') + '</a>' : '')
                    + '</div></div>';
                dlg.fields_dict.body.$wrapper.html(h);
                dlg.$wrapper.find('#wt-prev').prop('disabled', idx === 0).off('click').on('click', function () { if (idx > 0) { idx--; render(); } });
                dlg.$wrapper.find('#wt-next').prop('disabled', idx === data.total - 1).off('click').on('click', function () { if (idx < data.total - 1) { idx++; render(); } });
            }
            render(); dlg.show();
        }
    });
}

frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__('🔎 Revisione guidata documenti'), () => _thanatosDocWalkthrough(frm), __('Intelligence'));
        frm.add_custom_button(__('Dossier cliente (DOCX)'), () => {
            frappe.call({ method: 'thanatos_intel.reporting.dossier_cliente.genera_dossier', args: { case: frm.doc.name },
                freeze: true, freeze_message: __('Genero il dossier...'),
                callback(r) { const m = r.message || {}; if (m.file_url) { frappe.show_alert({ message: __('Dossier DOCX generato.'), indicator: 'green' }, 6); window.open(m.file_url, '_blank'); } frm.reload_doc(); } });
        }, __('File'));
        frm.add_custom_button(__('Proforma / Preventivo'), () => {
            const d = new frappe.ui.Dialog({ title: __('Proforma'), fields: [
                { fieldname: 'hours_senior', fieldtype: 'Int', label: 'Ore senior', default: 40 },
                { fieldname: 'hours_analyst', fieldtype: 'Int', label: 'Ore analista', default: 30 },
                { fieldname: 'markup', fieldtype: 'Percent', label: 'Markup costi vivi (%)', default: 50 },
                { fieldname: 'sconto', fieldtype: 'Percent', label: 'Sconto (%)', default: 0 } ],
                primary_action_label: __('Genera'),
                primary_action(v) { d.hide();
                    frappe.call({ method: 'thanatos_intel.billing.proforma_cliente.genera_proforma',
                        args: { case: frm.doc.name, hours_senior: v.hours_senior, hours_analyst: v.hours_analyst, markup: (v.markup || 50) / 100, sconto: v.sconto || 0 },
                        freeze: true, freeze_message: __('Genero la proforma...'),
                        callback(r) { const m = r.message || {}; if (m.file_url) { frappe.show_alert({ message: __('Proforma € {0} generata.', [Math.round(m.imponibile)]), indicator: 'green' }, 7); window.open(m.file_url, '_blank'); } frm.reload_doc(); } });
                } });
            d.show();
        }, __('File'));
    }
});

// ── Assistente AI del caso (chat che esegue gli strumenti) ──
frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        if (frm.is_new() || !frm.fields_dict.ai_chat_panel) return;
        const $w = frm.fields_dict.ai_chat_panel.$wrapper;
        if ($w.data('built')) return; $w.data('built', true);
        const chips = ['avanzamento', 'valuta assicurazione', 'genera dossier', 'proforma', 'doppia cessione', 'domande', 'analisi completa'];
        $w.html(
            '<div style="border:1px solid #e0d7c0;border-radius:10px;background:#fff;overflow:hidden">'
            + '<div style="background:#0D1B3E;color:#C8A96E;font-weight:700;padding:8px 12px">🤖 Assistente AI del caso</div>'
            + '<div id="aic-msgs" style="height:240px;overflow-y:auto;padding:10px 12px;font-size:13px;background:#faf8f2"></div>'
            + '<div style="padding:6px 10px;border-top:1px solid #eee">'
            + '<div id="aic-chips" style="margin-bottom:6px"></div>'
            + '<div style="display:flex;gap:6px"><input id="aic-in" class="form-control input-sm" placeholder="Chiedi o comanda… (es. valuta assicurazione, verifica camerale 03293360966)" style="flex:1">'
            + '<button id="aic-send" class="btn btn-primary btn-sm">Invia</button></div></div></div>');
        const $msgs = $w.find('#aic-msgs');
        function add(who, text) {
            const me = who === 'me';
            $msgs.append('<div style="margin-bottom:8px;text-align:' + (me ? 'right' : 'left') + '">'
                + '<span style="display:inline-block;max-width:85%;padding:6px 10px;border-radius:10px;white-space:pre-wrap;'
                + (me ? 'background:#0D1B3E;color:#fff' : 'background:#fff;border:1px solid #e0d7c0') + '">'
                + frappe.utils.escape_html(text) + '</span></div>');
            $msgs.scrollTop($msgs[0].scrollHeight);
        }
        function send(text) {
            if (!text) return; add('me', text); $w.find('#aic-in').val('');
            add('ai', '…');
            frappe.call({ method: 'thanatos_intel.ai.case_assistant.case_ai_chat', args: { case: frm.doc.name, message: text },
                callback(r) {
                    $msgs.find('div:last').remove();
                    const m = r.message || {}; add('ai', m.reply || '(nessuna risposta)');
                    if (m.action) setTimeout(() => frm.reload_doc(), 1200);
                } });
        }
        chips.forEach(ch => { $w.find('#aic-chips').append('<button class="btn btn-xs btn-default" style="margin:2px">' + ch + '</button>'); });
        $w.find('#aic-chips button').on('click', function () { send($(this).text()); });
        $w.find('#aic-send').on('click', () => send($w.find('#aic-in').val().trim()));
        $w.find('#aic-in').on('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); send($w.find('#aic-in').val().trim()); } });
        add('ai', 'Ciao. Sono l’assistente del caso: posso eseguire gli strumenti (dossier, proforma, doppia cessione, domande, screening, verifica camerale, valutazione assicurativa, analisi completa) o rispondere alle tue domande. Scrivi un comando o usa i tasti rapidi.');
    }
});
