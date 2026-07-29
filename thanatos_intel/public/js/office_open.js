// Apre gli allegati Office (docx...) del caso nell'editor Collabora online.
frappe.ui.form.on("Investigation Case", {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__("Apri documento in Office"), function () {
      frappe.db.get_list("File", {
        filters: {
          attached_to_doctype: "Investigation Case",
          attached_to_name: frm.doc.name,
        },
        fields: ["name", "file_name"],
        limit: 0,
      }).then((rows) => {
        const editable = (rows || []).filter((r) =>
          /\.(docx|odt|doc|rtf|xlsx|ods|pptx|odp)$/i.test(r.file_name || "")
        );
        if (!editable.length) {
          frappe.msgprint(__("Nessun documento Office allegato a questo caso."));
          return;
        }
        if (editable.length === 1) {
          window.open("/office?file=" + encodeURIComponent(editable[0].name), "_blank");
          return;
        }
        const d = new frappe.ui.Dialog({
          title: __("Scegli documento"),
          fields: [{
            fieldname: "f", fieldtype: "Select", label: __("Documento"),
            options: editable.map((r) => r.file_name).join("\n"),
          }],
          primary_action_label: __("Apri online"),
          primary_action(v) {
            const pick = editable.find((r) => r.file_name === v.f);
            if (pick) window.open("/office?file=" + encodeURIComponent(pick.name), "_blank");
            d.hide();
          },
        });
        d.show();
      });
    }, __("Documenti"));
  },
});
