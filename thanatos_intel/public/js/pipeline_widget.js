/**
 * Pipeline widget — stepper visuale per desk.
 * Usato in Investigation Case e Diplomatic Eligibility Case.
 * Stile: tema Frappe standard (il branding Thanatos è solo sul portale).
 *
 * Uso:
 *   ThanatosPipeline.render(frm, 'get_case_pipeline');
 *   ThanatosPipeline.render(frm, 'get_ddd_pipeline', 'ddd_case_name_field');
 */
window.ThanatosPipeline = (function () {

    const STATUS_ICON = { done: '✓', current: '▶', pending: '○', blocked: '✗' };
    const STATUS_COLOR = {
        done: 'var(--green-500)', current: 'var(--primary)',
        pending: 'var(--gray-400)', blocked: 'var(--red-500)'
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

        const done_count = steps.filter(s => s.status === 'done').length;
        const pct = Math.round(done_count / steps.length * 100);

        let html = `
<div id="${wrapper_id}" style="
    background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--border-radius-md, 8px);
    padding:16px 20px;margin:16px 0;">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
    <span style="color:var(--text-color);font-size:var(--text-md, 13px);font-weight:600">
      Pipeline pratica
    </span>
    <span style="color:var(--text-muted);font-size:var(--text-sm, 11px)">${done_count}/${steps.length} step completati</span>
  </div>
  <div style="background:var(--control-bg);height:4px;border-radius:2px;margin-bottom:14px">
    <div style="background:var(--primary);height:4px;border-radius:2px;width:${pct}%;transition:width .4s"></div>
  </div>`;

        steps.forEach((s) => {
            const icon = STATUS_ICON[s.status] || '○';
            const color = STATUS_COLOR[s.status] || 'var(--gray-400)';
            const is_current = s.status === 'current';
            const actor_label = ACTOR_BADGE[s.actor] || s.actor;
            const actor_class = s.actor === 'client' ? 'blue' : 'gray';

            html += `
<div style="display:flex;gap:12px;align-items:flex-start;padding:9px 0;
     border-bottom:1px solid var(--border-color);${is_current ? 'background:var(--bg-light-gray, var(--control-bg));margin:0 -12px;padding:9px 12px;border-radius:var(--border-radius, 4px)' : ''}">
  <div style="width:22px;height:22px;border-radius:50%;background:transparent;
       border:2px solid ${color};display:flex;align-items:center;justify-content:center;
       color:${color};font-size:10px;flex-shrink:0;margin-top:2px">${icon}</div>
  <div style="flex:1;min-width:0">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span style="color:${s.status === 'done' ? 'var(--text-muted)' : 'var(--text-color)'};font-size:var(--text-md, 13px);
            ${s.status === 'done' ? 'text-decoration:line-through' : ''};font-weight:${is_current ? '600' : '400'}">
        ${s.label}
      </span>
      <span class="indicator-pill ${actor_class}" style="font-size:10px">${actor_label}</span>
    </div>
    ${is_current && s.description ? `<div style="color:var(--text-muted);font-size:var(--text-sm, 11px);margin-top:3px">${s.description}</div>` : ''}
    ${is_current && s.desk_url && s.actor === 'operator' ? `
    <a href="${s.desk_url}" class="btn btn-primary btn-xs" style="margin-top:8px">Vai ›</a>` : ''}
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
