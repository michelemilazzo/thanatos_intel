frappe.pages["centralino"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: "Centralino",
        single_column: true,
    });
    new CentralinoPage(wrapper);
};

class CentralinoPage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.activeLead = null;
        this.filter = "all";
        this.search = "";
        this.operatorStatus = "online";
        this._searchTimer = null;

        this._injectStyles();
        this._render();
        this._bindEvents();
        this._subscribeRealtime();
        this.loadConversations();
    }

    // ── Layout ────────────────────────────────────────────────────────────────

    _render() {
        $(this.wrapper).find(".layout-main-section").html(`
<div class="ctlno-root">
  <div class="ctlno-header">
    <div class="ctlno-header-left">
      <span class="ctlno-logo">📞</span>
      <span class="ctlno-title">Centralino</span>
    </div>
    <div class="ctlno-header-center">
      <button class="ctlno-filter act" data-f="all">Tutte</button>
      <button class="ctlno-filter" data-f="mine">Mie</button>
      <button class="ctlno-filter" data-f="unassigned">Non assegnate</button>
      <button class="ctlno-filter" data-f="closed">Chiuse</button>
      <button class="ctlno-filter" data-f="calls">📞 Chiamate</button>
    </div>
    <div class="ctlno-header-right">
      <button class="ctlno-deviazione" id="ctlno-deviazione" title="Impostazioni deviazione chiamate">⚙ Deviazione</button>
      <input class="ctlno-search" id="ctlno-search" placeholder="🔍 Cerca...">
      <div class="ctlno-status-wrap">
        <button class="ctlno-status-btn online" id="ctlno-status-btn">● Online ▾</button>
        <div class="ctlno-status-menu" id="ctlno-status-menu">
          <a class="ctlno-sm-item" data-s="online">● Online</a>
          <a class="ctlno-sm-item" data-s="busy">◉ Occupato</a>
          <a class="ctlno-sm-item" data-s="offline">○ Offline</a>
        </div>
      </div>
    </div>
  </div>
  <div class="ctlno-body">
    <div class="ctlno-sidebar" id="ctlno-sidebar">
      <div class="ctlno-list-wrap" id="ctlno-list"></div>
    </div>
    <div class="ctlno-chat-area" id="ctlno-chat-area">
      <div class="ctlno-empty-state">
        <div style="font-size:48px;margin-bottom:16px">💬</div>
        <div style="color:#A4A9BC;font-size:14px;letter-spacing:1px">Seleziona una conversazione</div>
      </div>
    </div>
  </div>
</div>`);
    }

    _bindEvents() {
        const root = this.wrapper;

        // Filtri
        $(root).on("click", ".ctlno-filter", (e) => {
            $(root).find(".ctlno-filter").removeClass("act");
            $(e.currentTarget).addClass("act");
            this.filter = $(e.currentTarget).data("f");
            this.loadConversations();
        });

        // Impostazioni deviazione chiamate -> form WhatsApp Number
        $(root).on("click", "#ctlno-deviazione", () => {
            frappe.db.get_value("WhatsApp Number", {"is_active": 1}, "name").then((r) => {
                const n = r && r.message && r.message.name;
                if (n) frappe.set_route("Form", "WhatsApp Number", n);
                else frappe.set_route("List", "WhatsApp Number");
            });
        });

        // Ricerca
        $(root).on("input", "#ctlno-search", (e) => {
            clearTimeout(this._searchTimer);
            this._searchTimer = setTimeout(() => {
                this.search = e.target.value.trim();
                this.loadConversations();
            }, 350);
        });

        // Status operatore
        $(root).on("click", "#ctlno-status-btn", (e) => {
            e.stopPropagation();
            $(root).find("#ctlno-status-menu").toggleClass("open");
        });
        $(document).on("click.centralino", () => {
            $(root).find("#ctlno-status-menu").removeClass("open");
        });
        $(root).on("click", ".ctlno-sm-item", (e) => {
            const s = $(e.currentTarget).data("s");
            this._setStatus(s);
        });

        // Click su conversazione
        $(root).on("click", ".ctlno-conv-item", (e) => {
            const name = $(e.currentTarget).data("name");
            this.openConversation(name);
        });
        $(root).on("click", ".ctlno-call-item", (e) => {
            this.openCall($(e.currentTarget).data("call"));
        });
    }

    // ── Conversations list ────────────────────────────────────────────────────

    loadConversations() {
        if (this.filter === "calls") { this._loadCalls(); return; }
        const filter_type = this.filter === "closed" ? "all" : this.filter;
        frappe.call({
            method: "thanatos_intel.api.centralino.get_conversations",
            args: { filter_type, search: this.search },
            callback: (r) => {
                let rows = r.message || [];
                if (this.filter === "closed") {
                    rows = rows.filter(c => c.status === "Chiuso");
                } else {
                    rows = rows.filter(c => c.status !== "Chiuso");
                }
                this._renderList(rows);
            },
        });
    }

    _renderList(rows) {
        if (!rows.length) {
            $("#ctlno-list").html(
                `<div class="ctlno-empty-list">Nessuna conversazione</div>`
            );
            return;
        }
        const html = rows.map(c => this._convItemHtml(c)).join("");
        $("#ctlno-list").html(html);
        if (this.activeLead) {
            $(`[data-name="${this.activeLead}"]`).addClass("active");
        }
    }

    _loadCalls() {
        if (!document.getElementById("ctlno-call-css")) {
            $("head").append(`<style id="ctlno-call-css">
              .ctlno-call-item{padding:10px 14px;border-bottom:1px solid var(--border-color);cursor:pointer}
              .ctlno-call-item:hover,.ctlno-call-item.active{background:var(--bg-color)}
              .ctlno-ci-top{display:flex;justify-content:space-between;font-size:13px}
              .ctlno-ci-name{font-weight:600}.ctlno-ci-time{color:#888;font-size:11px}
              .ctlno-ci-sub{font-size:11px;color:#888;margin-top:2px}
              .ctlno-call-detail{padding:20px;max-width:820px}
              .ctlno-call-h{font-size:18px;font-weight:600}.ctlno-call-h span{color:#888;font-size:13px;font-weight:400;margin-left:8px}
              .ctlno-call-meta{color:#888;font-size:12px;margin:4px 0 8px}
              .ctlno-call-tr-h{font-weight:600;margin:14px 0 6px;color:#C8A96E}
              .ctlno-call-tr{white-space:pre-wrap;line-height:1.6;font-size:13px;background:var(--card-bg,#fff);border:1px solid var(--border-color);border-radius:8px;padding:12px}
              .ctlno-call-link{display:inline-block;margin-top:12px;color:#C8A96E}
            </style>`);
        }
        frappe.call({ method: "thanatos_intel.api.centralino.get_call_logs",
            args: { search: this.search },
            callback: (r) => this._renderCallList(r.message || []) });
    }

    _renderCallList(rows) {
        if (!rows.length) { $("#ctlno-list").html('<div class="ctlno-empty-list">Nessuna chiamata registrata</div>'); return; }
        $("#ctlno-list").html(rows.map(c => this._callItemHtml(c)).join(""));
        if (this.activeCall) $(`[data-call="${this.activeCall}"]`).addClass("active");
    }

    _callItemHtml(c) {
        const esc = frappe.utils.escape_html;
        const who = esc(c.caller_name || c.caller_number || "Sconosciuto");
        const when = c.called_at ? frappe.datetime.prettyDate(c.called_at) : "";
        const dur = (c.duration_minutes || 0) + "m " + (c.duration_seconds || 0) + "s";
        const rec = c.audio_file ? "🔴" : "";
        return `<div class="ctlno-call-item" data-call="${c.name}">
            <div class="ctlno-ci-top"><span class="ctlno-ci-name">📞 ${who}</span><span class="ctlno-ci-time">${esc(when)}</span></div>
            <div class="ctlno-ci-sub">${esc(c.outcome || "")} · ${dur} ${rec}</div></div>`;
    }

    openCall(name) {
        const esc = frappe.utils.escape_html;
        this.activeCall = name;
        $(".ctlno-call-item").removeClass("active");
        $(`[data-call="${name}"]`).addClass("active");
        $("#ctlno-chat-area").html('<div class="ctlno-loading">Caricamento...</div>');
        frappe.db.get_doc("Call Log", name).then(d => {
            const src = "/api/method/thanatos_intel.api.centralino.stream_call_audio?call_log=" + encodeURIComponent(name);
            const audio = d.audio_file
                ? `<audio controls preload="metadata" style="width:100%;margin:12px 0" src="${src}"></audio>
                   <div><a class="ctlno-call-link" href="${src}" download="${esc(name)}.ogg">⬇ Scarica registrazione</a></div>`
                : '<div class="ctlno-call-meta">Nessuna registrazione audio.</div>';
            let segs = [];
            try { segs = JSON.parse(d.transcript_raw || "[]"); } catch (e) {}
            let tr;
            if (segs.length) {
                tr = segs.map(sg => {
                    const t = Math.floor((sg.start_ms || 0) / 1000);
                    const ts = String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0");
                    const spk = sg.speaker_label || sg.speaker || "?";
                    return `<div class="ctlno-tr-seg"><b>${esc(spk)}</b> <span style="color:#888">[${ts}]</span> ${esc(sg.text || "")}</div>`;
                }).join("");
            } else { tr = d.transcript_text ? esc(d.transcript_text) : "(trascrizione non disponibile)"; }
            const mdUrl = "/api/method/thanatos_intel.api.centralino.call_transcript_md?call_log=" + encodeURIComponent(name);
            const who = esc(d.caller_name || d.caller_number || "Sconosciuto");
            $("#ctlno-chat-area").html(`<div class="ctlno-call-detail">
                <div class="ctlno-call-h">📞 ${who}<span>${esc(d.caller_number || "")}</span></div>
                <div class="ctlno-call-meta">${esc(d.outcome || "")} · ${(d.duration_minutes || 0)}m ${(d.duration_seconds || 0)}s · ${d.called_at ? frappe.datetime.str_to_user(d.called_at) : ""}</div>
                ${audio}
                <div class="ctlno-call-tr-h">Trascrizione <a class="ctlno-call-link" href="${mdUrl}" style="font-size:11px;font-weight:400;margin-left:10px" download="${esc(name)}.md">📄 Esporta .md</a></div>
                <div class="ctlno-call-tr">${tr}</div>
                ${d.linked_case ? `<a class="ctlno-call-link" href="/app/investigation-case/${d.linked_case}" target="_blank">Apri caso ${esc(d.linked_case)}</a>` : ""}
            </div>`);
        });
    }

    _convItemHtml(c) {
        const name = frappe.db.get_value
            ? (c.source_name || c.source_identifier || c.name)
            : (c.source_name || c.source_identifier || c.name);
        const initials = (c.source_name || "?").slice(0, 2).toUpperCase();
        const ts = c.last_message_at ? frappe.datetime.prettyDate(c.last_message_at) : "";
        const badge = c.status === "Chiuso"
            ? `<span class="ctlno-badge closed">chiuso</span>`
            : c.status === "In lavorazione"
                ? `<span class="ctlno-badge wip">WIP</span>`
                : "";
        const prio = c.priority === "Alta" || c.priority === "Urgente"
            ? `<span class="ctlno-prio-dot"></span>` : "";
        const linked = c.linked_case
            ? `<span class="ctlno-badge case">${c.linked_case}</span>` : "";
        const icon = c.source_type === "WhatsApp" ? "🟢" : c.source_type === "Telegram" ? "🔵" : "💬";

        return `
<div class="ctlno-conv-item" data-name="${frappe.utils.escape_html(c.name)}">
  <div class="ctlno-conv-avatar">${initials}</div>
  <div class="ctlno-conv-body">
    <div class="ctlno-conv-top">
      <span class="ctlno-conv-name">${prio}${icon} ${frappe.utils.escape_html(c.source_name || c.source_identifier || c.name)}</span>
      <span class="ctlno-conv-ts">${ts}</span>
    </div>
    <div class="ctlno-conv-sub">
      ${badge}${linked}
      ${c.assigned_to ? `<span class="ctlno-assigned">${c.assigned_to.split("@")[0]}</span>` : ""}
    </div>
  </div>
</div>`;
    }

    // ── Chat view ─────────────────────────────────────────────────────────────

    openConversation(leadName) {
        this.activeLead = leadName;
        $(".ctlno-conv-item").removeClass("active");
        $(`[data-name="${leadName}"]`).addClass("active");
        $("#ctlno-chat-area").html(`<div class="ctlno-loading">Caricamento...</div>`);

        frappe.call({
            method: "thanatos_intel.api.centralino.get_thread",
            args: { lead_name: leadName },
            callback: (r) => {
                if (r.message) this._renderChat(r.message);
            },
        });
    }

    _renderChat(data) {
        const isClosed = data.status === "Chiuso";
        const closedNote = isClosed
            ? `<div class="ctlno-chat-closed-banner">Conversazione chiusa</div>` : "";

        const bubbles = (data.messages || []).map(m => this._bubbleHtml(m)).join("");

        const actions = `
<div class="ctlno-chat-actions">
  <button class="ctlno-act-btn" id="ctlno-btn-assign" title="Assegna">👤 Assegna</button>
  ${data.linked_case
    ? `<a class="ctlno-act-btn" href="/app/investigation-case/${encodeURIComponent(data.linked_case)}" target="_blank">📁 ${data.linked_case}</a>`
    : `<button class="ctlno-act-btn" id="ctlno-btn-promote">📁 Crea pratica</button>`}
  ${isClosed
    ? `<button class="ctlno-act-btn warn" id="ctlno-btn-reopen">🔄 Riapri</button>`
    : `<button class="ctlno-act-btn warn" id="ctlno-btn-close">✓ Chiudi</button>`}
  <a class="ctlno-act-btn" href="/app/intel-lead/${encodeURIComponent(data.name)}" target="_blank">↗ Apri</a>
</div>`;

        const replyBox = isClosed ? "" : `
<div class="ctlno-reply-wrap">
  <textarea class="ctlno-reply-input" id="ctlno-reply-input" placeholder="Scrivi risposta… (Invio=nuova riga, Ctrl+Invio=invia)" rows="2"></textarea>
  <button class="ctlno-send-btn" id="ctlno-send-btn">▶</button>
</div>`;

        const srcName = frappe.utils.escape_html(data.source_name || data.source_identifier || data.name);
        const waNum = data.whatsapp_number
            ? `<span class="ctlno-chat-sub">📱 ${data.whatsapp_number}</span>` : "";

        $("#ctlno-chat-area").html(`
<div class="ctlno-chat-header">
  <div>
    <span class="ctlno-chat-title">${srcName}</span>
    ${waNum}
  </div>
  <span class="ctlno-status-badge ${(data.status || "").toLowerCase().replace(/ /g, "-")}">${data.status || ""}</span>
</div>
${actions}
<div class="ctlno-chat-messages" id="ctlno-messages">
  ${bubbles || `<div class="ctlno-no-msgs">Nessun messaggio</div>`}
</div>
${closedNote}
${replyBox}`);

        this._scrollBottom();
        this._bindChatEvents(data);
    }

    _bubbleHtml(m) {
        const isOut = m.direction === "Outbound";
        const align = isOut ? "flex-end" : "flex-start";
        const bg = isOut ? "#C8A96E" : "#1e2435";
        const color = isOut ? "#0A0E1A" : "#E8E9F0";
        const ts = m.sent_at ? frappe.datetime.str_to_user(m.sent_at) : "";
        const status = isOut ? this._statusIcon(m.status) : "";
        const by = isOut && m.sent_by ? `<span style="font-size:9px;opacity:.6">${m.sent_by.split("@")[0]}</span> ` : "";
        const media = m.media_url
            ? `<div style="margin-top:4px"><a href="${frappe.utils.escape_html(m.media_url)}" target="_blank" style="color:inherit;font-size:10px">📎 media</a></div>` : "";

        const wamid = m.wa_message_id ? `data-wamid="${frappe.utils.escape_html(m.wa_message_id)}"` : "";
        return `
<div style="display:flex;justify-content:${align};margin:4px 8px" ${wamid}>
  <div style="max-width:72%;background:${bg};color:${color};border-radius:12px;padding:8px 12px;font-size:13px;line-height:1.5">
    <div style="font-size:9px;opacity:.55;margin-bottom:3px">${by}${ts} <span class="ctlno-status">${status}</span></div>
    ${frappe.utils.escape_html(m.content || "")}${media}
  </div>
</div>`;
    }

    _statusIcon(st) {
        if (st === "Letto") return "🔵";
        if (st === "Consegnato") return "✓✓";
        return "✓";
    }

    _scrollBottom() {
        const el = document.getElementById("ctlno-messages");
        if (el) el.scrollTop = el.scrollHeight;
    }

    _bindChatEvents(data) {
        const root = this.wrapper;

        // Invia
        $(root).on("click.chat", "#ctlno-send-btn", () => this._sendReply());
        $(root).on("keydown.chat", "#ctlno-reply-input", (e) => {
            if (e.ctrlKey && e.key === "Enter") this._sendReply();
        });

        // Chiudi / Riapri
        $(root).on("click.chat", "#ctlno-btn-close", () => {
            frappe.confirm("Chiudere questa conversazione?", () => {
                frappe.call({
                    method: "thanatos_intel.api.centralino.close_lead",
                    args: { lead_name: this.activeLead },
                    callback: () => {
                        this.loadConversations();
                        this.openConversation(this.activeLead);
                    },
                });
            });
        });
        $(root).on("click.chat", "#ctlno-btn-reopen", () => {
            frappe.call({
                method: "thanatos_intel.api.centralino.reopen_lead",
                args: { lead_name: this.activeLead },
                callback: () => {
                    this.loadConversations();
                    this.openConversation(this.activeLead);
                },
            });
        });

        // Assegna
        $(root).on("click.chat", "#ctlno-btn-assign", () => this._openAssignDialog());

        // Promuovi a caso
        $(root).on("click.chat", "#ctlno-btn-promote", () => this._openPromoteDialog(data));
    }

    _sendReply() {
        const text = $("#ctlno-reply-input").val().trim();
        if (!text || !this.activeLead) return;
        $("#ctlno-reply-input").val("").prop("disabled", true);
        $("#ctlno-send-btn").prop("disabled", true);

        frappe.call({
            method: "thanatos_intel.api.centralino.send_reply",
            args: { lead_name: this.activeLead, message_text: text },
            callback: (r) => {
                $("#ctlno-reply-input").prop("disabled", false);
                $("#ctlno-send-btn").prop("disabled", false);
                if (r.message?.status === "sent") {
                    this._appendBubble({
                        direction: "Outbound",
                        content: text,
                        sent_at: frappe.datetime.now_datetime(),
                        sent_by: frappe.session.user,
                        status: "Inviato",
                    });
                } else {
                    frappe.msgprint(__("Errore invio: ") + (r.message?.error || "sconosciuto"));
                }
            },
        });
    }

    _appendBubble(m) {
        const html = this._bubbleHtml(m);
        $("#ctlno-messages").append(html);
        this._scrollBottom();
    }

    _openAssignDialog() {
        frappe.call({
            method: "thanatos_intel.api.centralino.get_operators",
            callback: (r) => {
                const users = r.message || [];
                const opts = users.map(u =>
                    `<option value="${frappe.utils.escape_html(u.name)}">${frappe.utils.escape_html(u.full_name || u.name)}</option>`
                ).join("");
                const d = new frappe.ui.Dialog({
                    title: __("Assegna a operatore"),
                    fields: [{
                        label: "Operatore",
                        fieldname: "to_user",
                        fieldtype: "Select",
                        options: users.map(u => u.name).join("\n"),
                    }],
                    primary_action_label: __("Assegna"),
                    primary_action: (vals) => {
                        frappe.call({
                            method: "thanatos_intel.api.centralino.assign_lead",
                            args: { lead_name: this.activeLead, to_user: vals.to_user },
                            callback: () => {
                                d.hide();
                                frappe.show_alert({ message: __("Assegnato!"), indicator: "green" });
                                this.loadConversations();
                                this.openConversation(this.activeLead);
                            },
                        });
                    },
                });
                d.show();
            },
        });
    }

    _openPromoteDialog(data) {
        const d = new frappe.ui.Dialog({
            title: __("Promuovi a pratica"),
            fields: [
                {
                    label: "Titolo pratica",
                    fieldname: "case_title",
                    fieldtype: "Data",
                    reqd: 1,
                    default: `${data.source_name || data.source_identifier} — ${frappe.datetime.nowdate()}`,
                },
                {
                    label: "Tipo pratica",
                    fieldname: "case_type",
                    fieldtype: "Link",
                    options: "Investigation Case Type",
                },
            ],
            primary_action_label: __("Crea pratica"),
            primary_action: (vals) => {
                frappe.call({
                    method: "frappe.client.run_doc_method",
                    args: {
                        dt: "Intel Lead",
                        dn: this.activeLead,
                        method: "promote_to_case",
                        args: { case_title: vals.case_title, case_type: vals.case_type },
                    },
                    callback: (r) => {
                        d.hide();
                        if (r.message?.case) {
                            frappe.show_alert({ message: __("Pratica creata: ") + r.message.case, indicator: "green" });
                            this.loadConversations();
                            this.openConversation(this.activeLead);
                        }
                    },
                });
            },
        });
        d.show();
    }

    // ── Operator status ───────────────────────────────────────────────────────

    _setStatus(s) {
        this.operatorStatus = s;
        const labels = { online: "● Online", busy: "◉ Occupato", offline: "○ Offline" };
        $("#ctlno-status-btn")
            .text(`${labels[s]} ▾`)
            .removeClass("online busy offline")
            .addClass(s);
        $("#ctlno-status-menu").removeClass("open");
        frappe.call({
            method: "thanatos_intel.api.centralino.set_operator_status",
            args: { status: s },
        });
    }

    // ── Realtime ──────────────────────────────────────────────────────────────

    _subscribeRealtime() {
        frappe.realtime.on("centralino_update", (data) => {
            this._handleUpdate(data);
        });
        frappe.realtime.on("centralino_incoming_call", (data) => {
            this._showIncomingCall(data);
        });
    }

    // ── Chiamate WhatsApp (softphone WebRTC) ────────────────────────────────────

    _showIncomingCall(data) {
        $("#ctlno-callbar").remove();
        const bar = $(`
<div id="ctlno-callbar" class="ctlno-callbar">
  <span class="ctlno-call-ring">📞 Chiamata WhatsApp in arrivo da <b>${frappe.utils.escape_html(data.from || "")}</b></span>
  <button class="ctlno-call-answer" id="ctlno-answer">Rispondi</button>
  <button class="ctlno-call-hangup" id="ctlno-decline">Ignora</button>
</div>`);
        $(this.wrapper).find(".ctlno-root").prepend(bar);
        $("#ctlno-answer").on("click", () => this._answerCall(data.call_id));
        $("#ctlno-decline").on("click", () => $("#ctlno-callbar").remove());
    }

    async _answerCall(callId) {
        try {
            $("#ctlno-callbar .ctlno-call-ring").html("⏳ Connessione audio…");
            const pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
            this._activeCallPc = pc;
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach(t => pc.addTrack(t, stream));
            pc.ontrack = (e) => {
                let audio = document.getElementById("ctlno-remote-audio");
                if (!audio) {
                    audio = document.createElement("audio");
                    audio.id = "ctlno-remote-audio"; audio.autoplay = true;
                    document.body.appendChild(audio);
                }
                audio.srcObject = e.streams[0];
            };
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            // attende ICE gathering completo (sdp con candidati)
            await new Promise(res => {
                if (pc.iceGatheringState === "complete") return res();
                const check = () => { if (pc.iceGatheringState === "complete") { pc.removeEventListener("icegatheringstatechange", check); res(); } };
                pc.addEventListener("icegatheringstatechange", check);
                setTimeout(res, 2000);
            });
            frappe.call({
                method: "thanatos_intel.api.wa_calling.operator_join",
                args: { call_id: callId, sdp: pc.localDescription.sdp },
                callback: async (r) => {
                    if (r.message?.ok && r.message.sdp) {
                        await pc.setRemoteDescription({ type: "answer", sdp: r.message.sdp });
                        $("#ctlno-callbar .ctlno-call-ring").html("🟢 In chiamata con " + callId.slice(0, 10));
                        $("#ctlno-answer").remove();
                        $("#ctlno-decline").text("Riaggancia").off("click").on("click", () => this._hangupCall());
                    } else {
                        $("#ctlno-callbar .ctlno-call-ring").html("❌ Chiamata non più attiva");
                        this._hangupCall();
                    }
                },
            });
        } catch (e) {
            frappe.msgprint(__("Microfono non disponibile o permesso negato: ") + e.message);
            $("#ctlno-callbar").remove();
        }
    }

    _hangupCall() {
        if (this._activeCallPc) { try { this._activeCallPc.close(); } catch (e) {} this._activeCallPc = null; }
        $("#ctlno-remote-audio").remove();
        $("#ctlno-callbar").remove();
    }

    _handleUpdate(data) {
        const { lead, type } = data;

        // Aggiornamento stato consegna/lettura → aggiorna la spunta live
        if (type === "status" && data.wa_message_id) {
            const el = document.querySelector(`[data-wamid="${data.wa_message_id}"] .ctlno-status`);
            if (el) el.textContent = this._statusIcon(data.status);
            return;
        }

        // Refresh lista conversazioni
        this.loadConversations();

        // Se la conversazione attiva ha un nuovo messaggio → ricarica la chat
        if (lead === this.activeLead && (type === "new_message" || type === "new_lead")) {
            frappe.call({
                method: "thanatos_intel.api.centralino.get_thread",
                args: { lead_name: lead },
                callback: (r) => {
                    if (r.message) {
                        const msgs = r.message.messages || [];
                        const last = msgs[msgs.length - 1];
                        if (last && last.direction === "Inbound") {
                            this._appendBubble(last);
                        }
                    }
                },
            });
        }
    }

    // ── Styles ────────────────────────────────────────────────────────────────

    _injectStyles() {
        if (document.getElementById("ctlno-styles")) return;
        const style = document.createElement("style");
        style.id = "ctlno-styles";
        style.textContent = `
/* ─── Layout ─────────────────────────────────────────────────────── */
.ctlno-root {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 100px);
  background: #0A0E1A;
  color: #E8E9F0;
  font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #1F2742;
}
.ctlno-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ─── Header ─────────────────────────────────────────────────────── */
.ctlno-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: rgba(10,14,26,.97);
  border-bottom: 1px solid #1F2742;
  flex-shrink: 0;
}
.ctlno-header-left { display: flex; align-items: center; gap: 8px; }
.ctlno-logo { font-size: 20px; }
.ctlno-title { font-size: 14px; font-weight: 700; letter-spacing: 2px; color: #C8A96E; text-transform: uppercase; }
.ctlno-header-center { display: flex; gap: 4px; flex: 1; }
.ctlno-header-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.ctlno-deviazione { background: #1a1f2e; color: #C8A96E; border: 1px solid #C8A96E;
  border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer; white-space: nowrap; }
.ctlno-deviazione:hover { background: #C8A96E; color: #0A0E1A; }

/* ─── Filters ─────────────────────────────────────────────────────── */
.ctlno-filter {
  background: none;
  border: 1px solid #1F2742;
  color: #7A8194;
  font-size: 10px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  padding: 5px 10px;
  border-radius: 3px;
  cursor: pointer;
  transition: all .15s;
}
.ctlno-filter:hover { border-color: #C8A96E; color: #C8A96E; }
.ctlno-filter.act { background: #C8A96E; border-color: #C8A96E; color: #0A0E1A; font-weight: 700; }

/* ─── Search ─────────────────────────────────────────────────────── */
.ctlno-search {
  background: #111729;
  border: 1px solid #1F2742;
  border-radius: 4px;
  color: #E8E9F0;
  font-size: 11px;
  padding: 5px 10px;
  width: 160px;
  outline: none;
}
.ctlno-search:focus { border-color: #C8A96E; }

/* ─── Status button ──────────────────────────────────────────────── */
.ctlno-status-wrap { position: relative; }
.ctlno-status-btn {
  background: none;
  border: 1px solid #1F2742;
  border-radius: 4px;
  color: #4CAF50;
  font-size: 10px;
  letter-spacing: 1px;
  padding: 5px 10px;
  cursor: pointer;
  white-space: nowrap;
}
.ctlno-status-btn.busy { color: #FF9800; }
.ctlno-status-btn.offline { color: #7A8194; }
.ctlno-status-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  background: #111729;
  border: 1px solid #1F2742;
  border-radius: 6px;
  padding: 4px;
  display: none;
  flex-direction: column;
  z-index: 100;
  min-width: 130px;
}
.ctlno-status-menu.open { display: flex; }
.ctlno-sm-item {
  padding: 7px 12px;
  font-size: 11px;
  color: #A4A9BC;
  cursor: pointer;
  border-radius: 4px;
  text-decoration: none;
}
.ctlno-sm-item:hover { background: #0A0E1A; color: #C8A96E; }

/* ─── Sidebar ─────────────────────────────────────────────────────── */
.ctlno-sidebar {
  width: 280px;
  border-right: 1px solid #1F2742;
  overflow-y: auto;
  background: #0d1020;
  flex-shrink: 0;
}
.ctlno-list-wrap { padding: 4px 0; }
.ctlno-empty-list { color: #5B6276; font-size: 12px; text-align: center; padding: 32px 16px; }
.ctlno-loading { color: #5B6276; font-size: 12px; text-align: center; padding: 32px 16px; }

/* ─── Conversation item ──────────────────────────────────────────── */
.ctlno-conv-item {
  display: flex;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid #131929;
  transition: background .1s;
}
.ctlno-conv-item:hover { background: #111729; }
.ctlno-conv-item.active { background: #1A2035; border-left: 3px solid #C8A96E; }
.ctlno-conv-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: #1F2742; color: #C8A96E;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.ctlno-conv-body { flex: 1; min-width: 0; }
.ctlno-conv-top { display: flex; justify-content: space-between; align-items: baseline; gap: 4px; }
.ctlno-conv-name { font-size: 12px; font-weight: 600; color: #E8E9F0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
.ctlno-conv-ts { font-size: 9px; color: #5B6276; flex-shrink: 0; }
.ctlno-conv-sub { margin-top: 3px; display: flex; gap: 4px; flex-wrap: wrap; }
.ctlno-badge { font-size: 9px; letter-spacing: 1px; padding: 1px 5px; border-radius: 3px; text-transform: uppercase; }
.ctlno-badge.closed { background: #2a1010; color: #E06C6C; }
.ctlno-badge.wip { background: #1a2535; color: #C8A96E; }
.ctlno-badge.case { background: #111729; color: #A4A9BC; }
.ctlno-prio-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #E06C6C; margin-right: 4px; }
.ctlno-assigned { font-size: 9px; color: #5B6276; }

/* ─── Chat area ───────────────────────────────────────────────────── */
.ctlno-chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #0A0E1A;
}
.ctlno-empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; }

.ctlno-chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid #1F2742;
  background: #0d1020;
  flex-shrink: 0;
}
.ctlno-chat-title { font-size: 14px; font-weight: 700; color: #E8E9F0; }
.ctlno-chat-sub { font-size: 10px; color: #5B6276; margin-left: 8px; }
.ctlno-status-badge {
  font-size: 9px; letter-spacing: 1px; text-transform: uppercase;
  padding: 3px 8px; border-radius: 3px;
  background: #1F2742; color: #A4A9BC;
}
.ctlno-status-badge.aperto { background: #0d2a1a; color: #4CAF50; }
.ctlno-status-badge.chiuso { background: #2a1010; color: #E06C6C; }
.ctlno-status-badge.in-lavorazione { background: #1a2535; color: #C8A96E; }

.ctlno-chat-actions {
  display: flex;
  gap: 6px;
  padding: 6px 12px;
  border-bottom: 1px solid #1F2742;
  background: #0d1020;
  flex-shrink: 0;
}
.ctlno-act-btn {
  background: none;
  border: 1px solid #1F2742;
  color: #A4A9BC;
  font-size: 10px;
  letter-spacing: 1px;
  padding: 4px 10px;
  border-radius: 3px;
  cursor: pointer;
  transition: all .15s;
  text-decoration: none;
  display: inline-block;
}
.ctlno-act-btn:hover { border-color: #C8A96E; color: #C8A96E; }
.ctlno-act-btn.warn:hover { border-color: #E06C6C; color: #E06C6C; }

.ctlno-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
  scroll-behavior: smooth;
}
.ctlno-no-msgs { color: #5B6276; text-align: center; padding: 32px; font-size: 12px; }
.ctlno-chat-closed-banner {
  text-align: center;
  padding: 8px;
  font-size: 11px;
  color: #E06C6C;
  background: #1a0a0a;
  border-top: 1px solid #2a1010;
  flex-shrink: 0;
}

/* ─── Reply box ───────────────────────────────────────────────────── */
.ctlno-reply-wrap {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid #1F2742;
  background: #0d1020;
  flex-shrink: 0;
  align-items: flex-end;
}
.ctlno-reply-input {
  flex: 1;
  background: #111729;
  border: 1px solid #1F2742;
  border-radius: 8px;
  color: #E8E9F0;
  font-size: 13px;
  padding: 8px 12px;
  resize: none;
  outline: none;
  max-height: 120px;
  line-height: 1.5;
}
.ctlno-reply-input:focus { border-color: #C8A96E; }
.ctlno-send-btn {
  background: #C8A96E;
  color: #0A0E1A;
  border: none;
  border-radius: 6px;
  width: 36px;
  height: 36px;
  cursor: pointer;
  font-size: 14px;
  transition: background .15s;
  flex-shrink: 0;
}
.ctlno-send-btn:hover { background: #B8975A; }
.ctlno-send-btn:disabled { background: #3a3a3a; cursor: not-allowed; }

/* ─── Call bar (chiamata WhatsApp in arrivo) ───────────────────────── */
.ctlno-callbar { display:flex; align-items:center; gap:12px; padding:10px 16px;
  background:linear-gradient(90deg,#0d3320,#0a2418); border-bottom:1px solid #1d5638; flex-shrink:0; }
.ctlno-call-ring { color:#4CAF50; font-size:13px; flex:1; animation:ctlnoPulse 1.4s infinite; }
@keyframes ctlnoPulse { 0%,100%{opacity:1} 50%{opacity:.55} }
.ctlno-call-answer { background:#4CAF50; color:#fff; border:none; border-radius:5px; padding:7px 18px; font-size:12px; font-weight:700; cursor:pointer; letter-spacing:1px; }
.ctlno-call-hangup { background:none; color:#E06C6C; border:1px solid #E06C6C; border-radius:5px; padding:7px 14px; font-size:12px; cursor:pointer; letter-spacing:1px; }
`;
        document.head.appendChild(style);
    }
}
