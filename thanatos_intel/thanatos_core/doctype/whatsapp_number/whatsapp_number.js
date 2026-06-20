frappe.ui.form.on("WhatsApp Number", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Genera QR"), () => showQR(frm));
            frm.add_custom_button(__("Copia webhook URL"), () => {
                const url = `${window.location.origin}/api/method/thanatos_intel.ingest.whatsapp.webhook?number_id=${encodeURIComponent(frm.doc.name)}&token=${encodeURIComponent("***")}`;
                frappe.utils.copy_to_clipboard(url.replace("***", "IL-TUO-TOKEN"));
                frappe.show_alert({ message: __("URL copiato negli appunti"), indicator: "green" });
            });
        }
    },

    phone_number(frm) {
        updatePreview(frm);
    },
    wa_link_text(frm) {
        updatePreview(frm);
    },
});

function updatePreview(frm) {
    const phone = (frm.doc.phone_number || "").replace(/[+ \-]/g, "");
    const text = frm.doc.wa_link_text || "";
    let url = `https://wa.me/${phone}`;
    if (text) url += `?text=${encodeURIComponent(text)}`;
    if (phone.length > 5) {
        frm.set_df_property("qr_preview", "options",
            `<div style="padding:8px">
              <a href="${url}" target="_blank" style="color:#C8A96E;font-size:13px">${url}</a>
             </div>`
        );
        frm.refresh_field("qr_preview");
    }
}

function showQR(frm) {
    frappe.call({
        method: "get_qr_base64",
        doc: frm.doc,
        freeze: true,
        freeze_message: __("Generazione QR…"),
        callback(r) {
            if (!r.message) return;
            const { url, qr, error } = r.message;
            if (error || !qr) {
                frappe.msgprint({ title: __("Errore"), indicator: "red", message: error || __("QR non generato") });
                return;
            }
            const d = new frappe.ui.Dialog({
                title: __("QR Code — {0}", [frm.doc.display_name]),
                size: "small",
            });
            d.$body.html(`
                <div style="text-align:center;padding:16px">
                  <img src="${qr}" style="width:220px;height:220px;border:8px solid white;border-radius:4px;box-shadow:0 2px 12px rgba(0,0,0,.2)">
                  <div style="margin-top:12px;font-size:12px;color:#888;word-break:break-all">${url}</div>
                  <div style="margin-top:12px;display:flex;gap:8px;justify-content:center">
                    <a href="${qr}" download="qr-${frm.doc.name}.png"
                       style="background:#C8A96E;color:#0A0E1A;padding:6px 14px;border-radius:4px;font-weight:bold;font-size:13px;text-decoration:none">
                       ⬇ Scarica PNG
                    </a>
                    <a href="${url}" target="_blank"
                       style="background:#25D366;color:white;padding:6px 14px;border-radius:4px;font-weight:bold;font-size:13px;text-decoration:none">
                       Apri in WhatsApp
                    </a>
                  </div>
                </div>
            `);
            d.show();
        },
    });
}
