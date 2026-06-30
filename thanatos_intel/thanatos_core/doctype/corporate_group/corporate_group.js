frappe.ui.form.on('Corporate Group', {
    refresh(frm) {
        if (frm.is_new()) return;
        frappe.call({
            method: 'thanatos_intel.ai.corporate_links.graph',
            args: { group: frm.doc.name },
        }).then(r => { if (r.message) frm.get_field('graph_html').$wrapper.html(r.message); });
    }
});
