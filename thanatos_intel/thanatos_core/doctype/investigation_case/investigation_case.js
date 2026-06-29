frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
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

        if (!frm.is_new()) {
            frm.add_custom_button(__("Tracciamento visuale"), () => {
                frappe.call({
                    method: "thanatos_intel.osint.free_sources.case_tracing_links",
                    args: { case: frm.doc.name },
                    freeze: true, freeze_message: __("Raccolta wallet del caso…"),
                    callback(r) {
                        const m = r.message || {};
                        if (m.error) { frappe.msgprint(__("Errore: {0}", [m.error])); return; }
                        if (!m.count) { frappe.msgprint(__("Nessun wallet collegato a questo caso.")); return; }
                        let html = "";
                        (m.wallets || []).forEach(w => {
                            const btns = Object.keys(w.links).map(k =>
                                `<a href="${w.links[k]}" target="_blank" rel="noopener" class="btn btn-default btn-sm" style="margin:2px">${k} ↗</a>`
                            ).join(" ");
                            html += `<div style="margin-bottom:12px"><div style="font-family:monospace;font-size:12px;word-break:break-all"><b>${w.chain.toUpperCase()}</b> · ${w.address}${w.role ? " · "+w.role : ""}</div><div style="margin-top:6px">${btns}</div></div>`;
                        });
                        frappe.msgprint({ title: __("Tracciamento visuale · {0} wallet", [m.count]), message: html, wide: true });
                    }
                });
            }, __("Intelligence"));
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

            frm.add_custom_button(__('👥 Soci & Titolari effettivi (UBO)'), () => {
                const d = new frappe.ui.Dialog({
                    title: __('Soci e titolari effettivi'),
                    fields: [{ fieldname: 'piva', fieldtype: 'Data', label: 'Partita IVA', reqd: 1 }],
                    primary_action_label: __('Cerca'),
                    primary_action(v) {
                        d.hide();
                        frappe.call({
                            method: 'thanatos_intel.osint.openapi_client.soci_titolari',
                            args: { piva: v.piva, investigation_case: frm.doc.name },
                            freeze: true, freeze_message: __('Interrogazione openapi…'),
                            callback(r) {
                                const m = r.message || {};
                                const soci = (m.soci||[]).map(s => frappe.utils.escape_html(s.nome) + ' (' + s.quota + '%)').join('; ') || '—';
                                const ubo = (m.ubo||[]).map(u => frappe.utils.escape_html(u.nome) + ' [' + (u.cf||'') + ']').join('; ') || '—';
                                frappe.msgprint({ title: __('Soci & UBO'), indicator: 'blue',
                                    message: '<b>P.IVA:</b> ' + (m.piva||'-') + '<br><b>Soci:</b> ' + soci + '<br><b>Titolari effettivi (UBO):</b> ' + ubo });
                                frm.reload_doc();
                            }
                        });
                    }
                });
                d.show();
            }, __('Intelligence'));

            frm.add_custom_button(__('🛂 Screening KYC (PEP/Sanzioni)'), () => {
                const d = new frappe.ui.Dialog({
                    title: __('Screening reputazionale KYC'),
                    fields: [
                        { fieldname: 'query', fieldtype: 'Data', label: 'Nominativo / Ragione sociale', reqd: 1 },
                        { fieldname: 'mode', fieldtype: 'Select', label: 'Tipo', default: 'pep',
                          options: 'pep\nsanction_list\nadverse_media\nfull' }
                    ],
                    primary_action_label: __('Esegui'),
                    primary_action(v) {
                        d.hide();
                        frappe.call({
                            method: 'thanatos_intel.osint.openapi_client.screening_kyc',
                            args: { query: v.query, mode: v.mode, investigation_case: frm.doc.name },
                            freeze: true, freeze_message: __('Screening in corso…'),
                            callback(r) {
                                const m = r.message || {};
                                if (m.error) { frappe.msgprint({ title: __('Screening'), indicator: 'red', message: m.error }); return; }
                                const hl = (m.hits||[]).map(h => frappe.utils.escape_html(h.nome||'') + ' (' + (h.tipo||'') + ')').join('<br>') || 'nessun match';
                                frappe.msgprint({ title: __('Screening ' + v.mode), indicator: (m.match ? 'orange' : 'green'),
                                    message: '<b>«' + frappe.utils.escape_html(v.query) + '»</b> — ' + (m.match||0) + ' match<br>' + hl });
                                frm.reload_doc();
                            }
                        });
                    }
                });
                d.show();
            }, __('Intelligence'));

            frm.add_custom_button(__('🧰 Strumenti dati (openapi)'), () => {
                frappe.call({
                    method: 'thanatos_intel.osint.openapi_client.strumenti',
                    callback(r) {
                        const s = r.message || {};
                        let msg = '<p><b>' + (s.totale_servizi||0) + ' servizi</b> · ambiente <b>' + (s.ambiente||'') + '</b> · '
                            + (s.connesso ? '<span style="color:#27ae60">connesso</span>' : '<span style="color:#c0392b">non connesso</span>') + '</p>';
                        (s.famiglie||[]).forEach(f => {
                            msg += '<p style="margin:6px 0"><b>' + frappe.utils.escape_html(f.famiglia) + '</b> '
                                + '<span style="color:#888">(' + f.pattern + ', ' + f.fascia + ')</span><br>'
                                + '<span style="color:#555">' + frappe.utils.escape_html((f.strumenti||[]).join(' · ')) + '</span><br>'
                                + '<i style="color:#888">' + frappe.utils.escape_html(f.uso||'') + '</i></p>';
                        });
                        frappe.msgprint({ title: __('Strumenti dati a disposizione'), message: msg, wide: true });
                    }
                });
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
        if (window.ThanatosCockpit) ThanatosCockpit.render(frm);
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


// ── COCKPIT del caso (unico): fasi + stepper sul motore + prossima azione ────
// Sostituisce i 3 avanzamenti sovrapposti (Pipeline pratica, Percorso guidato,
// Avanzamento investigazione). Reso nel campo progress_panel, in cima alla form.
window.ThanatosCockpit = {
	PHASES: [
		{ key: 'intake', label: '1 · Intake', kw: ['mandat', 'incaric', 'kyc', 'kyb', 'client', 'apri', 'pratica', 'identific', 'accett', 'triage'] },
		{ key: 'parti', label: '2 · Parti', kw: ['document', 'parti', 'entità', 'entita', 'ingest', 'raccolt', 'anagrafic', 'autenticit'] },
		{ key: 'verifiche', label: '3 · Verifiche', kw: ['verifica', 'visura', 'camerale', 'due diligence', 'screening', 'soci', 'ubo', 'sanzion', 'blacklist', 'cessionari', 'catena', 'assever', 'congru', 'esistenz', 'vies', 'kyc/kyb'] },
		{ key: 'analisi', label: '4 · Analisi', kw: ['analisi', 'doppia cession', 'riconcil', 'contratt', 'escrow', 'rischio', 'parere', 'legale', 'quantific', 'antifrode'] },
		{ key: 'esito', label: '5 · Esito', kw: ['report', 'dossier', 'fascicolo', 'verdetto', 'go / no', 'go/no', 'chiusur', 'fattura', 'consegna'] }
	],
	phaseIndexOf(label, idx, total) {
		const l = (label || '').toLowerCase();
		for (let i = 0; i < this.PHASES.length; i++) {
			if (this.PHASES[i].kw.some(k => l.indexOf(k) >= 0)) return i;
		}
		return Math.min(4, Math.floor(idx * 5 / Math.max(1, total)));
	},
	render(frm) {
		if (frm.is_new() || !frm.fields_dict.cockpit_panel) return;
		this.injectCss();
		const $w = frm.fields_dict.cockpit_panel.$wrapper;
		$w.html('<div class="ck-mut">Carico cockpit…</div>');
		const self = this;
		frappe.call('thanatos_intel.workflow.api.board', { case_name: frm.doc.name })
			.then(r => self.draw(frm, $w, r.message || {}))
			.catch(() => $w.html('<div class="ck-mut">Cockpit non disponibile.</div>'));
	},
	draw(frm, $w, b) {
		const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
		if (!b.has_workflow) {
			if (frm.doc.blueprint) {
				$w.html('<div class="ck-card"><div class="ck-row"><span class="ck-mut">Percorso non ancora avviato.</span> '
					+ '<button class="btn btn-sm btn-primary ck-start">▶ Avvia pratica</button></div></div>');
				$w.find('.ck-start').on('click', () => frappe.call('thanatos_intel.workflow.engine.start',
					{ case_name: frm.doc.name }).then(() => { frappe.show_alert({ message: 'Pratica avviata', indicator: 'green' }); frm.reload_doc(); }));
			} else {
				$w.html('<div class="ck-card"><span class="ck-mut">Nessun <b>Blueprint di servizio</b> selezionato: scegline uno per avviare la pratica guidata passo-passo.</span> '
					+ '<button class="btn btn-sm btn-primary ck-pick-bp" style="margin-left:8px">' + __('Scegli Blueprint') + '</button></div>');
				$w.find('.ck-pick-bp').on('click', () => {
					const d = new frappe.ui.Dialog({
						title: __('Scegli Blueprint di servizio'),
						fields: [{ fieldname: 'bp', fieldtype: 'Link', options: 'Service Blueprint', label: __('Blueprint'), reqd: 1 }],
						primary_action_label: __('Imposta'),
						primary_action(v) {
							d.hide();
							frm.set_value('blueprint', v.bp);
							frm.save().then(() => { frappe.show_alert({ message: __('Blueprint impostato'), indicator: 'green' }); frm.reload_doc(); });
						}
					});
					d.show();
				});
			}
			return;
		}
		const steps = b.steps || [];
		const total = steps.length;
		const allDone = total > 0 && b.done >= total;
		const notStarted = !b.active && b.done === 0 && !steps.some(s => s.status === 'current');
		// fase di ogni step + fase corrente
		let curPhase = 0;
		steps.forEach((s, i) => { s._ph = this.phaseIndexOf(s.label, i, total); if (s.status === 'current') curPhase = s._ph; });
		const cur = steps.find(s => s.status === 'current');
		if (allDone) curPhase = 4;
		// stato per fase
		const phState = this.PHASES.map((p, pi) => {
			const ps = steps.filter(s => s._ph === pi);
			if (!ps.length) return pi < curPhase ? 'done' : (pi === curPhase ? 'current' : 'todo');
			if (ps.every(s => s.status === 'done')) return 'done';
			if (pi === curPhase || ps.some(s => s.status === 'current')) return 'current';
			return pi < curPhase ? 'done' : 'todo';
		});

		// ── fascia 5 fasi ──
		let h = '<div class="ck-card">';
		h += '<div class="ck-ribbon">';
		this.PHASES.forEach((p, pi) => {
			h += `<div class="ck-seg ck-${phState[pi]}"><span class="ck-seg-dot"></span><span class="ck-seg-lbl">${esc(p.label)}</span></div>`;
		});
		h += '</div>';
		// barra unica
		h += `<div class="ck-prog"><div class="ck-bar"><div class="ck-bar-f" style="width:${b.pct || 0}%"></div></div>`
			+ `<span class="ck-pct">${b.done}/${b.total} step · ${b.pct || 0}%</span></div>`;

		// ── prossima azione (step corrente) ──
		if (cur) {
			const wait = cur.actor === 'client';
			h += `<div class="ck-next"><div class="ck-next-h">Prossima azione · ${esc(this.PHASES[cur._ph].label)}</div>`
				+ `<div class="ck-next-b"><span class="ck-next-lbl">${esc(cur.label)}</span>`
				+ `<span class="ck-chip">${wait ? 'Cliente' : 'Operatore'}</span>`
				+ (cur.mode === 'GATE' ? '<span class="ck-chip ck-gate">GATE</span>' : '')
				+ '</div><div class="ck-next-act">'
				+ (wait ? '<span class="ck-wait">⏳ In attesa del cliente</span>'
					: `<button class="btn btn-sm btn-primary ck-done" data-seq="${cur.seq}">✓ Completa step</button>`)
				+ ` <button class="btn btn-sm btn-default ck-ai">🤖 Cosa faccio ora?</button></div>`
				+ '<div class="ck-aiout" style="display:none"></div></div>';
		} else if (allDone) {
			h += '<div class="ck-next ck-done-all">✓ Tutti gli step completati.</div>';
		} else if (notStarted) {
			h += '<div class="ck-next"><div class="ck-next-h">Prossima azione</div>'
				+ '<div class="ck-next-b"><span class="ck-next-lbl">Pratica non ancora avviata</span></div>'
				+ '<div class="ck-next-act"><button class="btn btn-sm btn-primary ck-start">▶ Avvia pratica</button>'
				+ ' <button class="btn btn-sm btn-default ck-ai">🤖 Cosa faccio ora?</button></div>'
				+ '<div class="ck-aiout" style="display:none"></div></div>';
		} else {
			h += '<div class="ck-next"><div class="ck-next-h">Prossima azione</div>'
				+ '<div class="ck-next-act"><button class="btn btn-sm btn-default ck-ai">🤖 Cosa faccio ora?</button></div>'
				+ '<div class="ck-aiout" style="display:none"></div></div>';
		}

		// ── elenco completo (collassato) ──
		h += '<details class="ck-all"><summary>Tutti gli step</summary><div class="ck-steps">';
		steps.forEach(s => {
			const ic = s.status === 'done' ? '✓' : (s.status === 'current' ? '▶' : '○');
			h += `<div class="ck-step ck-${s.status}"><span class="ck-ic">${ic}</span><span class="ck-lbl">${esc(s.label)}</span>`
				+ `<span class="ck-chip">${s.actor === 'client' ? 'Cliente' : 'Operatore'}</span>`
				+ (s.mode === 'GATE' ? '<span class="ck-chip ck-gate">GATE</span>' : '') + '</div>';
		});
		h += '</div></details></div>';
		$w.html(h);

		$w.find('.ck-start').on('click', () => frappe.call('thanatos_intel.workflow.engine.start',
			{ case_name: frm.doc.name }).then(() => { frappe.show_alert({ message: 'Pratica avviata', indicator: 'green' }); frm.reload_doc(); }));
		$w.find('.ck-done').on('click', function () {
			const seq = $(this).data('seq');
			frappe.prompt([{ fieldtype: 'Small Text', label: 'Nota (opzionale)', fieldname: 'note' }], (v) => {
				frappe.call('thanatos_intel.workflow.api.complete_gate', { case_name: frm.doc.name, seq: seq, note: v.note || '' })
					.then(() => { frappe.show_alert({ message: 'Step completato', indicator: 'green' }); frm.reload_doc(); });
			}, 'Completa step', 'Conferma');
		});
		$w.find('.ck-ai').on('click', function () {
			const $o = $w.find('.ck-aiout').show().html('<div class="ck-mut">🤖 Sto pensando…</div>');
			frappe.call('thanatos_intel.workflow.ai_concierge.suggest_next', { case_name: frm.doc.name })
				.then(r => { const m = r.message || {}; $o.html(m.ok
					? '<div class="ck-ai-card">🤖 ' + esc(m.suggestion).replace(/\n/g, '<br>') + '</div>'
					: '<div class="ck-mut">' + esc(m.error || 'AI non disponibile.') + '</div>'); })
				.catch(() => $o.html('<div class="ck-mut">AI non disponibile.</div>'));
		});
	},
	injectCss() {
		if (document.getElementById('ck-css')) return;
		const css = `
		.ck-card{border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);padding:14px 16px;margin:6px 0 4px}
		.ck-mut{color:var(--text-muted);font-size:13px}
		.ck-row{display:flex;align-items:center;gap:12px}
		.ck-ribbon{display:flex;gap:6px;margin-bottom:12px}
		.ck-seg{flex:1;display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid var(--border-color);border-radius:8px;background:var(--bg-color);min-width:0}
		.ck-seg-dot{width:9px;height:9px;border-radius:50%;background:var(--border-color);flex:none}
		.ck-seg-lbl{font-size:11.5px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
		.ck-seg.ck-done .ck-seg-dot{background:#29CD42}
		.ck-seg.ck-done .ck-seg-lbl{color:var(--text-color)}
		.ck-seg.ck-current{border-color:#C8A96E;box-shadow:inset 0 -2px 0 #C8A96E}
		.ck-seg.ck-current .ck-seg-dot{background:#C8A96E}
		.ck-seg.ck-current .ck-seg-lbl{color:var(--text-color);font-weight:500}
		.ck-prog{display:flex;align-items:center;gap:12px;margin-bottom:4px}
		.ck-bar{flex:1;height:8px;background:var(--bg-color);border:1px solid var(--border-color);border-radius:4px;overflow:hidden}
		.ck-bar-f{height:100%;background:#C8A96E;transition:width .3s}
		.ck-pct{font-size:12px;color:var(--text-muted);white-space:nowrap}
		.ck-next{margin-top:14px;border:1px solid #C8A96E;border-radius:10px;padding:12px 14px;background:var(--bg-color)}
		.ck-next-h{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#C8A96E;margin-bottom:6px}
		.ck-next-b{display:flex;align-items:center;gap:8px;margin-bottom:10px}
		.ck-next-lbl{font-size:14px;font-weight:500;color:var(--text-color)}
		.ck-next-act{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
		.ck-done-all{margin-top:14px;border:1px solid #29CD42;color:#1a8a2e;border-radius:10px;padding:10px 14px;font-size:13px}
		.ck-wait{font-size:12px;color:#ECAD4B}
		.ck-chip{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);border:1px solid var(--border-color);padding:2px 7px;border-radius:10px;white-space:nowrap}
		.ck-gate{color:#ECAD4B;border-color:#ECAD4B}
		.ck-aiout{margin-top:10px}
		.ck-ai-card{background:var(--card-bg);border:1px solid #C8A96E;border-radius:8px;padding:12px;font-size:13px;color:var(--text-color);line-height:1.5}
		.ck-all{margin-top:12px}
		.ck-all summary{cursor:pointer;font-size:12px;color:var(--text-muted);user-select:none}
		.ck-steps{display:flex;flex-direction:column;gap:4px;margin-top:8px}
		.ck-step{display:flex;align-items:center;gap:10px;padding:7px 10px;border:1px solid var(--border-color);border-radius:6px}
		.ck-step.ck-current{border-color:#C8A96E;box-shadow:inset 3px 0 0 #C8A96E}
		.ck-step.ck-done{opacity:.55}
		.ck-ic{width:18px;text-align:center;font-weight:700;color:#C8A96E}
		.ck-step.ck-done .ck-ic{color:#29CD42}
		.ck-lbl{flex:1;font-size:13px;color:var(--text-color)}
		`;
		$('<style id="ck-css">').text(css).appendTo(document.head);
	}
};

// Render del cockpit + pannello verifiche + declutter (nasconde pannelli ridondanti)
frappe.ui.form.on('Investigation Case', {
	refresh(frm) {
		if (frm.is_new()) return;
		ThanatosCockpit.render(frm);
		ThanatosVerifiche.render(frm);
		['case_timeline', 'ai_suggest', 'progress_panel'].forEach(f => { if (frm.fields_dict[f]) frm.set_df_property(f, 'hidden', 1); });
	}
});

// ── Pannello "Strumenti dati (openapi)" nel tab Entità & Verifiche ───────────
// Per-entità (società → visura/soci-UBO/KYC; persona → KYC/negatività/patrimoniale)
// + catalogo e ricerca libera. Ogni run scrive un reperto sul caso.
window.ThanatosVerifiche = {
	OC: 'thanatos_intel.osint.openapi_client.',
	render(frm) {
		if (frm.is_new() || !frm.fields_dict.verifiche_panel) return;
		this.injectCss();
		const $w = frm.fields_dict.verifiche_panel.$wrapper;
		$w.html('<div class="vf-mut">Carico entità…</div>');
		const self = this;
		frappe.call(this.OC + 'case_entities', { case: frm.doc.name })
			.then(r => self.draw(frm, $w, (r.message || {}).entities || []))
			.catch(() => $w.html('<div class="vf-mut">Strumenti non disponibili.</div>'));
	},
	draw(frm, $w, ents) {
		const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
		let h = '<div class="vf-card"><div class="vf-head">Strumenti dati per le entità del caso</div>';
		if (!ents.length) {
			h += '<div class="vf-mut">Nessuna entità nel caso. Aggiungile in "Entities Involved" qui sopra.</div>';
		} else {
			ents.forEach(e => {
				const isCo = e.type === 'Company';
				const tlabel = isCo ? 'Società' : (e.type === 'Person' ? 'Persona' : (e.type || 'Persona'));
				h += `<div class="vf-row"><div class="vf-ent"><span class="vf-nm">${esc(e.full_name)}</span>`
					+ `<span class="vf-chip">${tlabel}</span>`
					+ (isCo ? `<span class="vf-id">${e.piva ? 'P.IVA ' + esc(e.piva) : '⚠ P.IVA mancante'}</span>` : (e.cf ? `<span class="vf-id">${esc(e.cf)}</span>` : '')) + '</div>'
					+ '<div class="vf-acts">';
				if (isCo) {
					if (!e.piva) h += this.btn('🔗 Trova P.IVA', 'piva', e) + this.btn('🌍 Estero', 'estero', e);
					h += this.btn('🏛 Visura', 'visura', e) + this.btn('👥 Soci & UBO', 'soci', e) + this.btn('🛂 Sanzioni/PEP', 'free', e);
				} else {
					h += this.btn('🛂 Sanzioni/PEP', 'free', e) + this.btn('⚖ Negatività', 'neg', e) + this.btn('🏦 Patrimoniale', 'patr', e);
				}
				h += '</div></div>';
			});
		}
		const missing = ents.filter(e => e.type === 'Company' && !e.piva).length;
		h += '<div class="vf-foot">'
			+ (missing ? '<button class="btn btn-xs btn-primary vf-resolve">🔗 Risolvi ' + missing + ' P.IVA mancanti</button>' : '')
			+ '<button class="btn btn-xs btn-default vf-prev">🧾 Preventivo & pagamento cliente</button>'
			+ '<button class="btn btn-xs btn-default vf-cat">🧰 Catalogo strumenti (free/paid)</button>'
			+ '<button class="btn btn-xs btn-default vf-free">🔎 Ricerca libera</button></div>';
		h += '<div class="vf-out" style="display:none"></div></div>';
		$w.html(h);
		const self = this;
		$w.find('.vf-btn').on('click', function () { self.run(frm, $w, $(this).data('act'), $(this).data('idx'), ents); });
		$w.find('.vf-cat').on('click', () => self.catalog($w));
		$w.find('.vf-free').on('click', () => self.freeForm(frm, $w));
		$w.find('.vf-prev').on('click', () => self.preventivo(frm, $w));
		$w.find('.vf-resolve').on('click', () => {
			const $o = $w.find('.vf-out').show().html('<div class="vf-mut">Risoluzione P.IVA mancanti (openapi)…</div>');
			frappe.call({ method: self.OC + 'risolvi_pive_caso', args: { case: frm.doc.name }, freeze: true, freeze_message: 'Risoluzione P.IVA…', callback: r => {
				const m = r.message || {};
				$o.html('<div class="vf-res">✓ ' + (m.tot || 0) + ' P.IVA risolte e salvate' + ((m.tot || 0) ? ': ' + (m.risolte || []).map(x => frappe.utils.escape_html(x.nome) + ' → ' + x.piva).join('; ') : '.') + '<br>Ricarico…</div>');
				setTimeout(() => frm.reload_doc(), 1200);
			} });
		});
	},
	btn(label, act, e) {
		return `<button class="btn btn-xs btn-default vf-btn" data-act="${act}" data-idx="${e.idx}">${label}</button>`;
	},
	run(frm, $w, act, idx, ents) {
		const e = ents.find(x => String(x.idx) === String(idx));
		if (!e) return;
		const $o = $w.find('.vf-out').show().html('<div class="vf-mut">Interrogazione openapi…</div>');
		const done = (html) => $o.html('<div class="vf-res">' + html + '</div>');
		const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
		const cb = (fmt) => ({ callback: r => done(fmt(r.message || {})), freeze: true, freeze_message: 'Interrogazione…' });
		const args = { investigation_case: frm.doc.name };
		if (act === 'visura') {
			if (!e.piva) return done('⚠ Manca la P.IVA su questa entità.');
			frappe.call(Object.assign({ method: 'thanatos_intel.osint.registro_imprese.verifica_impresa', args: Object.assign({ piva: e.piva }, args) }, cb(m => {
				const c = m.company || {}; return '<b>' + esc(c.denominazione || e.full_name) + '</b><br>Stato: ' + esc(c.stato || '-') + ' · Capitale: ' + esc(c.capitale || '-') + ' · ATECO: ' + esc(c.ateco || '-');
			})));
		} else if (act === 'soci') {
			if (!e.piva) return done('⚠ Manca la P.IVA su questa entità.');
			frappe.call(Object.assign({ method: this.OC + 'soci_titolari', args: Object.assign({ piva: e.piva }, args) }, cb(m => {
				const soci = (m.soci || []).map(s => esc(s.nome) + ' (' + s.quota + '%)').join('; ') || '—';
				const ubo = (m.ubo || []).map(u => esc(u.nome) + ' [' + (u.cf || '') + ']').join('; ') || '—';
				return '<b>Soci:</b> ' + soci + '<br><b>UBO:</b> ' + ubo;
			})));
		} else if (act === 'free') {
			frappe.call(Object.assign({ method: this.OC + 'screening_free', args: Object.assign({ query: e.full_name }, args) }, cb(m => {
				if (m.error) return '⚠ ' + esc(m.error);
				const hl = (m.hits || []).map(x => esc(x.nome)).join(', ') || 'nessun match';
				return '<b>Sanzioni/PEP «' + esc(e.full_name) + '»</b> <span class="vf-free-tag">free · OpenSanctions</span><br>' + (m.match || 0) + ' match — ' + hl;
			})));
		} else if (act === 'estero') {
			const isUK = /\bUK\b|\bGB\b/i.test(e.ident || '');
			if (isUK) {
				frappe.call(Object.assign({ method: 'thanatos_intel.osint.companies_house.kyb_lookup', args: { entity_name: e.entity } }, cb(m => {
					return '<b>🇬🇧 Companies House «' + esc(e.full_name) + '»</b> (' + esc(m.number || '') + ')<br>Stato: ' + esc(m.status || '-') + ' · ' + (m.officers || 0) + ' officer · ' + (m.psc || 0) + ' PSC (UBO) · ' + (m.linked_companies || 0) + ' società collegate';
				}))).fail(() => done('⚠ Companies House: chiave mancante. Registrati gratis su developer.company-information.service.gov.uk e inserisci companies_house_api_key.'));
			} else {
				frappe.call(Object.assign({ method: 'thanatos_intel.osint.opencorporates.lookup', args: Object.assign({ name: e.full_name }, args) }, cb(m => {
					if (m.stub) return '⚠ ' + esc(m.message);
					if (m.error) return '⚠ ' + esc(m.error);
					const hl = (m.risultati || []).map(x => esc(x.nome) + ' (' + esc(x.giurisdizione) + ' ' + esc(x.numero) + ') — ' + esc(x.stato || '-')).join('<br>') || 'nessun match';
					return '<b>🌍 OpenCorporates «' + esc(e.full_name) + '»</b>' + (m.jurisdiction ? ' [' + esc(m.jurisdiction) + ']' : '') + '<br>' + (m.match || 0) + ' match<br>' + hl;
				})));
			}
		} else if (act === 'piva') {
			frappe.call({ method: this.OC + 'risolvi_piva', args: { name: e.full_name }, freeze: true, freeze_message: 'Risoluzione P.IVA…', callback: r => {
				const m = r.message || {};
				if (!m.piva) return done('⚠ P.IVA non trovata per «' + esc(e.full_name) + '».');
				frappe.call({ method: 'frappe.client.set_value', args: { doctype: 'Investigation Entity', name: e.entity, fieldname: 'primary_identifier', value: m.piva }, callback: () => {
					done('✓ P.IVA <b>' + esc(m.piva) + '</b> (' + esc(m.denominazione || '') + ') salvata. Ricarico…');
					setTimeout(() => frm.reload_doc(), 900);
				} });
			} });
		} else if (act === 'neg') {
			const idv = e.cf || e.piva;
			if (!idv) return done('⚠ Manca CF/P.IVA.');
			frappe.call(Object.assign({ method: this.OC + 'negativita', args: Object.assign({ cf_piva: idv }, args) }, cb(m => {
				if (m.error) return '⚠ ' + esc(m.error);
				return '<b>Negatività ' + esc(idv) + ':</b> ' + esc(m.status) + ' — ' + esc(JSON.stringify(m.esito || ''));
			})));
		} else if (act === 'patr') {
			const parts = (e.full_name || '').trim().split(/\s+/);
			frappe.prompt([
				{ fieldtype: 'Data', fieldname: 'name', label: 'Nome', default: parts[0] || '', reqd: 1 },
				{ fieldtype: 'Data', fieldname: 'surname', label: 'Cognome', default: parts.slice(1).join(' '), reqd: 1 },
				{ fieldtype: 'Data', fieldname: 'cf', label: 'Codice Fiscale', default: e.cf || '', reqd: 1 }
			], (v) => {
				frappe.call(Object.assign({ method: this.OC + 'patrimoniale', args: Object.assign({ name: v.name, surname: v.surname, tax_code: v.cf }, args) }, cb(m => {
					if (m.error) return '⚠ ' + esc(m.error);
					return '<b>Patrimoniale ' + esc(v.name + ' ' + v.surname) + ':</b> ' + esc(m.status);
				})));
			}, 'Patrimoniale persona', 'Esegui');
		}
	},
	catalog($w) {
		const $o = $w.find('.vf-out').show().html('<div class="vf-mut">Carico catalogo…</div>');
		const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
		frappe.call('thanatos_intel.osint.tool_catalog.catalogo_completo').then(r => {
			const c = r.message || {}; const st = c.stats || {}; const mb = c.modello || {};
			let h = '<div class="vf-res"><div class="vf-mut" style="margin-bottom:6px">'
				+ (st.capacita || 0) + ' capacità · ' + (st.fonti_totali || 0) + ' fonti (<b style="color:#1a8a2e">' + (st.fonti_gratuite || 0) + ' gratuite</b>) · '
				+ (st.famiglie_openapi || 0) + ' famiglie openapi</div>';
			if (mb.principio) h += '<div class="vf-bill">💶 ' + esc(mb.catena) + '<br><b>' + esc(mb.principio) + '</b></div>';
			h += '<table class="vf-cat-tbl"><thead><tr><th>Capacità</th><th>🟢 Gratis dà</th><th>🔴 Paid aggiunge</th><th>⚠ Manca nel free</th></tr></thead><tbody>';
			(c.capacita || []).forEach(x => {
				const cons = x.consiglio === 'free' ? '<span class="vf-free-tag">usa free</span>' : (x.consiglio === 'paid' ? '<span class="vf-paid-tag">paid</span>' : '<span class="vf-mix-tag">misto</span>');
				const fhas = (x.free || []).length;
				h += '<tr><td><b>' + esc(x.capacita) + '</b> ' + cons + '<br><span class="vf-mut">' + esc(((x.free || []).concat(x.paid || [])).join(' · ')) + '</span></td>'
					+ '<td class="' + (fhas ? 'vf-ok' : '') + '">' + esc(x.free_dati || '—') + '</td>'
					+ '<td>' + esc(x.paid_dati || '—') + '</td>'
					+ '<td class="vf-gap">' + esc(x.gap || '—') + '</td></tr>';
			});
			h += '</tbody></table></div>';
			$o.html(h);
		});
	},
	freeForm(frm, $w) {
		frappe.prompt([
			{ fieldtype: 'Select', fieldname: 'tool', label: 'Strumento', reqd: 1, options: ['Visura camerale (P.IVA)', 'Soci & UBO (P.IVA)', 'Screening KYC (nome)', 'Negatività (CF/P.IVA)', 'Verifica IBAN', 'Veicolo (targa)', 'VirusTotal (IP/dominio/URL)', 'AbuseIPDB (IP)', 'Shodan (IP)', 'IPinfo (IP)', 'urlscan (dominio/URL)'].join('\n') },
			{ fieldtype: 'Data', fieldname: 'value', label: 'Valore (P.IVA / nome / CF / IBAN / targa / IP / dominio / URL)', reqd: 1 }
		], (v) => {
			const $o = $w.find('.vf-out').show().html('<div class="vf-mut">Interrogazione…</div>');
			const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
			const done = h => $o.html('<div class="vf-res">' + h + '</div>');
			const a = { investigation_case: frm.doc.name };
			const T = v.tool;
			if (T.indexOf('Visura') === 0) frappe.call({ method: 'thanatos_intel.osint.registro_imprese.verifica_impresa', args: Object.assign({ piva: v.value }, a), callback: r => { const c = (r.message || {}).company || {}; done('<b>' + esc(c.denominazione || '-') + '</b> · ' + esc(c.stato || '-')); } });
			else if (T.indexOf('Soci') === 0) frappe.call({ method: this.OC + 'soci_titolari', args: Object.assign({ piva: v.value }, a), callback: r => { const m = r.message || {}; done('Soci: ' + ((m.soci || []).map(s => esc(s.nome) + ' (' + s.quota + '%)').join('; ') || '—') + '<br>UBO: ' + ((m.ubo || []).map(u => esc(u.nome)).join('; ') || '—')); } });
			else if (T.indexOf('Screening') === 0) frappe.call({ method: this.OC + 'screening_kyc', args: Object.assign({ query: v.value, mode: 'pep' }, a), callback: r => { const m = r.message || {}; done(m.error ? '⚠ ' + esc(m.error) : (m.match || 0) + ' match — ' + ((m.hits || []).map(x => esc(x.nome)).join(', ') || 'nessuno')); } });
			else if (T.indexOf('Negatività') === 0) frappe.call({ method: this.OC + 'negativita', args: Object.assign({ cf_piva: v.value }, a), callback: r => { const m = r.message || {}; done(m.error ? '⚠ ' + esc(m.error) : esc(m.status) + ' — ' + esc(JSON.stringify(m.esito || ''))); } });
			else if (T.indexOf('IBAN') >= 0) frappe.call({ method: this.OC + 'verifica_iban', args: Object.assign({ iban: v.value }, a), callback: r => { const m = r.message || {}; done(m.error ? '⚠ ' + esc(m.error) : 'Valido: ' + esc(m.valido) + ' · Banca: ' + esc(m.banca || '-')); } });
			else if (T.indexOf('Veicolo') >= 0) frappe.call({ method: this.OC + 'veicolo', args: Object.assign({ targa: v.value }, a), callback: r => { const m = r.message || {}; done(m.error ? '⚠ ' + esc(m.error) : esc(JSON.stringify(m.dati || {}).slice(0, 300))); } });
			const CY = 'thanatos_intel.osint.cyber_intel.';
			const cyDone = (m, body) => done(m.stub ? '⚠ ' + esc(m.message) : (m.error ? '⚠ ' + esc(m.error) : body(m)));
			if (T.indexOf('VirusTotal') === 0) frappe.call({ method: CY + 'virustotal', args: Object.assign({ target: v.value }, a), callback: r => cyDone(r.message || {}, m => '<b>VirusTotal ' + esc(m.target) + '</b><br>Malicious: ' + m.malicious + ' · Suspicious: ' + m.suspicious + ' · Reputation: ' + esc(m.reputation) + '<br>AS: ' + esc(m.as_owner || '-') + ' (' + esc(m.country || '-') + ')') });
			else if (T.indexOf('AbuseIPDB') === 0) frappe.call({ method: CY + 'abuseipdb', args: Object.assign({ ip: v.value }, a), callback: r => cyDone(r.message || {}, m => '<b>AbuseIPDB ' + esc(m.ip) + '</b><br>Abuse score: ' + esc(m.abuse_score) + '% · ' + esc(m.segnalazioni) + ' segnalazioni<br>ISP: ' + esc(m.isp || '-') + ' (' + esc(m.paese || '-') + ')') });
			else if (T.indexOf('Shodan') === 0) frappe.call({ method: CY + 'shodan_host', args: Object.assign({ ip: v.value }, a), callback: r => cyDone(r.message || {}, m => '<b>Shodan ' + esc(m.ip) + '</b><br>Org: ' + esc(m.org || '-') + '<br>Porte: ' + esc((m.porte || []).join(', ') || '-') + '<br>Vuln: ' + esc((m.vulns || []).join(', ') || 'nessuna')) });
			else if (T.indexOf('IPinfo') === 0) frappe.call({ method: CY + 'ipinfo', args: Object.assign({ ip: v.value }, a), callback: r => cyDone(r.message || {}, m => '<b>IPinfo ' + esc(m.ip) + '</b><br>Org/ASN: ' + esc(m.org || '-') + '<br>' + esc(m.citta || '-') + ', ' + esc(m.paese || '-') + ' · ' + esc(m.hostname || '-')) });
			else if (T.indexOf('urlscan') === 0) frappe.call({ method: CY + 'urlscan', args: Object.assign({ target: v.value }, a), callback: r => cyDone(r.message || {}, m => '<b>urlscan ' + esc(m.target) + '</b><br>' + (m.scansioni || 0) + ' scansioni<br>' + (m.ultime || []).map(u => esc(u.url) + ' → ' + esc(u.ip || '-') + ' (' + esc(u.paese || '-') + ')').join('<br>')) });
		}, 'Ricerca libera', 'Esegui');
	},
	preventivo(frm, $w) {
		const esc = s => frappe.utils.escape_html(s == null ? '' : String(s));
		frappe.call('thanatos_intel.billing.openapi_billing.listino', { case: frm.doc.name }).then(r => {
			const lst = r.message || {}; const voci = lst.voci || [];
			const rows = voci.map(v => `<label style="display:flex;align-items:center;gap:8px;padding:5px 0;font-size:13px">
				<input type="checkbox" class="vf-pv-it" data-id="${v.id}" data-label="${esc(v.label)}">
				<span style="flex:1">${esc(v.label)}</span>
				<span style="color:var(--text-muted)">€ ${v.prezzo.toFixed(2)}</span></label>`).join('');
			const d = new frappe.ui.Dialog({
				title: 'Preventivo cliente',
				fields: [
					{ fieldtype: 'HTML', fieldname: 'list', options: '<div style="max-height:240px;overflow:auto">' + rows + '</div>' + '<div style="font-size:11px;color:var(--text-muted);margin-top:6px">Prezzi IVA esclusa' + (lst.iva_note ? ' · ' + esc(lst.iva_note) : '') + '</div>' },
					{ fieldtype: 'Data', fieldname: 'payer_email', label: 'Email destinatario (vuoto = email cliente del caso)' },
					{ fieldtype: 'Check', fieldname: 'invia', label: 'Invia subito il link via email', default: 1 },
					{ fieldtype: 'HTML', fieldname: 'out' }
				],
				primary_action_label: 'Genera preventivo & link',
				primary_action(v) {
					const items = [];
					d.$wrapper.find('.vf-pv-it:checked').each(function () {
						items.push({ id: $(this).data('id'), label: $(this).data('label') });
					});
					if (!items.length) { frappe.show_alert({ message: 'Seleziona almeno una voce', indicator: 'orange' }); return; }
					frappe.call({
						method: 'thanatos_intel.billing.openapi_billing.genera_preventivo',
						args: { case: frm.doc.name, items: JSON.stringify(items), payer_email: v.payer_email || '', invia: v.invia ? 1 : 0 },
						freeze: true, freeze_message: 'Genero preventivo e link Stripe…',
						callback(r2) {
							const m = r2.message || {};
							let h = '<div style="margin-top:10px;border-top:1px solid var(--border-color);padding-top:10px">';
							h += '<div>Imponibile: € ' + (m.imponibile != null ? m.imponibile : (m.totale_cliente || 0)).toFixed(2) + '</div>';
							if (m.iva_rate) h += '<div>' + esc(m.iva_note || 'IVA') + ': € ' + (m.iva_importo || 0).toFixed(2) + '</div>';
							else if (m.iva_note) h += '<div style="color:var(--text-muted)">' + esc(m.iva_note) + '</div>';
							h += '<b>Totale cliente: € ' + (m.totale_cliente || 0).toFixed(2) + '</b> (' + (m.righe || []).length + ' voci)';
							if (m.link) h += '<div style="margin-top:8px"><a href="' + m.link + '" target="_blank" class="btn btn-xs btn-primary">Apri link pagamento</a> '
								+ '<button class="btn btn-xs btn-default vf-copy" data-l="' + esc(m.link) + '">Copia link</button></div>';
							else if (m.link_error) h += '<div style="color:#c0392b;margin-top:6px">Link non generato: ' + esc(m.link_error) + '</div>';
							if (m.inviato) h += '<div style="margin-top:6px;color:' + (m.inviato.ok ? '#1a8a2e' : '#c0392b') + '">'
								+ (m.inviato.ok ? '✓ Inviato a ' + esc(m.inviato.to) : '⚠ Invio: ' + esc(m.inviato.error)) + '</div>';
							h += '</div>';
							d.fields_dict.out.$wrapper.html(h);
							d.$wrapper.find('.vf-copy').on('click', function () { navigator.clipboard.writeText($(this).data('l')); frappe.show_alert({ message: 'Link copiato', indicator: 'green' }); });
							frm.reload_doc();
						}
					});
				}
			});
			d.show();
		});
	},
	injectCss() {
		if (document.getElementById('vf-css')) return;
		const css = `
		.vf-card{border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);padding:12px 14px;margin:6px 0}
		.vf-head{font-size:13px;font-weight:500;color:var(--text-color);margin-bottom:10px}
		.vf-mut{color:var(--text-muted);font-size:12.5px}
		.vf-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 0;border-top:1px solid var(--border-color);flex-wrap:wrap}
		.vf-row:first-of-type{border-top:0}
		.vf-ent{display:flex;align-items:center;gap:8px;min-width:0;flex-wrap:wrap}
		.vf-nm{font-size:13px;color:var(--text-color)}
		.vf-chip{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);border:1px solid var(--border-color);padding:2px 7px;border-radius:10px}
		.vf-id{font-size:11.5px;color:var(--text-muted);font-family:monospace}
		.vf-acts{display:flex;gap:6px;flex-wrap:wrap}
		.vf-foot{margin-top:12px;display:flex;gap:8px}
		.vf-out{margin-top:12px}
		.vf-res{background:var(--bg-color);border:1px solid #C8A96E;border-radius:8px;padding:12px;font-size:13px;color:var(--text-color);line-height:1.6}
		.vf-free-tag{font-size:10px;color:#1a8a2e;border:1px solid #29CD42;border-radius:8px;padding:1px 6px;margin-left:4px}
		.vf-paid-tag{font-size:10px;color:#a33;border:1px solid #e0879a;border-radius:8px;padding:1px 6px;margin-left:4px}
		.vf-mix-tag{font-size:10px;color:#9a7d2e;border:1px solid #ECAD4B;border-radius:8px;padding:1px 6px;margin-left:4px}
		.vf-cat-tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}
		.vf-cat-tbl th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted);font-weight:500}
		.vf-cat-tbl td{padding:7px 8px;border-bottom:1px solid var(--border-color);vertical-align:top}
		.vf-cat-tbl td.vf-ok{color:#1a8a2e}
		.vf-cat-tbl td.vf-gap{color:#a33}
		.vf-bill{background:var(--bg-color);border:1px solid #ECAD4B;border-radius:8px;padding:8px 10px;margin:6px 0 10px;font-size:12px;color:var(--text-color);line-height:1.5}
		`;
		$('<style id="vf-css">').text(css).appendTo(document.head);
	}
};

// --- Genera fattura ARES (azione one-click) ---
frappe.ui.form.on("Investigation Case", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Genera fattura"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Genera fattura"),
                fields: [
                    {fieldname: "billing_entity", fieldtype: "Link", options: "Billing Entity",
                     label: __("Entità che fattura"), reqd: 1, default: frm.doc.billing_entity || ""},
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
                               amount: values.amount, description: values.description,
                               billing_entity: values.billing_entity},
                        freeze: true,
                        freeze_message: __("Creazione fattura..."),
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
            if (!d.get_value("billing_entity")) {
                frappe.call("thanatos_intel.billing.billing_entity.resolve_billing_entity", { case: frm.doc.name })
                    .then(r => { if (r.message) d.set_value("billing_entity", r.message); });
            }
            d.show();
        }, __("Azioni"));
    },
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
        const chips = thanatos_case_chips(frm.doc.case_type);
        $w.html(
            '<div style="border:1px solid #e0d7c0;border-radius:10px;background:#fff;overflow:hidden">'
            + '<div style="background:#0D1B3E;color:#C8A96E;font-weight:700;padding:8px 12px">🤖 Assistente AI del caso</div>'
            + '<div id="aic-msgs" style="height:240px;overflow-y:auto;padding:10px 12px;font-size:13px;background:#faf8f2"></div>'
            + '<div style="padding:6px 10px;border-top:1px solid #eee">'
            + '<div id="aic-chips" style="margin-bottom:6px"></div>'
            + '<div style="display:flex;gap:6px;align-items:center"><input id="aic-in" class="form-control input-sm" placeholder="' + ('Chiedi o comanda… (' + thanatos_case_example(frm.doc.case_type) + ')') + '" style="flex:1">'
            + '<button id="aic-attach" class="btn btn-default btn-sm" title="Carica file nel dossier (audio, zip, foto, PDF…)">📎</button>'
            + '<input id="aic-file" type="file" multiple style="display:none">'
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
        // upload file → dossier (reperto sul caso)
        $w.find('#aic-attach').on('click', () => $w.find('#aic-file').click());
        $w.find('#aic-file').on('change', function () {
            const files = Array.from(this.files || []); this.value = '';
            files.forEach(file => {
                add('me', '📎 ' + file.name);
                const fd = new FormData();
                fd.append('file', file); fd.append('is_private', 1);
                fd.append('doctype', 'Investigation Case'); fd.append('docname', frm.doc.name);
                add('ai', '⏳ carico…');
                fetch('/api/method/upload_file', { method: 'POST', headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token }, body: fd })
                    .then(r => r.json()).then(j => {
                        const fu = (j.message || {}).file_url;
                        if (!fu) { $msgs.find('div:last').remove(); add('ai', '⚠ upload fallito'); return; }
                        frappe.call({ method: 'thanatos_intel.ai.case_assistant.chat_upload',
                            args: { case: frm.doc.name, file_url: fu, file_name: file.name, content_type: file.type || '' },
                            callback(r2) {
                                $msgs.find('div:last').remove();
                                const m = r2.message || {};
                                add('ai', '✅ «' + file.name + '» nel dossier come reperto' + (m.evidence ? ' ' + m.evidence : '') + (m.transcribing ? ' · trascrizione audio avviata' : ''));
                                frm.reload_doc();
                            } });
                    }).catch(() => { $msgs.find('div:last').remove(); add('ai', '⚠ upload fallito'); });
            });
        });
        add('ai', 'Ciao, sono l’assistente di questo caso' + (frm.doc.case_type ? ' (' + frm.doc.case_type + ')' : '') + '. Qui i comandi utili: ' + chips.join(', ') + '. Scrivi un comando, fai una domanda o usa i tasti rapidi.');
    }
});

