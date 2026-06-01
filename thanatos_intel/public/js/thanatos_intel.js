// Thanatos Intel App JS

console.log('Thanatos Intel App loaded');

// Global utilities
window.thanatos_intel = {
    format_currency: function(value, decimals = 2) {
        return parseFloat(value).toLocaleString('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        });
    },

    format_percentage: function(value, decimals = 2) {
        return parseFloat(value).toFixed(decimals) + '%';
    },

    get_verdict_color: function(is_liquidizable) {
        return is_liquidizable ? '#28a745' : '#dc3545';
    },

    get_verdict_icon: function(is_liquidizable) {
        return is_liquidizable ? '✅' : '❌';
    }
};
