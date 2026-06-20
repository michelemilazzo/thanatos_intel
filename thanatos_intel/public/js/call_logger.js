/**
 * Dialog "Registra Chiamata" richiamabile da qualsiasi form Thanatos.
 * Uso: window.thanatos.logCall({ linked_case, linked_client, linked_intel_lead,
 *                                 caller_name, caller_number, linked_contact })
 */
window.thanatos = window.thanatos || {};

window.thanatos.logCall = function (defaults = {}) {
    let started = null;
    let timerInterval = null;

    const d = new frappe.ui.Dialog({
        title: __("Registra Chiamata"),
        size: "large",
        fields: [
            {
                fieldname: "direction",
                fieldtype: "Select",
                label: __("Direzione"),
                options: ["Entrante", "Uscente"],
                default: defaults.direction || "Entrante",
                reqd: 1,
                in_list_view: 1,
            },
            {
                fieldname: "outcome",
                fieldtype: "Select",
                label: __("Esito"),
                options: ["Risposta", "Non risposto", "Occupato", "Messaggio vocale", "Richiamato", "Annullato"],
                default: "Risposta",
                reqd: 1,
            },
            { fieldname: "cb1", fieldtype: "Column Break" },
            {
                fieldname: "called_at",
                fieldtype: "Datetime",
                label: __("Data/ora"),
                default: frappe.datetime.now_datetime(),
                reqd: 1,
            },
            {
                fieldname: "handled_by",
                fieldtype: "Link",
                label: __("Gestita da"),
                options: "User",
                default: frappe.session.user,
            },
            { fieldname: "sb_who", fieldtype: "Section Break", label: __("Interlocutore") },
            {
                fieldname: "caller_name",
                fieldtype: "Data",
                label: __("Nome"),
                default: defaults.caller_name || "",
            },
            {
                fieldname: "caller_number",
                fieldtype: "Data",
                label: __("Numero"),
                default: defaults.caller_number || "",
            },
            { fieldname: "cb2", fieldtype: "Column Break" },
            {
                fieldname: "linked_contact",
                fieldtype: "Link",
                label: __("Contatto rubrica"),
                options: "Intelligence Contact",
                default: defaults.linked_contact || "",
            },
            {
                fieldname: "linked_client",
                fieldtype: "Link",
                label: __("Cliente"),
                options: "Investigation Client",
                default: defaults.linked_client || "",
            },
            { fieldname: "sb_dur", fieldtype: "Section Break", label: __("Durata") },
            {
                fieldname: "timer_html",
                fieldtype: "HTML",
                options: `<div style="display:flex;align-items:center;gap:12px;padding:4px 0">
                  <span id="call-timer" style="font-size:28px;font-family:monospace;font-weight:bold;color:#C8A96E;min-width:90px">0:00</span>
                  <button class="btn btn-xs btn-default" id="btn-start-timer">▶ Avvia</button>
                  <button class="btn btn-xs btn-default" id="btn-stop-timer" disabled>⏹ Stop</button>
                </div>`,
            },
            {
                fieldname: "duration_minutes",
                fieldtype: "Int",
                label: __("Minuti"),
                default: defaults.duration_minutes || 0,
            },
            { fieldname: "cb3", fieldtype: "Column Break" },
            {
                fieldname: "duration_seconds",
                fieldtype: "Int",
                label: __("Secondi"),
                default: 0,
            },
            {
                fieldname: "recording_url",
                fieldtype: "Data",
                label: __("URL registrazione"),
                default: defaults.recording_url || "",
            },
            { fieldname: "sb_links", fieldtype: "Section Break", label: __("Collega a") },
            {
                fieldname: "linked_case",
                fieldtype: "Link",
                label: __("Pratica"),
                options: "Investigation Case",
                default: defaults.linked_case || "",
            },
            {
                fieldname: "linked_intel_lead",
                fieldtype: "Link",
                label: __("Intel Lead"),
                options: "Intel Lead",
                default: defaults.linked_intel_lead || "",
            },
            { fieldname: "cb4", fieldtype: "Column Break" },
            {
                fieldname: "linked_appointment",
                fieldtype: "Link",
                label: __("Appuntamento"),
                options: "Investigation Appointment",
                default: defaults.linked_appointment || "",
            },
            { fieldname: "sb_notes", fieldtype: "Section Break", label: __("Note") },
            {
                fieldname: "summary",
                fieldtype: "Small Text",
                label: __("Riassunto"),
                placeholder: __("Di cosa si è parlato…"),
            },
            {
                fieldname: "action_items",
                fieldtype: "Small Text",
                label: __("Azioni di follow-up"),
                placeholder: __("Es: richiamare entro venerdì, inviare documento X…"),
            },
        ],
        primary_action_label: __("Salva Chiamata"),
        primary_action(values) {
            stopTimer();
            frappe.call({
                method: "frappe.client.insert",
                args: {
                    doc: {
                        doctype: "Call Log",
                        called_at: values.called_at,
                        direction: values.direction,
                        outcome: values.outcome,
                        handled_by: values.handled_by,
                        caller_name: values.caller_name || "",
                        caller_number: values.caller_number || "",
                        linked_contact: values.linked_contact || "",
                        linked_client: values.linked_client || "",
                        linked_case: values.linked_case || "",
                        linked_intel_lead: values.linked_intel_lead || "",
                        linked_appointment: values.linked_appointment || "",
                        duration_minutes: parseInt(values.duration_minutes) || 0,
                        duration_seconds: parseInt(values.duration_seconds) || 0,
                        recording_url: values.recording_url || "",
                        summary: values.summary || "",
                        action_items: values.action_items || "",
                    },
                },
                freeze: true,
                freeze_message: __("Salvataggio…"),
                callback(r) {
                    if (r.message) {
                        frappe.show_alert({ message: __("Chiamata registrata: {0}", [r.message.name]), indicator: "green" });
                        d.hide();
                        if (defaults.onSuccess) defaults.onSuccess(r.message);
                    }
                },
            });
        },
    });

    d.show();

    // Timer
    function formatTime(sec) {
        const m = Math.floor(sec / 60), s = sec % 60;
        return `${m}:${s.toString().padStart(2, "0")}`;
    }

    function startTimer() {
        started = Date.now();
        const $timer = document.getElementById("call-timer");
        const $start = document.getElementById("btn-start-timer");
        const $stop = document.getElementById("btn-stop-timer");
        if ($start) $start.disabled = true;
        if ($stop) $stop.disabled = false;
        timerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - started) / 1000);
            if ($timer) $timer.textContent = formatTime(elapsed);
        }, 1000);
    }

    function stopTimer() {
        if (!started) return;
        clearInterval(timerInterval);
        const elapsed = Math.floor((Date.now() - started) / 1000);
        d.set_value("duration_minutes", Math.floor(elapsed / 60));
        d.set_value("duration_seconds", elapsed % 60);
        started = null;
    }

    setTimeout(() => {
        const $start = document.getElementById("btn-start-timer");
        const $stop = document.getElementById("btn-stop-timer");
        if ($start) $start.addEventListener("click", startTimer);
        if ($stop) $stop.addEventListener("click", stopTimer);
    }, 300);

    d.onhide = () => { clearInterval(timerInterval); };
};
