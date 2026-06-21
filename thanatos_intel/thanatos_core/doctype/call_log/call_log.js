frappe.ui.form.on("Call Log", {
    refresh(frm) {
        renderTranscriptUI(frm);

        if (!frm.is_new()) {
            const st = frm.doc.transcription_status;

            if (st !== "In elaborazione") {
                frm.add_custom_button(__("Trascrivi chiamata"), () => startTranscription(frm));
            }

            if (st === "In elaborazione") {
                frm.add_custom_button(__("Aggiorna stato"), () => frm.reload_doc());
                frm.set_intro(
                    '<span style="color:#C8A96E">⏳ Trascrizione in corso... aggiorna tra qualche minuto.</span>',
                    false
                );
            }

            if (st === "Completato") {
                frm.add_custom_button(__("Rigenera vista"), () => refreshTranscript(frm));
                frm.add_custom_button(__("🎙️ Identifica voci"), () => identifyVoices(frm));
            }
        }
    },

    speaker_a_label(frm) { refreshTranscript(frm); },
    speaker_b_label(frm) { refreshTranscript(frm); },
});

function identifyVoices(frm) {
    frappe.call({
        method: "get_speakers", doc: frm.doc,
        callback(r) {
            const speakers = r.message?.speakers || [];
            if (!speakers.length) {
                frappe.msgprint(__("Nessuna impronta vocale disponibile (diarizzazione non eseguita)."));
                return;
            }
            const fields = [];
            speakers.forEach(s => {
                fields.push({
                    fieldtype: "Section Break",
                    label: __("Voce {0}{1}", [s.speaker, s.label ? ` — attuale: ${s.label}` : ""]),
                });
                fields.push({
                    fieldname: `name_${s.speaker}`, fieldtype: "Data",
                    label: __("Nome / etichetta"), default: s.label || "",
                });
                fields.push({
                    fieldname: `type_${s.speaker}`, fieldtype: "Select",
                    label: __("Tipo"), options: "Contatto\nOperatore\nAltro", default: "Contatto",
                });
                fields.push({
                    fieldname: `contact_${s.speaker}`, fieldtype: "Link",
                    label: __("Contatto rubrica"), options: "Intelligence Contact",
                    depends_on: `eval:doc.type_${s.speaker}=='Contatto'`,
                });
                fields.push({
                    fieldname: `user_${s.speaker}`, fieldtype: "Link",
                    label: __("Operatore"), options: "User",
                    depends_on: `eval:doc.type_${s.speaker}=='Operatore'`,
                });
            });
            const d = new frappe.ui.Dialog({
                title: __("Identifica le voci (crea impronte)"),
                fields,
                primary_action_label: __("Salva impronte"),
                primary_action(vals) {
                    const tasks = speakers.filter(s => vals[`name_${s.speaker}`]).map(s =>
                        new Promise((resolve) => {
                            frappe.call({
                                method: "enroll_voice", doc: frm.doc,
                                args: {
                                    speaker: s.speaker, label: vals[`name_${s.speaker}`],
                                    person_type: vals[`type_${s.speaker}`],
                                    contact: vals[`contact_${s.speaker}`] || null,
                                    user: vals[`user_${s.speaker}`] || null,
                                },
                                callback: () => resolve(),
                            });
                        }));
                    Promise.all(tasks).then(() => {
                        d.hide();
                        frappe.show_alert({ message: __("Impronte salvate! Le prossime chiamate riconosceranno queste voci."), indicator: "green" });
                        frm.reload_doc();
                    });
                },
            });
            d.show();
        },
    });
}

function startTranscription(frm) {
    if (!frm.doc.audio_file && !frm.doc.recording_url) {
        frappe.msgprint(__("Carica un file audio o inserisci l'URL di registrazione prima."));
        return;
    }

    const provider = "AssemblyAI";  // mostrato all'utente
    frappe.confirm(
        __("Avviare la trascrizione con {0}?<br><small>Potrebbe richiedere 1-5 minuti. Riceverai una notifica al termine.</small>", [provider]),
        () => {
            frappe.call({
                method: "start_transcription",
                doc: frm.doc,
                freeze: true,
                freeze_message: __("Avvio trascrizione…"),
                callback(r) {
                    if (r.message?.status === "queued") {
                        frappe.show_alert({ message: __("Trascrizione avviata in background!"), indicator: "blue" });
                        frm.reload_doc();
                    } else if (r.message?.status === "already_running") {
                        frappe.show_alert({ message: __("Trascrizione già in corso."), indicator: "orange" });
                    }
                },
            });
        }
    );
}

function refreshTranscript(frm) {
    if (frm.doc.transcription_status !== "Completato") return;
    frappe.call({
        method: "get_transcript_html",
        doc: frm.doc,
        callback(r) {
            if (r.message?.html) {
                frm.set_df_property("transcript_html", "options", r.message.html);
                frm.refresh_field("transcript_html");
            }
        },
    });
}

function renderTranscriptUI(frm) {
    if (frm.doc.transcription_status !== "Completato" || !frm.doc.transcript_raw) return;

    // Mostra subito il JSON che abbiamo già
    try {
        const segments = JSON.parse(frm.doc.transcript_raw || "[]");
        const labelA = frm.doc.speaker_a_label || "Operatore";
        const labelB = frm.doc.speaker_b_label || "";
        const labels = { A: labelA };
        if (labelB) labels["B"] = labelB;

        function fmtMs(ms) {
            const s = Math.floor(ms / 1000);
            return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
        }

        const rows = segments.map(seg => {
            const sp = seg.speaker || "?";
            const label = labels[sp] || `Speaker ${sp}`;
            const isA = sp === "A";
            const align = isA ? "flex-start" : "flex-end";
            const bg = isA ? "#1e2435" : "#C8A96E";
            const color = isA ? "#e8e8e8" : "#0A0E1A";
            const ts = fmtMs(seg.start_ms || 0);
            return `<div style="display:flex;justify-content:${align};margin:4px 0">
              <div style="max-width:75%;background:${bg};color:${color};border-radius:10px;padding:8px 12px;font-size:13px;line-height:1.5">
                <div style="font-size:10px;font-weight:bold;margin-bottom:3px;opacity:.7">${label} · ${ts}</div>
                ${frappe.utils.escape_html(seg.text || "")}
              </div>
            </div>`;
        }).join("");

        const html = `
          <div style="background:#0d1117;border-radius:8px;padding:12px;max-height:500px;overflow-y:auto">
            ${rows || '<p style="color:#666;text-align:center;padding:20px">Nessun segmento.</p>'}
          </div>
          <div style="margin-top:8px;display:flex;gap:8px">
            <button class="btn btn-xs btn-default" onclick="copyTranscript()">📋 Copia testo</button>
          </div>`;

        frm.set_df_property("transcript_html", "options", html);
        frm.refresh_field("transcript_html");
    } catch (e) {
        console.error("renderTranscriptUI", e);
    }
}

window.copyTranscript = function () {
    const text = (cur_frm?.doc?.transcript_text || "").trim();
    if (!text) { frappe.show_alert({ message: __("Nessun testo da copiare"), indicator: "orange" }); return; }
    frappe.utils.copy_to_clipboard(text);
    frappe.show_alert({ message: __("Testo copiato!"), indicator: "green" });
};
