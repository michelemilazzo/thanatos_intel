frappe.ui.form.on('Soggetto', {
    refresh(frm) {
        if (frm.is_new()) { frm.get_field('scheda_html').$wrapper.html(''); return; }
        frappe.call({
            method: 'thanatos_intel.thanatos_core.party.person_card',
            args: { soggetto: frm.doc.name },
        }).then(r => {
            if (r.message) frm.get_field('scheda_html').$wrapper.html(r.message);
        });
    }
});
