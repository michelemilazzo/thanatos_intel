frappe.ui.form.on("WhatsApp Template", {
    refresh(frm) {
        updatePreview(frm);
    },
    body_text(frm) { updatePreview(frm); },
    header_text(frm) { updatePreview(frm); },
    footer_text(frm) { updatePreview(frm); },
});

function updatePreview(frm) {
    const header = frm.doc.header_text
        ? `<div style="font-weight:bold;margin-bottom:6px;font-size:14px">${frappe.utils.escape_html(frm.doc.header_text)}</div>`
        : "";
    const body = (frm.doc.body_text || "")
        .replace(/\{\{(\w+)\}\}/g, '<span style="background:#C8A96E22;color:#C8A96E;border-radius:3px;padding:1px 4px">{{$1}}</span>')
        .replace(/\n/g, "<br>");
    const footer = frm.doc.footer_text
        ? `<div style="color:#888;font-size:11px;margin-top:6px">${frappe.utils.escape_html(frm.doc.footer_text)}</div>`
        : "";
    frm.set_df_property("preview_html", "options", `
        <div style="background:#0d1117;border-radius:12px;padding:14px 16px;max-width:320px;font-size:13px;color:#e8e8e8;line-height:1.5;margin:8px 0">
          ${header}${body}${footer}
          <div style="font-size:10px;color:#555;margin-top:8px;text-align:right">${frm.doc.language || "it"} · ${frm.doc.category || ""}</div>
        </div>
    `);
    frm.refresh_field("preview_html");
}
