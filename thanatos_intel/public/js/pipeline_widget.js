/**
 * Pipeline widget — stepper visuale per desk.
 * Usato in Investigation Case e Diplomatic Eligibility Case.
 * Stile: tema Frappe standard (il branding Thanatos è solo sul portale).
 * Navigazione: ogni step è cliccabile (se ha desk_url), bottoni Indietro/Avanti.
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

    function _navigate(steps, target_idx) {
        const s = steps[target_idx];
        if (!s) return;
        if (s.desk_url) {
            window.location.href = s.desk_url;
        } else {
            frappe.show_alert({message: `Step "${s.label}" — nessuna URL associata (${ACTOR_BADGE[s.actor]||s.actor})`, indicator: 'orange'});
        }
    }

    function _inject(frm, steps) {
        const wrapper_id = 'tx-pipeline-widget';
        $(frm.layout.wrapper).find('#' + wrapper_id).remove();

        const done_count = steps.filter(s => s.status === 'done').length;
        const pct = Math.round(done_count / steps.length * 100);
        const current_idx = steps.findIndex(s => s.status === 'current');
        // Trova precedente/successivo step navigabile (con desk_url)
        let prev_idx = -1, next_idx = -1;
        if (current_idx > 0) {
            for (let i = current_idx - 1; i >= 0; i--) {
                if (steps[i].desk_url) { prev_idx = i; break; }
            }
        }
        if (current_idx >= 0 && current_idx < steps.length - 1) {
            for (let i = current_idx + 1; i < steps.length; i++) {
                if (steps[i].desk_url) { next_idx = i; break; }
            }
        }

        let html = `
<div id="${wrapper_id}" style="
    background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--border-radius-md, 8px);
    padding:16px 20px;margin:16px 0;">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;gap:8px;flex-wrap:wrap">
    <span style="color:var(--text-color);font-size:var(--text-md, 13px);font-weight:600">
      Pipeline pratica
    </span>
    <span style="flex:1"></span>
    <button class="btn btn-xs btn-default" id="tx-pipeline-prev" ${prev_idx<0?'disabled':''} title="Step precedente">← Indietro</button>
    <button class="btn btn-xs btn-default" id="tx-pipeline-next" ${next_idx<0?'disabled':''} title="Step successivo">Avanti →</button>
    <span style="color:var(--text-muted);font-size:var(--text-sm, 11px);margin-left:8px">${done_count}/${steps.length} step completati</span>
  </div>
  <div style="background:var(--control-bg);height:4px;border-radius:2px;margin-bottom:14px">
    <div style="background:var(--primary);height:4px;border-radius:2px;width:${pct}%;transition:width .4s"></div>
  </div>`;

        steps.forEach((s, idx) => {
            const icon = STATUS_ICON[s.status] || '○';
            const color = STATUS_COLOR[s.status] || 'var(--gray-400)';
            const is_current = s.status === 'current';
            const actor_label = ACTOR_BADGE[s.actor] || s.actor;
            const actor_class = s.actor === 'client' ? 'blue' : 'gray';
            const clickable = !!s.desk_url;

            html += `
<div data-step-idx="${idx}" class="tx-pipeline-step ${clickable?'tx-clickable':''}" style="display:flex;gap:12px;align-items:flex-start;padding:9px 0;
     border-bottom:1px solid var(--border-color);${clickable?'cursor:pointer;':''}${is_current ? 'background:var(--bg-light-gray, var(--control-bg));margin:0 -12px;padding:9px 12px;border-radius:var(--border-radius, 4px)' : ''}">
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
      ${clickable?'<span style="font-size:11px;color:var(--text-muted);margin-left:4px">↗</span>':''}
    </div>
    ${is_current && s.description ? `<div style="color:var(--text-muted);font-size:var(--text-sm, 11px);margin-top:3px">${s.description}</div>` : ''}
    ${is_current && s.desk_url && s.actor === 'operator' ? `
    <a href="${s.desk_url}" class="btn btn-primary btn-xs" style="margin-top:8px" onclick="event.stopPropagation()">Vai ›</a>` : ''}
  </div>
</div>`;
        });

        html += '</div>';

        const $target = $(frm.layout.wrapper).find('.form-page').first();
        $target.prepend(html);

        // Eventi click: step + navigation
        const $w = $target.find('#' + wrapper_id);
        $w.find('.tx-clickable').on('click', function(e){
            if($(e.target).is('a, button')) return;
            const idx = parseInt($(this).data('step-idx'));
            _navigate(steps, idx);
        });
        $w.find('#tx-pipeline-prev').on('click', ()=>_navigate(steps, prev_idx));
        $w.find('#tx-pipeline-next').on('click', ()=>_navigate(steps, next_idx));
    }

    return { render };
})();
