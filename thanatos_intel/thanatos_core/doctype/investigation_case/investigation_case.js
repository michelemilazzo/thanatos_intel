frappe.ui.form.on('Investigation Case', {
    refresh(frm) {
        ThanatosPipeline.render(frm, 'get_case_pipeline');

        // Badge stato caso
        const colors = {
            'Open': 'blue', 'In Progress': 'yellow', 'Completed': 'green',
            'Closed': 'darkgrey', 'Archived': 'darkgrey', 'On Hold': 'orange'
        };
        if (frm.doc.case_status) {
            frm.page.set_indicator(frm.doc.case_status, colors[frm.doc.case_status] || 'grey');
        }
    },
    after_save(frm) {
        ThanatosPipeline.render(frm, 'get_case_pipeline');
    }
});
