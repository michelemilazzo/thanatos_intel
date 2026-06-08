/**
 * Pipeline widget — stepper visuale per desk.
 * Usato in Investigation Case e Diplomatic Eligibility Case.
 *
 * Uso:
 *   ThanatosPipeline.render(frm, 'get_case_pipeline');
 *   ThanatosPipeline.render(frm, 'get_ddd_pipeline', 'ddd_case_name_field');
 */
window.ThanatosPipeline = (function () {

    const STATUS_ICON = { done: '✓', current: '▶', pending: '○', blocked: '✗' };
    const STATUS_COLOR = {
        done: '#2ecc71', current: '#C8A96E', pending: '#7A8294', blocked: '#e74c3c'
    };
    const ACTOR_BADGE = { operator: 'Operatore', client: 'Cliente' };

    function render(frm, api_method, name_arg) {
        if (frm.is_new()) return;
        const arg_name = name_arg ? frm.doc[name_arg] : frm.doc.name;
        if (!arg_name) return;

        frappe.call({
            method: 'thanatos_intel.pipeline.pipeline.' + api_method,
            args: api_method === 'get_ddd_pipeline'
                ? { ddd_case_name: arg_name }
                : { case_name: arg_name },
            callback(r) {
                if (!r.message || !r.message.length) return;
                _inject(frm, r.message);
            }
        });
    }

    function _inject(frm, steps) {
        const wrapper_id = 'tx-pipeline-widget';
        $(frm.layout.wrapper).find('#' + wrapper_id).remove();

        const current = steps.find(s => s.status === 'current');
        const done_count = steps.filter(s => s.status === 'done').length;
        const pct = Math.round(done_count / steps.length * 100);

        let html = `
<div id="${wrapper_id}" style="
    background:#111729;border:1px solid #1F2842;border-radius:6px;
    padding:20px 24px;margin:16px 0;font-family:-apple-system,sans-serif;">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
    <span style="color:#C8A96E;font-family:Georgia,serif;font-size:13px;letter-spacing:2px;text-transform:uppercase">
      Pipeline pratica
    </span>
    <span style="color:#7A8294;font-size:11px">${done_count}/${steps.length} step completati</span>
  </div>
  <div style="background:#1F2842;height:4px;border-radius:2px;margin-bottom:18px">
    <div style="background:#C8A96E;height:4px;border-radius:2px;width:${pct}%;transition:width .4s"></div>
  </div>`;

        steps.forEach((s, i) => {
            const icon = STATUS_ICON[s.status] || '○';
            const color = STATUS_COLOR[s.status] || '#7A8294';
            const is_current = s.status === 'current';
            const actor_label = ACTOR_BADGE[s.actor] || s.actor;
            const actor_color = s.actor === 'client' ? '#6A9FD8' : '#C8A96E';

            html += `
<div style="display:flex;gap:14px;align-items:flex-start;padding:10px 0;
     border-bottom:1px solid #1A2035;${is_current ? 'background:rgba(200,169,110,.04);margin:0 -12px;padding:10px 12px;border-radius:4px' : ''}">
  <div style="width:24px;height:24px;border-radius:50%;background:${is_current ? '#C8A96E22' : 'transparent'};
       border:2px solid ${color};display:flex;align-items:center;justify-content:center;
       color:${color};font-size:11px;flex-shrink:0;margin-top:2px">${icon}</div>
  <div style="flex:1;min-width:0">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span style="color:${s.status === 'done' ? '#7A8294' : '#E8E9F0'};font-size:13px;
            ${s.status === 'done' ? 'text-decoration:line-through' : ''};font-weight:${is_current ? '600' : '400'}">
        ${s.label}
      </span>
      <span style="font-size:9px;padding:2px 7px;border-radius:10px;
            background:${actor_color}22;color:${actor_color};letter-spacing:1px;text-transform:uppercase">
        ${actor_label}
      </span>
    </div>
    ${is_current && s.description ? `<div style="color:#7A8294;font-size:11px;margin-top:3px">${s.description}</div>` : ''}
    ${is_current && s.desk_url && s.actor === 'operator' ? `
    <a href="${s.desk_url}" style="display:inline-block;margin-top:8px;padding:5px 12px;
       background:#C8A96E;color:#0A0E1A;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;
       text-decoration:none;border-radius:2px">Vai ›</a>` : ''}
  </div>
</div>`;
        });

        html += '</div>';

        // Inserisce dopo il primo fieldset o all'inizio del body
        const $target = $(frm.layout.wrapper).find('.form-page').first();
        $target.prepend(html);
    }

    return { render };
})();
