frappe.ui.form.on('Diplomatic Eligibility Case', {
    refresh(frm) {
        ThanatosPipeline.render(frm, 'get_ddd_pipeline');

        const colors = {
            'Draft': 'grey', 'Active': 'blue', 'In Analysis': 'yellow',
            'Completed': 'green', 'Rejected': 'red', 'On Hold': 'orange'
        };
        if (frm.doc.status) {
            frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || 'grey');
        }
    },
    after_save(frm) {
        ThanatosPipeline.render(frm, 'get_ddd_pipeline');
    }
});
