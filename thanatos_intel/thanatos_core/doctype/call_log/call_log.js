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
            }
        }
    },

    speaker_a_label(frm) { refreshTranscript(frm); },
    speaker_b_label(frm) { refreshTranscript(frm); },
});

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
