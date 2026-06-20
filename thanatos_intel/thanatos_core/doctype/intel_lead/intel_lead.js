frappe.ui.form.on("Intel Lead", {
    refresh(frm) {
        renderChat(frm);

        if (!frm.is_new()) {
            if (frm.doc.source_type === "WhatsApp") {
                frm.add_custom_button(__("Rispondi su WhatsApp"), () => openReplyDialog(frm));
            }

            frm.add_custom_button(__("Riassegna"), () => openReassignDialog(frm), __("Azioni"));

            if (frm.doc.status !== "Promosso a Caso" && frm.doc.status !== "Archiviato") {
                frm.add_custom_button(__("Promuovi a Caso"), () => openPromoteDialog(frm), __("Azioni"))
                    .addClass("btn-primary");
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
        }
    },
});

// ─── Promote to case ────────────────────────────────────────────────────────

function openPromoteDialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Promuovi a Caso investigativo"),
        fields: [
            {
                fieldname: "case_title",
                fieldtype: "Data",
                label: __("Titolo pratica"),
                default: `[${frm.doc.source_type}] ${frm.doc.source_name || frm.doc.source_identifier || "Lead"}`,
            },
            { fieldname: "case_type", fieldtype: "Link", label: __("Tipo pratica"), options: "Case Type" },
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
                    if (r.message?.case) {
                        frm.reload_doc();
                        frappe.show_alert({ message: __("Pratica {0} creata", [r.message.case]), indicator: "green" });
                        setTimeout(() => frappe.set_route("Form", "Investigation Case", r.message.case), 900);
                    }
                },
            });
        },
    });
    d.show();
}

// ─── Reassign ────────────────────────────────────────────────────────────────

function openReassignDialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Riassegna conversazione"),
        fields: [
            {
                fieldname: "new_user",
                fieldtype: "Link",
                label: __("Assegna a"),
                options: "User",
                reqd: 1,
                default: frm.doc.assigned_to,
            },
            {
                fieldname: "note",
                fieldtype: "Small Text",
                label: __("Nota per l'operatore (opzionale)"),
            },
        ],
        primary_action_label: __("Trasferisci"),
        primary_action({ new_user, note }) {
            d.hide();
            frappe.call({
                method: "thanatos_intel.ingest.whatsapp_send.reassign_lead",
                args: { lead_name: frm.doc.name, new_user, note: note || "" },
                freeze: true,
                callback(r) {
                    if (r.message?.ok) {
                        frappe.show_alert({ message: __("Lead trasferito a {0}", [new_user]), indicator: "green" });
                        frm.reload_doc();
                    }
                },
            });
        },
    });
    d.show();
}

// ─── WhatsApp Reply ──────────────────────────────────────────────────────────

