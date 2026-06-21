frappe.pages["wa-test"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "WhatsApp Test",
        single_column: true,
    });
    new WaTest(page);
};

class WaTest {
    constructor(page) {
        this.page = page;
        this.$body = $(page.main);
        this._injectStyles();
        this._render();
        this.loadStatus();
    }

    _render() {
        this.$body.html(`
<div class="wat-wrap">
  <!-- Stato sistema -->
  <div class="wat-card">
    <div class="wat-h">🩺 Stato sistema</div>
    <div id="wat-status" class="wat-status">Caricamento…</div>
    <button class="wat-btn" id="wat-refresh">Aggiorna</button>
  </div>

  <!-- Test trascrizione + diarizzazione -->
  <div class="wat-card">
    <div class="wat-h">🎤 Test trascrizione + voci (Whisper locale)</div>
    <p class="wat-sub">Carica un file audio (ogg/mp3/wav/m4a). La trascrizione separa le voci (Speaker A/B…).</p>
    <div class="wat-row">
      <input type="file" id="wat-audio" accept="audio/*">
      <label class="wat-chk"><input type="checkbox" id="wat-diarize" checked> Separa voci</label>
      <span class="wat-chk">N. voci: <input type="number" id="wat-nspk" value="2" min="1" max="6" style="width:46px"></span>
      <button class="wat-btn" id="wat-transcribe" disabled>Trascrivi</button>
    </div>
    <div id="wat-trx"></div>
  </div>

  <!-- Test invio messaggio -->
  <div class="wat-card">
    <div class="wat-h">📤 Test invio messaggio WhatsApp</div>
    <p class="wat-sub">⚠️ Funziona solo se il numero ti ha scritto nelle ultime 24h (finestra aperta).</p>
    <div class="wat-row">
      <input type="text" id="wat-phone" placeholder="+39…" class="wat-inp">
      <input type="text" id="wat-text" placeholder="Messaggio di test" class="wat-inp" style="flex:1">
      <button class="wat-btn" id="wat-send">Invia</button>
    </div>
    <div id="wat-send-res"></div>
  </div>
</div>`);

        this.$body.on("click", "#wat-refresh", () => this.loadStatus());
        this.$body.on("change", "#wat-audio", (e) => {
            $("#wat-transcribe").prop("disabled", !e.target.files.length);
        });
        this.$body.on("click", "#wat-transcribe", () => this.transcribe());
        this.$body.on("click", "#wat-send", () => this.send());
    }

    loadStatus() {
        $("#wat-status").html("Caricamento…");
        frappe.call({ method: "thanatos_intel.api.wa_test.system_status", callback: (r) => {
            const s = r.message || {};
            const dot = (ok) => `<span class="wat-dot ${ok ? "ok" : "ko"}"></span>`;
            const w = s.whisper || {}, n = s.whatsapp_number || {};
            $("#wat-status").html(`
              <div>${dot(w.ok)} Whisper locale ${w.ok ? `(modello: ${w.info?.model || "?"})` : "— offline"}</div>
              <div>${dot(n.ok)} Numero WhatsApp ${n.ok ? `${n.display || n.phone}` : (n.error || "")}</div>
              <div>${dot(n.token_valid)} Token Meta ${n.token_valid ? `valido — ${n.verified_name || ""}` : "non valido"}</div>
              <div>${dot(s.webhook_token_set)} Webhook token configurato</div>
            `);
        }});
    }

    transcribe() {
        const file = $("#wat-audio")[0].files[0];
        if (!file) return;
        const $res = $("#wat-trx").html(`<div class="wat-load">⏳ Carico e trascrivo… (può richiedere qualche secondo)</div>`);
        const diarize = $("#wat-diarize").is(":checked") ? 1 : 0;
        const nspk = parseInt($("#wat-nspk").val()) || 2;

        // upload del file, poi trascrizione
        const fd = new FormData();
        fd.append("file", file);
        fd.append("is_private", 1);
        fd.append("folder", "Home");
        $.ajax({
            url: "/api/method/upload_file", method: "POST", data: fd,
            processData: false, contentType: false,
            headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
            success: (up) => {
                const file_url = up.message.file_url;
                frappe.call({
                    method: "thanatos_intel.api.wa_test.transcribe_file",
                    args: { file_url, diarize, num_speakers: nspk },
                    callback: (r) => this._renderTranscript(r.message),
                    error: () => $res.html(`<div class="wat-err">Errore trascrizione</div>`),
                });
            },
            error: () => $res.html(`<div class="wat-err">Errore upload file</div>`),
        });
    }

