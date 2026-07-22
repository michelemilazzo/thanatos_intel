/**
 * Centralino Thanatos — gestore GLOBALE delle chiamate WhatsApp in arrivo.
 *
 * Caricato su ogni pagina del desk (app_include_js): ovunque si trovi
 * l'operatore, quando arriva una chiamata WhatsApp compare una barra con
 * "Rispondi", che apre la gamba audio nel browser (WebRTC) collegandosi al
 * media server tramite l'endpoint whitelisted `operator_join` e il TURN.
 *
 * La pagina dedicata `/app/centralino` ha già la sua barra interna: qui la
 * saltiamo per non mostrarne due.
 */
frappe.provide("thanatos.switchboard");

(function () {
	// Server ICE: STUN pubblico + TURN Thanatos (relay su IP pubblico). Il
	// media server aiortc è su rete privata, senza TURN l'audio non passa.
	const ICE_SERVERS = [
		{ urls: "stun:stun.l.google.com:19302" },
		{
			urls: "turn:89.167.24.194:3478?transport=udp",
			username: "thanatos",
			credential: "TrnThan2026-x7qKp9",
		},
	];
	const OPERATOR_ROLES = ["System Manager", "Investigation Manager", "Investigator"];

	let pc = null;
	let stream = null;
	let callId = null;
	let ring = null;
	let timerInt = null;

	function isOperator() {
		return (frappe.user_roles || []).some((r) => OPERATOR_ROLES.includes(r));
	}

	function onCentralinoPage() {
		try {
			const route = frappe.get_route ? frappe.get_route() : [];
			return route && route[0] === "centralino";
		} catch (e) {
			return false;
		}
	}

	function injectStyle() {
		if (document.getElementById("thn-sw-style")) return;
		const css = `
#thn-callbar{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2147483000;
  display:flex;align-items:center;gap:14px;background:#0b1f33;color:#fff;padding:12px 18px;
  border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.45);font-size:14px;max-width:92vw;
  border:1px solid rgba(255,255,255,.12)}
#thn-callbar .thn-info{line-height:1.35}
#thn-callbar .thn-info b{font-weight:600}
#thn-callbar .thn-sub{opacity:.75;font-size:12px}
#thn-callbar button{border:0;border-radius:9px;padding:9px 16px;font-weight:600;cursor:pointer;font-size:14px}
#thn-callbar .thn-answer{background:#22c55e;color:#04240f}
#thn-callbar .thn-answer:hover{background:#16a34a}
#thn-callbar .thn-hangup{background:#ef4444;color:#fff}
#thn-callbar .thn-hangup:hover{background:#dc2626}
#thn-callbar .thn-dot{width:9px;height:9px;border-radius:50%;background:#22c55e;
  box-shadow:0 0 0 0 rgba(34,197,94,.7);animation:thn-pulse 1.4s infinite}
@keyframes thn-pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.7)}70%{box-shadow:0 0 0 12px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}`;
		const st = document.createElement("style");
		st.id = "thn-sw-style";
		st.textContent = css;
		document.head.appendChild(st);
	}

	// Suoneria discreta (WebAudio): due toni ripetuti finché non si risponde.
	function startRing() {
		stopRing();
		try {
			const AC = window.AudioContext || window.webkitAudioContext;
			if (!AC) return;
			const ctx = new AC();
			const beep = () => {
				const o = ctx.createOscillator();
				const g = ctx.createGain();
				o.connect(g);
				g.connect(ctx.destination);
				o.frequency.value = 520;
				g.gain.setValueAtTime(0.0001, ctx.currentTime);
				g.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.05);
				g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
				o.start();
				o.stop(ctx.currentTime + 0.55);
			};
			beep();
			ring = { ctx, int: setInterval(beep, 2500) };
		} catch (e) {
			/* audio non disponibile: la barra resta comunque visibile */
		}
	}

	function stopRing() {
		if (ring) {
			try { clearInterval(ring.int); } catch (e) {}
			try { ring.ctx.close(); } catch (e) {}
			ring = null;
		}
	}

	function removeBar() {
		stopRing();
		const bar = document.getElementById("thn-callbar");
		if (bar) bar.remove();
	}

	function showIncoming(data) {
		if (!isOperator()) return;
		if (onCentralinoPage()) return; // gestita dalla pagina dedicata
		injectStyle();
		removeBar();
		callId = data.call_id;
		const caller = data.caller || {};
		const who = frappe.utils.escape_html(caller.name || data.from || "Sconosciuto");
		const number = frappe.utils.escape_html(data.from || "");
		const org = caller.org ? " · " + frappe.utils.escape_html(caller.org) : "";
		const assigned = caller.assigned_name
			? "Assegnato a " + frappe.utils.escape_html(caller.assigned_name)
			: "";
		const bar = document.createElement("div");
		bar.id = "thn-callbar";
		bar.innerHTML = `
			<span class="thn-dot"></span>
			<span class="thn-info">📞 <b>Chiamata WhatsApp</b> da <b>${who}</b>${org}
				<div class="thn-sub">${number}${assigned ? " · " + assigned : ""}</div>
			</span>
			<button class="thn-answer" id="thn-answer">Rispondi</button>
			<button class="thn-hangup" id="thn-ignore">Ignora</button>`;
		document.body.appendChild(bar);
		document.getElementById("thn-answer").onclick = () => answer();
		document.getElementById("thn-ignore").onclick = () => removeBar();
		startRing();
	}

	async function answer() {
		stopRing();
		const info = document.querySelector("#thn-callbar .thn-info");
		const answerBtn = document.getElementById("thn-answer");
		if (answerBtn) answerBtn.remove();
		if (info) info.innerHTML = "⏳ <b>Connessione audio…</b>";
		try {
			pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
			stream = await navigator.mediaDevices.getUserMedia({ audio: true });
			stream.getTracks().forEach((t) => pc.addTrack(t, stream));
			pc.ontrack = (e) => {
				let audio = document.getElementById("thn-remote-audio");
				if (!audio) {
					audio = document.createElement("audio");
					audio.id = "thn-remote-audio";
					audio.autoplay = true;
					document.body.appendChild(audio);
				}
				audio.srcObject = e.streams[0];
			};
			pc.oniceconnectionstatechange = () => {
				if (["failed", "closed", "disconnected"].includes(pc.iceConnectionState)) hangup();
			};
			const offer = await pc.createOffer({ offerToReceiveAudio: true });
			await pc.setLocalDescription(offer);
			await new Promise((res) => {
				if (pc.iceGatheringState === "complete") return res();
				const check = () => {
					if (pc.iceGatheringState === "complete") {
						pc.removeEventListener("icegatheringstatechange", check);
						res();
					}
				};
				pc.addEventListener("icegatheringstatechange", check);
				setTimeout(res, 2500); // non attendere all'infinito
			});
			const r = await frappe.call({
				method: "thanatos_intel.api.wa_calling.operator_join",
				args: { call_id: callId, sdp: pc.localDescription.sdp },
			});
			if (r.message && r.message.ok && r.message.sdp) {
				await pc.setRemoteDescription({ type: "answer", sdp: r.message.sdp });
				onConnected();
			} else {
				if (info) info.innerHTML = "❌ <b>Chiamata non più attiva</b>";
				setTimeout(removeBar, 2500);
				hangup(true);
			}
		} catch (e) {
			frappe.show_alert({
				message: __("Microfono non disponibile o permesso negato: ") + e.message,
				indicator: "red",
			});
			removeBar();
			hangup(true);
		}
	}

	function onConnected() {
		const bar = document.getElementById("thn-callbar");
		if (!bar) return;
		const started = Date.now();
		const fmt = (s) =>
			Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
		bar.querySelector(".thn-info").innerHTML =
			'🟢 <b>In chiamata</b> <span class="thn-sub" id="thn-timer">0:00</span>';
		const ignore = document.getElementById("thn-ignore");
		if (ignore) {
			ignore.textContent = "Riaggancia";
			ignore.onclick = () => hangup();
		}
		timerInt = setInterval(() => {
			const t = document.getElementById("thn-timer");
			if (t) t.textContent = fmt(Math.floor((Date.now() - started) / 1000));
		}, 1000);
	}

	function hangup(silent) {
		if (timerInt) { clearInterval(timerInt); timerInt = null; }
		if (pc) { try { pc.close(); } catch (e) {} pc = null; }
		if (stream) { try { stream.getTracks().forEach((t) => t.stop()); } catch (e) {} stream = null; }
		const audio = document.getElementById("thn-remote-audio");
		if (audio) audio.remove();
		if (!silent) removeBar();
		callId = null;
	}

	$(document).ready(function () {
		if (!isOperator()) return;
		if (!frappe.realtime) return;
		frappe.realtime.on("centralino_incoming_call", showIncoming);
		// Il chiamante ha riagganciato prima della risposta.
		frappe.realtime.on("centralino_call_ended", (d) => {
			if (d && d.call_id && d.call_id === callId) {
				removeBar();
				hangup(true);
			}
		});
	});

	thanatos.switchboard.answer = answer;
	thanatos.switchboard.hangup = hangup;
})();