// ── Bottone Collegamenti societari ──
frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__('🕸️ Collegamenti societari'), () => {
            frappe.call({ method: 'thanatos_intel.ai.corporate_links.analizza_collegamenti', args: { case: frm.doc.name },
                freeze: true, freeze_message: __('Analisi rete societaria...'),
                callback(r) { const m = r.message || {}; frappe.msgprint({ title: __('Collegamenti societari'), indicator: 'orange',
                    message: '<pre style="white-space:pre-wrap;font-size:12px">' + frappe.utils.escape_html(m.text || '') + '</pre>' }); frm.reload_doc(); } });
        }, __('Intelligence'));
    }
});

// ── Bottone Costruisci cluster gruppo ──
frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__('🕸️ Costruisci cluster gruppo'), () => {
            frappe.call({ method: 'thanatos_intel.ai.corporate_links.costruisci_cluster', args: { case: frm.doc.name },
                freeze: true, freeze_message: __('Costruzione cluster...'),
                callback(r) { const m = r.message || {}; if (m.gruppo) { frappe.show_alert({ message: __('Cluster {0}: {1} membri, {2} collegamenti', [m.gruppo, m.membri, m.links]), indicator: 'green' }, 8);
                    frappe.set_route('Form', 'Corporate Group', m.gruppo); } } });
        }, __('Intelligence'));
    }
});


