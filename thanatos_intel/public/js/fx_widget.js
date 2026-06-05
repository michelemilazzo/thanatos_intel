/*  Thanatos FX widget
 *  Usage in any form/page:
 *    <span data-thanatos-fx="100"></span>
 *    <span data-thanatos-fx-from="EUR" data-thanatos-fx-block="100"></span>
 *
 *  Helper JS programmatic:
 *    thanatos.fx.convert(100, 'USD').then(v => console.log(v))
 *    thanatos.fx.convert_all(100).then(d => console.log(d))
 */
(function(){
  window.thanatos = window.thanatos || {};
  const cache = {rates: null, ts: 0};
  const TTL = 6 * 3600 * 1000;

  function getRates(){
    if(cache.rates && (Date.now() - cache.ts) < TTL) return Promise.resolve(cache.rates);
    return fetch('/api/method/thanatos_intel.thanatos_core.currency.converter.get_rates')
      .then(r => r.json()).then(j => {
        cache.rates = j.message || {}; cache.ts = Date.now();
        return cache.rates;
      });
  }

  function fmt(amount, ccy){
    const s = new Intl.NumberFormat('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}).format(amount);
    const sym = {EUR:'€',USD:'$',GBP:'£',CHF:'CHF',RON:'lei',BGN:'лв',RUB:'₽',
                 UAH:'₴',TRY:'₺',CNY:'¥',JPY:'¥',INR:'₹',AUD:'A$',CAD:'C$',
                 BRL:'R$',ZAR:'R',NOK:'kr',SEK:'kr',DKK:'kr',PLN:'zł',CZK:'Kč',
                 HUF:'Ft',ALL:'L',RSD:'din',AED:'د.إ',SAR:'﷼'}[ccy] || ccy;
    return ['USD','GBP','AUD','CAD','BRL','CHF','EUR'].includes(ccy) ? sym+s : s+' '+sym;
  }

  function convert(amount, toCcy, fromCcy){
    fromCcy = (fromCcy||'EUR').toUpperCase();
    toCcy = (toCcy||'USD').toUpperCase();
    return getRates().then(r => {
      if(!r[fromCcy] || !r[toCcy]) return 0;
      const eur = parseFloat(amount) / r[fromCcy];
      return Math.round(eur * r[toCcy] * 100) / 100;
    });
  }

  function convertAll(eurAmount, ccys){
    const def = ['USD','GBP','CHF','RON','BGN','RUB','UAH','TRY','AED','CNY',
                 'JPY','INR','CAD','PLN','CZK','HUF','ALL'];
    ccys = ccys || def;
    return getRates().then(r => {
      const out = {};
      ccys.forEach(c => {
        c = c.toUpperCase();
        if(r[c]) out[c] = {amount: Math.round(parseFloat(eurAmount)*r[c]*100)/100,
                            formatted: fmt(Math.round(parseFloat(eurAmount)*r[c]*100)/100, c)};
      });
      return out;
    });
  }

  window.thanatos.fx = {convert, convert_all: convertAll, format: fmt, getRates};

  // Auto-render data-thanatos-fx="100" → "$108.00" (USD default)
  function autoRender(){
    document.querySelectorAll('[data-thanatos-fx]:not([data-thanatos-fx-rendered])').forEach(el => {
      const amt = el.getAttribute('data-thanatos-fx');
      const to = el.getAttribute('data-thanatos-fx-to') || 'USD';
      const from = el.getAttribute('data-thanatos-fx-from') || 'EUR';
      convert(amt, to, from).then(v => {
        el.textContent = fmt(v, to);
        el.setAttribute('data-thanatos-fx-rendered','1');
      });
    });
    document.querySelectorAll('[data-thanatos-fx-block]:not([data-rendered])').forEach(el => {
      const amt = el.getAttribute('data-thanatos-fx-block');
      const from = el.getAttribute('data-thanatos-fx-from') || 'EUR';
      const ccys = (el.getAttribute('data-thanatos-fx-ccys')||'').split(',').filter(Boolean);
      Promise.resolve(from === 'EUR' ? parseFloat(amt) : convert(amt, 'EUR', from))
        .then(eur => convertAll(eur, ccys.length ? ccys : null))
        .then(data => {
          const rows = Object.entries(data).map(([c,d]) =>
            `<tr><td style="padding:3px 8px">${c}</td>
             <td style="padding:3px 8px;text-align:right;font-family:monospace">${d.formatted}</td></tr>`
          ).join('');
          el.innerHTML = `<table style="border-collapse:collapse;font-size:12px;border:1px solid #c8a96e">
            <thead><tr style="background:#0A0E1A;color:#c8a96e">
              <th style="padding:4px 8px">Currency</th>
              <th style="padding:4px 8px">Amount</th></tr></thead>
            <tbody>${rows}</tbody></table>`;
          el.setAttribute('data-rendered','1');
        });
    });
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', autoRender);
  else autoRender();
  // re-render on Frappe form refresh
  if(window.frappe && window.frappe.ui) {
    window.frappe.realtime && window.frappe.realtime.on('doc_update', autoRender);
    setInterval(autoRender, 2000);
  }
})();
