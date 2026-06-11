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

        if (!frm.is_new() && frm.doc.drive_folder) {
            frm.add_custom_button(__('Apri Drive'), () => {
                window.open('/drive?entity=' + frm.doc.drive_folder, '_blank');
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
        }

        // ---- Report: genera per tema, PDF in Drive con tag cliente, firma DocuSeal ----
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

            frm.add_custom_button(__('Invia a DocuSeal (firma)'), () => {
                const files = (frm.get_files ? frm.get_files() : []).filter(f => (f.file_url || '').toLowerCase().endsWith('.pdf'));
                const d = new frappe.ui.Dialog({
                    title: __('Invia report a DocuSeal'),
                    fields: [
                        { fieldname: 'file_url', fieldtype: 'Select', label: __('PDF da firmare'), reqd: 1,
                          options: files.map(f => f.file_url).join('\n') },
                        { fieldname: 'signer_email', fieldtype: 'Data', label: __('Email firmatario') },
                        { fieldname: 'signer_name', fieldtype: 'Data', label: __('Nome firmatario') }
                    ],
                    primary_action_label: __('Invia'),
                    primary_action(v) {
                        frappe.call({
                            method: 'thanatos_intel.reporting.case_reports.send_report_to_docuseal',
                            args: { file_url: v.file_url, case_name: frm.doc.name, signer_email: v.signer_email, signer_name: v.signer_name },
                            freeze: true, freeze_message: __('Invio a DocuSeal…'),
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