// ── Chip rapidi contestuali al tipo di caso ──
function thanatos_case_example(case_type) {
    const ex = {
        'Fraud': 'es. screening, analisi completa',
        'Cyber': 'es. screening, genera dossier',
        'Asset Recovery': 'es. screening, doppia cessione',
        'Due Diligence': 'es. verifica camerale 03293360966, valuta assicurazione',
        'Corporate': 'es. verifica camerale 03293360966, screening',
        'Family': 'es. screening, domande',
    };
    return ex[case_type] || 'es. screening, genera dossier';
}
function thanatos_case_chips(case_type) {
    const common = ['avanzamento', 'genera dossier', 'proforma', 'domande', 'analisi completa'];
    const extra = {
        'Fraud': ['screening', 'doppia cessione'],
        'Cyber': ['screening'],
        'Asset Recovery': ['screening', 'doppia cessione'],
        'Due Diligence': ['verifica camerale', 'valuta assicurazione', 'doppia cessione'],
        'Corporate': ['verifica camerale', 'screening'],
        'Family': ['screening'],
    };
    const ex = extra[case_type] || ['screening', 'verifica camerale'];
    return [...new Set(common.concat(ex))];
}

// ── Timeline compatta: ultime N attività + "Mostra tutte" + ricerca ──
function thanatos_compact_timeline(frm) {
    const wrap = frm.timeline && frm.timeline.wrapper;
    if (!wrap || !wrap.length) return;
    const all = wrap.find('.timeline-item').filter(function () {
        return $(this).find('textarea, .comment-input-wrapper, .comment-input-container').length === 0;
    });
    const LIMIT = 8;
    if (all.length <= LIMIT + 3) return;          // poche attività: nessun taglio
    let state = wrap.data('thn-tl') || { expanded: false };
    if (!wrap.find('.thn-tl-tools').length) {
        const tools = $('<div class="thn-tl-tools" style="display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap">'
            + '<input class="form-control input-sm thn-tl-search" placeholder="🔎 cerca nelle attività…" style="max-width:260px">'
            + '<button class="btn btn-xs btn-default thn-tl-toggle"></button>'
            + '<span class="text-muted thn-tl-count" style="font-size:11px"></span></div>');
        all.first().before(tools);
    }
    function apply() {
        const q = (wrap.find('.thn-tl-search').val() || '').toLowerCase().trim();
        let shown = 0;
        all.each(function (i) {
            const $i = $(this);
            const matchQ = !q || $i.text().toLowerCase().indexOf(q) >= 0;
            const vis = q ? matchQ : (state.expanded || i < LIMIT);
            $i.toggle(vis); if (vis) shown++;
        });
        const $t = wrap.find('.thn-tl-toggle');
        if (q) { $t.hide(); wrap.find('.thn-tl-count').text(shown + ' risultati'); }
        else {
            $t.show().text(state.expanded ? __('Mostra meno') : (__('Mostra tutte') + ' (' + all.length + ')'));
            wrap.find('.thn-tl-count').text(state.expanded ? '' : ('ultime ' + Math.min(LIMIT, all.length) + ' di ' + all.length));
        }
    }
    wrap.find('.thn-tl-toggle').off('click').on('click', () => { state.expanded = !state.expanded; wrap.data('thn-tl', state); apply(); });
    wrap.find('.thn-tl-search').off('input').on('input', apply);
    wrap.data('thn-tl', state);
    apply();
}

frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        if (frm.is_new()) return;
        setTimeout(() => thanatos_compact_timeline(frm), 1500);
        setTimeout(() => thanatos_compact_timeline(frm), 3500);
    }
});
