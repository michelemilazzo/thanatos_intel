frappe.ui.form.on('Token Liquidity Test', {
    refresh: function (frm) {
        // Add custom buttons
        frm.add_custom_button('Run Test Now', function () {
            if (!frm.doc.token_address) {
                frappe.msgprint('Please enter a token address');
                return;
            }

            frappe.call({
                method: 'thanatos_intel.crypto_liquidity_test.doctype.token_liquidity_test.token_liquidity_test.run_quick_test',
                args: {
                    token_address: frm.doc.token_address,
                    blockchain: frm.doc.blockchain || 'Polygon',
                    amount: frm.doc.test_amount || 100
                },
                callback: function (r) {
                    if (r.message) {
                        const result = r.message;

                        // Update form fields
                        frm.set_value('token_symbol', result.symbol);
                        frm.set_value('token_name', result.name);
                        frm.set_value('token_price_usd', result.price);
                        frm.set_value(
                            'pool_liquidity_usd',
                            result.liquidity
                        );
                        frm.set_value('volume_24h_usd', result.volume_24h);
                        frm.set_value(
                            'output_theoretical',
                            frm.doc.test_amount * result.price
                        );
                        frm.set_value(
                            'estimated_slippage_pct',
                            result.slippage_pct
                        );
                        frm.set_value(
                            'output_real',
                            frm.doc.test_amount *
                                result.price *
                                (1 - result.slippage_pct / 100)
                        );
                        frm.set_value(
                            'liquidity_status',
                            result.liquidity_status
                        );
                        frm.set_value(
                            'is_liquidizable',
                            result.is_liquidizable
                        );
                        frm.set_value(
                            'risk_assessment',
                            result.risk_assessment
                        );
                        frm.set_value(
                            'data_sources',
                            result.data_sources
                        );

                        // Show banner with verdict
                        show_verdict_banner(
                            frm,
                            result.is_liquidizable,
                            result.risk_assessment,
                            result.slippage_pct
                        );

                        frappe.msgprint({
                            title: 'Test Complete',
                            message: `<strong>${result.symbol}</strong> - ${result.liquidity_status}<br/>
                        Price: $${result.price.toFixed(2)}<br/>
                        Liquidity: $${(result.liquidity / 1000000).toFixed(1)}M<br/>
                        Slippage: ${result.slippage_pct.toFixed(2)}%`,
                            indicator: result.is_liquidizable
                                ? 'green'
                                : 'red'
                        });
                    }
                }
            });
        });

        // Color code the verdict section
        update_verdict_colors(frm);
    },

    token_address: function (frm) {
        if (frm.doc.token_address) {
            frm.doc.token_address = frm.doc.token_address.toLowerCase();
        }
    },

    blockchain: function (frm) {
        if (frm.doc.blockchain && frm.doc.blockchain !== 'Polygon') {
            frappe.msgprint(
                'Currently only Polygon is supported. More chains coming soon.'
            );
        }
    },

    is_liquidizable: function (frm) {
        update_verdict_colors(frm);
    }
});

function show_verdict_banner(frm, is_liquidizable, assessment, slippage) {
    let color = is_liquidizable ? '#28a745' : '#dc3545';
    let icon = is_liquidizable ? '✅' : '❌';

    let banner = $(`
        <div style="
            background: ${color};
            color: white;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 15px;
            font-weight: bold;
        ">
            ${icon} ${assessment}
            <br/><small>Slippage: ${slippage.toFixed(2)}%</small>
        </div>
    `);

    frm.$wrapper.find('.form-layout').prepend(banner);
}

function update_verdict_colors(frm) {
    const riskField = frm.fields_dict.risk_assessment;

    if (riskField) {
        const $field = riskField.$wrapper;

        if (frm.doc.is_liquidizable) {
            $field.css('border-left', '4px solid #28a745');
        } else {
            $field.css('border-left', '4px solid #dc3545');
        }
    }
}