async function openReplyDialog(frm) {
    const hoursAgo = frm.doc.last_message_at
        ? (Date.now() - new Date(frm.doc.last_message_at).getTime()) / 3_600_000
        : 999;
    const expired = hoursAgo > 24;

    // Carica template disponibili
    let templates = [];
    try {
        const r = await frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "WhatsApp Template",
                filters: { is_active: 1 },
                fields: ["name", "template_name", "body_text", "category", "meta_template_name"],
                limit: 50,
            },
        });
        templates = r.message || [];
    } catch (e) {}

    const templateOptions = templates.length
        ? [{ value: "", label: __("— Nessun template —") }, ...templates.map(t => ({ value: t.name, label: `${t.template_name} (${t.category})` }))]
        : [];

    const warningHtml = expired
        ? `<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:8px 12px;margin-bottom:10px;font-size:12px;color:#856404">
             ⚠ Finestra 24h scaduta — Meta richiede un <strong>template approvato</strong>.
             Seleziona un template con "Nome Meta" configurato.
           </div>`
        : "";

    const d = new frappe.ui.Dialog({
        title: __("Rispondi a {0}", [frm.doc.source_name || frm.doc.source_identifier]),
        size: "large",
        fields: [
            { fieldname: "warning_html", fieldtype: "HTML", options: warningHtml },
            { fieldname: "to_number", fieldtype: "Data", label: __("A"), read_only: 1, default: frm.doc.source_identifier },
            ...(templateOptions.length ? [{
                fieldname: "template",
                fieldtype: "Select",
                label: __("Template rapido"),
                options: templateOptions.map(o => o.label),
            }] : []),
            {
                fieldname: "message_text",
                fieldtype: "Small Text",
                label: __("Messaggio"),
                reqd: 1,
                placeholder: __("Scrivi il tuo messaggio…"),
            },
            { fieldname: "char_count", fieldtype: "HTML", options: '<div id="wa-char-count" style="text-align:right;font-size:11px;color:#888">0 / 4096</div>' },
        ],
        primary_action_label: __("Invia su WhatsApp"),
        primary_action({ message_text, template }) {
            if (!message_text?.trim()) { frappe.msgprint(__("Inserisci un messaggio.")); return; }
            d.disable_primary_action();
            frappe.call({
                method: "thanatos_intel.ingest.whatsapp_send.send_reply",
                args: { lead_name: frm.doc.name, message_text: message_text.trim() },
                freeze: true,
                freeze_message: __("Invio in corso…"),
                callback(r) {
                    d.enable_primary_action();
                    if (r.message?.ok) {
                        frappe.show_alert({ message: __("Inviato!"), indicator: "green" });
                        d.hide();
                        frm.reload_doc();
                    }
                },
                error() { d.enable_primary_action(); },
            });
        },
    });
    d.show();

    // Contatore caratteri
    const $ta = d.$body.find("textarea[data-fieldname='message_text']");
    $ta.on("input", () => {
        d.$body.find("#wa-char-count").text(`${$ta.val().length} / 4096`);
    });

    // Riempi dal template selezionato
    if (templateOptions.length) {
        const $sel = d.$body.find("select[data-fieldname='template']");
        $sel.on("change", function () {
            const label = $(this).val();
            const tpl = templates.find(t => `${t.template_name} (${t.category})` === label);
            if (tpl) {
                const ctx = {
                    nome: frm.doc.source_name || frm.doc.source_identifier || "",
                    numero_pratica: frm.doc.linked_case || "",
                    data: frappe.datetime.nowdate(),
                };
                let text = tpl.body_text || "";
                Object.entries(ctx).forEach(([k, v]) => { text = text.replaceAll(`{{${k}}}`, v); });
                d.set_value("message_text", text);
                $ta.trigger("input");
            }
        });
    }
}

// ─── Chat bubbles ────────────────────────────────────────────────────────────

function renderChat(frm) {
    if (frm.doc.source_type !== "WhatsApp") return;
    const msgs = frm.doc.messages || [];

    const statusIcon = { Inviato: "✓", Consegnato: "✓✓", Letto: "✓✓", Fallito: "✗" };
    const statusColor = { Letto: "#4FC3F7", Fallito: "#ef5350" };

    const bubbles = msgs.map(m => {
        const isOut = m.direction === "Outbound";
        const align = isOut ? "flex-end" : "flex-start";
        const bg = isOut ? "#C8A96E" : "#1e2435";
        const color = isOut ? "#0A0E1A" : "#e8e8e8";
        const time = m.sent_at ? frappe.datetime.str_to_user(m.sent_at) : "";
        const st = m.status || "";
        const stIcon = isOut ? `<span style="color:${statusColor[st] || '#aaa'};font-size:11px"> ${statusIcon[st] || ""}  ${st}</span>` : "";
        const media = m.media_url
            ? `<div style="margin-top:4px"><a href="${m.media_url}" target="_blank" style="color:inherit;font-size:11px;opacity:.75">📎 Media</a></div>` : "";
        return `<div style="display:flex;justify-content:${align};margin:4px 0">
          <div style="max-width:72%;background:${bg};color:${color};border-radius:12px;padding:8px 12px;font-size:13px;line-height:1.5">
            ${frappe.utils.escape_html(m.content || "")}${media}
            <div style="font-size:10px;opacity:.55;margin-top:4px;text-align:right">${time}${stIcon}</div>
          </div>
        </div>`;
    }).join("");

    frm.set_df_property("chat_html", "options",
        `<div style="background:#0d1117;border-radius:8px;padding:12px;max-height:440px;overflow-y:auto" id="wa-chat-box">
           ${bubbles || '<div style="color:#555;text-align:center;padding:24px;font-size:13px">Nessun messaggio nel thread</div>'}
         </div>`
    );
    frm.refresh_field("chat_html");
    setTimeout(() => { const b = document.getElementById("wa-chat-box"); if (b) b.scrollTop = b.scrollHeight; }, 120);
}