    _renderTranscript(data) {
        if (!data || !data.segments) {
            $("#wat-trx").html(`<div class="wat-err">Nessun risultato</div>`);
            return;
        }
        const colors = { A: "#1e2435", B: "#C8A96E", C: "#2a3550", D: "#6e5a2a" };
        const txtcol = { A: "#E8E9F0", B: "#0A0E1A", C: "#E8E9F0", D: "#E8E9F0" };
        const fmt = (ms) => { const s = Math.floor(ms / 1000); return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`; };
        const rows = data.segments.map(seg => {
            const sp = seg.speaker || "A";
            const isA = sp === "A";
            return `<div style="display:flex;justify-content:${isA ? "flex-start" : "flex-end"};margin:4px 0">
              <div style="max-width:75%;background:${colors[sp] || "#333"};color:${txtcol[sp] || "#fff"};border-radius:10px;padding:8px 12px;font-size:13px">
                <div style="font-size:10px;font-weight:bold;opacity:.7;margin-bottom:3px">Speaker ${sp} · ${fmt(seg.start_ms || 0)}</div>
                ${frappe.utils.escape_html(seg.text || "")}
              </div></div>`;
        }).join("");
        const speakers = [...new Set(data.segments.map(s => s.speaker))].length;
        $("#wat-trx").html(`
          <div class="wat-meta">Lingua: <b>${data.language || "?"}</b> · Durata: <b>${Math.round(data.duration || 0)}s</b> · Voci rilevate: <b>${speakers}</b></div>
          <div class="wat-chat">${rows}</div>`);
    }

    send() {
        const phone = $("#wat-phone").val().trim();
        const text = $("#wat-text").val().trim();
        if (!phone || !text) { frappe.show_alert({ message: "Numero e messaggio richiesti", indicator: "orange" }); return; }
        $("#wat-send-res").html(`<div class="wat-load">Invio…</div>`);
        frappe.call({
            method: "thanatos_intel.api.wa_test.send_test_message",
            args: { phone, text },
            callback: (r) => {
                if (r.message?.ok) {
                    $("#wat-send-res").html(`<div class="wat-ok">✅ Inviato (id: ${r.message.message_id.slice(0, 24)}…)</div>`);
                } else {
                    $("#wat-send-res").html(`<div class="wat-err">❌ ${r.message?.error || "errore"}</div>`);
                }
            },
        });
    }

    _injectStyles() {
        if (document.getElementById("wat-styles")) return;
        const s = document.createElement("style");
        s.id = "wat-styles";
        s.textContent = `
.wat-wrap{max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:16px;padding:8px 0}
.wat-card{background:#0d1117;border:1px solid #1F2742;border-radius:10px;padding:18px 20px;color:#C7CCDA}
.wat-h{font-size:15px;font-weight:700;color:#C8A96E;margin-bottom:8px}
.wat-sub{font-size:12px;color:#7A8194;margin:0 0 12px}
.wat-status>div{padding:3px 0;font-size:13px}
.wat-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px}
.wat-dot.ok{background:#4CAF50}.wat-dot.ko{background:#E06C6C}
.wat-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.wat-chk{font-size:12px;color:#A4A9BC;display:inline-flex;align-items:center;gap:5px}
.wat-inp{background:#111729;border:1px solid #1F2742;border-radius:5px;color:#E8E9F0;padding:7px 10px;font-size:13px}
.wat-btn{background:#C8A96E;color:#0A0E1A;border:none;border-radius:5px;padding:7px 16px;font-size:12px;font-weight:700;cursor:pointer;letter-spacing:1px}
.wat-btn:disabled{background:#3a3a3a;color:#777;cursor:not-allowed}
.wat-load{color:#C8A96E;font-size:13px;padding:8px 0}
.wat-err{color:#E06C6C;font-size:13px;padding:8px 0}
.wat-ok{color:#4CAF50;font-size:13px;padding:8px 0}
.wat-meta{font-size:12px;color:#A4A9BC;margin:10px 0 6px}
.wat-chat{background:#0a0e1a;border-radius:8px;padding:12px;max-height:440px;overflow-y:auto}
input[type=file]{color:#A4A9BC;font-size:12px}
`;
        document.head.appendChild(s);
    }
}
