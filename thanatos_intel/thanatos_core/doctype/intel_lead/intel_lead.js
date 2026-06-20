frappe.ui.form.on("Intel Lead", {
    refresh(frm) {
        renderChat(frm);

        if (!frm.is_new() && frm.doc.source_type === "WhatsApp") {
            addReplyButton(frm);
        }

        if (!frm.is_new() && frm.doc.status !== "Promosso a Caso" && frm.doc.status !== "Archiviato") {
            frm.add_custom_button(__("Promuovi a Caso"), () => {
                const d = new frappe.ui.Dialog({
                    title: __("Promuovi a Caso investigativo"),
                    fields: [
                        {
                            fieldname: "case_title",
                            fieldtype: "Data",
                            label: __("Titolo pratica"),
                            default: `[${frm.doc.source_type}] ${frm.doc.source_name || frm.doc.source_identifier || "Lead"}`,
                        },
                        {
                            fieldname: "case_type",
                            fieldtype: "Link",
                            label: __("Tipo pratica"),
                            options: "Case Type",
                        },
                    ],
                    primary_action_label: __("Crea Pratica"),
                    primary_action({ case_title, case_type }) {
                        d.hide();
                        frappe.call({
                            method: "promote_to_case",
                            doc: frm.doc,
                            args: { case_title, case_type },
                            freeze: true,
                            freeze_message: __("Creazione pratica…"),
                            callback(r) {
                                if (r.message && r.message.case) {
                                    frm.reload_doc();
                                    frappe.show_alert({ message: __("Pratica {0} creata", [r.message.case]), indicator: "green" });
                                    setTimeout(() => frappe.set_route("Form", "Investigation Case", r.message.case), 1000);
                                }
                            },
                        });
                    },
                });
                d.show();
            }, __("Azioni")).addClass("btn-primary");

            frm.add_custom_button(__("Archivia"), () => {
                frappe.confirm(__("Archiviare questo lead?"), () => {
                    frm.set_value("status", "Archiviato");
                    frm.save();
                });
            }, __("Azioni"));
        }

        if (frm.doc.linked_case) {
            frm.add_custom_button(__("Apri Pratica"), () => {
                frappe.set_route("Form", "Investigation Case", frm.doc.linked_case);
            });
        }
    },
});

function addReplyButton(frm) {
    frm.add_custom_button(__("Rispondi su WhatsApp"), () => openReplyDialog(frm));
}

function openReplyDialog(frm) {
    const hoursAgo = frm.doc.last_message_at
        ? (Date.now() - new Date(frm.doc.last_message_at).getTime()) / 3600000
        : 999;
    const expired = hoursAgo > 24;
    const warning = expired
        ? `<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:8px 12px;margin-bottom:10px;font-size:12px;color:#856404">
             ⚠ Sono passate più di 24h dall'ultimo messaggio. Meta API permette solo <strong>template approvati</strong> fuori dalla finestra di 24h.
           </div>`
        : "";

    const d = new frappe.ui.Dialog({
        title: __("Rispondi a {0}", [frm.doc.source_name || frm.doc.source_identifier]),
        size: "large",
        fields: [
            {
                fieldname: "warning_html",
                fieldtype: "HTML",
                options: warning,
            },
            {
                fieldname: "to_number",
                fieldtype: "Data",
                label: __("A (numero)"),
                read_only: 1,
                default: frm.doc.source_identifier,
            },
            {
                fieldname: "message_text",
                fieldtype: "Small Text",
                label: __("Messaggio"),
                reqd: 1,
                placeholder: __("Scrivi il tuo messaggio…"),
            },
            {
                fieldname: "char_count",
                fieldtype: "HTML",
                options: '<div id="wa-char-count" style="text-align:right;font-size:11px;color:#888">0 / 4096</div>',
            },
        ],
        primary_action_label: __("Invia su WhatsApp"),
        primary_action({ message_text }) {
            if (!message_text || !message_text.trim()) {
                frappe.msgprint(__("Inserisci un messaggio.")); return;
            }
            d.disable_primary_action();
            frappe.call({
                method: "thanatos_intel.ingest.whatsapp_send.send_reply",
                args: { lead_name: frm.doc.name, message_text: message_text.trim() },
                freeze: true,
                freeze_message: __("Invio in corso…"),
                callback(r) {
                    d.enable_primary_action();
                    if (r.message && r.message.ok) {
                        frappe.show_alert({ message: __("Messaggio inviato!"), indicator: "green" });
                        d.hide();
                        frm.reload_doc();
                    }
                },
                error() {
                    d.enable_primary_action();
                },
            });
        },
    });

    d.show();

    // Contatore caratteri
    const $ta = d.$body.find("textarea[data-fieldname='message_text']");
    $ta.on("input", () => {
        const n = $ta.val().length;
        d.$body.find("#wa-char-count").text(`${n} / 4096`);
    });
}

function renderChat(frm) {
    if (frm.doc.source_type !== "WhatsApp") return;
    const msgs = frm.doc.messages || [];
    if (!msgs.length && !frm.doc.content) return;

    const bubbles = msgs.map(m => {
        const isOut = m.direction === "Outbound";
        const align = isOut ? "flex-end" : "flex-start";
        const bg = isOut ? "#C8A96E" : "#1e2435";
        const color = isOut ? "#0A0E1A" : "#e8e8e8";
        const time = m.sent_at ? frappe.datetime.str_to_user(m.sent_at) : "";
        const status = isOut ? ` <span style="font-size:10px;opacity:.6">${m.status || ""}</span>` : "";
        const media = m.media_url
            ? `<div style="margin-top:4px"><a href="${m.media_url}" target="_blank" style="color:inherit;font-size:11px;opacity:.8">📎 Media</a></div>`
            : "";
        return `<div style="display:flex;justify-content:${align};margin:4px 0">
          <div style="max-width:70%;background:${bg};color:${color};border-radius:12px;padding:8px 12px;font-size:13px;line-height:1.4">
            ${frappe.utils.escape_html(m.content || "")}
            ${media}
            <div style="font-size:10px;opacity:.5;margin-top:4px;text-align:right">${time}${status}</div>
          </div>
        </div>`;
    }).join("");

    const html = `
      <div style="background:#0d1117;border-radius:8px;padding:12px;max-height:420px;overflow-y:auto;margin-bottom:8px" id="wa-chat-box">
        ${bubbles || `<div style="color:#666;text-align:center;padding:24px;font-size:13px">Nessun messaggio nel thread</div>`}
      </div>`;

    frm.set_df_property("chat_html", "options", html);
    frm.refresh_field("chat_html");

    // Scroll to bottom
    setTimeout(() => {
        const box = document.getElementById("wa-chat-box");
        if (box) box.scrollTop = box.scrollHeight;
    }, 100);
}
