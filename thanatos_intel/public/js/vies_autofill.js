// VIES autofill — pulsante "🔍 VIES" sul form Investigation Client
// Cerca la P.IVA su VIES e pre-popola ragione sociale, indirizzo, paese.
frappe.ui.form.on("Investigation Client", {
    refresh(frm) {
        if (!frm.doc.vat_number) return;
        _add_vies_button(frm);
    },
    vat_number(frm) {
        _add_vies_button(frm);
    },
});

function _add_vies_button(frm) {
    frm.remove_custom_button("🔍 VIES");
    if (!frm.doc.vat_number) return;
    frm.add_custom_button("🔍 VIES", () => _run_lookup(frm));
}

function _run_lookup(frm) {
    const vat = (frm.doc.vat_number || "").trim();
    if (!vat) {
        frappe.msgprint("Inserisci prima la partita IVA.");
        return;
    }
    frappe.show_progress("Ricerca VIES...", 50, 100);
    frappe.call({
        method: "thanatos_intel.integrations.vies_lookup.lookup",
        args: { vat_number: vat },
        callback(r) {
            frappe.hide_progress();
            const d = r.message || {};
            if (!d.ok) {
                frappe.msgprint({
                    title: "VIES",
                    message: d.error || "Nessun dato trovato.",
                    indicator: "orange",
                });
                return;
            }
            _apply(frm, d);
        },
        error() { frappe.hide_progress(); },
    });
}

function _apply(frm, d) {
    const changed = [];

    function _set(field, val) {
        if (val && frm.doc[field] !== val) {
            frm.set_value(field, val);
            changed.push(field);
        }
    }

    if (!frm.doc.client_name || frm.doc.client_name === frm.doc.vat_number) {
        _set("client_name", d.company_name);
    }

    // componi indirizzo
    const parts = [d.address_line1, d.pincode && d.city ? `${d.pincode} ${d.city}` : d.city].filter(Boolean);
    if (parts.length) _set("address", parts.join("\n"));

    // paese: mappa country_code → nome Frappe
    if (d.country_code) {
        frappe.db.get_value("Country", { "code": d.country_code.toLowerCase() }, "name")
            .then(r => {
                if (r && r.message && r.message.name) _set("country", r.message.name);
            });
    }

    const offline = d.offline ? " (dati approssimativi — nodo VIES offline)" : "";
    const valid = d.valid ? "✅ Valida" : "⚠️ Non validata da VIES";
    frappe.show_alert({
        message: `${valid} — ${d.company_name}${offline}`,
        indicator: d.valid ? "green" : "orange",
    }, 6);
}
