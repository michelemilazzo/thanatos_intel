// Frappe Page: Evidence Upload (Thanatos Intel)
// URL: /app/evidence-upload

frappe.pages["evidence-upload"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Acquisizione Evidenza",
		single_column: true,
	});

	page.set_indicator("Riservato — Catena di custodia", "yellow");

	// Iniettiamo lo stile Thanatos solo dentro il content di questa pagina
	const $body = $(`
		<style>
		.thanatos-page{padding:24px;color:#1a1a1a}
		.thanatos-page .badge-conf{display:inline-block;padding:4px 12px;border:1px solid #C8A96E;color:#8a7142;border-radius:2px;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-bottom:14px}
		.thanatos-page .hero{padding:8px 0 24px;border-bottom:1px solid #e7e7e2;margin-bottom:24px}
		.thanatos-page .hero h2{margin:0 0 8px;color:#0D1B3E;font-family:Georgia,'Times New Roman',serif;font-weight:700;letter-spacing:3px;text-transform:uppercase;font-size:22px}
		.thanatos-page .hero p{margin:0;color:#5a5a55;max-width:760px;line-height:1.6;font-size:13px}
		.thanatos-page .panel{background:#fff;border:1px solid #e7e7e2;border-left:3px solid #C8A96E;border-radius:0 4px 4px 0;padding:18px 20px;margin-bottom:16px}
		.thanatos-page .panel h4{margin:0 0 14px;color:#0D1B3E;font-family:Georgia,serif;font-size:13px;letter-spacing:2px;text-transform:uppercase;font-weight:600}
		.thanatos-page .grid-row{display:grid;grid-template-columns:1fr 220px;gap:12px}
		.thanatos-page .dropzone{margin-top:8px;padding:42px 16px;border:2px dashed #C8A96E;border-radius:6px;background:rgba(200,169,110,0.04);text-align:center;cursor:pointer;transition:all .2s}
		.thanatos-page .dropzone:hover,.thanatos-page .dropzone.dragover{background:rgba(200,169,110,0.10);border-color:#a8841f}
		.thanatos-page .dropzone .icon{font-size:42px;color:#C8A96E;line-height:1;margin-bottom:8px}
		.thanatos-page .dropzone .lbl{color:#0D1B3E;font-family:Georgia,serif;font-size:15px;letter-spacing:2px;font-weight:600;margin:6px 0 2px}
		.thanatos-page .dropzone .hint{color:#5a5a55;font-size:11px;letter-spacing:1px}
		.thanatos-page .files{margin-top:14px}
		.thanatos-page .file{display:flex;align-items:center;gap:12px;padding:10px 12px;margin:5px 0;background:#fafaf5;border-left:3px solid #C8A96E;border-radius:0 3px 3px 0;font-size:13px}
		.thanatos-page .file .name{flex:1}
		.thanatos-page .file .size{color:#8a8a85;font-size:11px;font-family:monospace}
		.thanatos-page .file .status{font-size:10px;padding:2px 8px;border-radius:2px;letter-spacing:1px;text-transform:uppercase;font-family:monospace}
		.thanatos-page .st-pending{background:rgba(200,169,110,0.18);color:#8a7142}
		.thanatos-page .st-ok{background:rgba(80,200,120,0.15);color:#3d7a3d}
		.thanatos-page .st-err{background:rgba(220,80,80,0.15);color:#a13838}
		.thanatos-page .ai{margin-top:14px;padding:16px 18px;background:linear-gradient(180deg,rgba(200,169,110,0.10),rgba(200,169,110,0.04));border:1px solid rgba(200,169,110,0.4);border-radius:4px}
		.thanatos-page .ai h5{color:#8a7142;margin:0 0 8px;font-family:Georgia,serif;font-size:12px;letter-spacing:2px;text-transform:uppercase;font-weight:600}
		.thanatos-page .ai .chip{display:inline-block;padding:2px 8px;background:rgba(200,169,110,0.2);color:#8a7142;font-size:10px;letter-spacing:1px;margin-left:8px;border-radius:2px;font-family:monospace}
		.thanatos-page .ai .text{color:#1a1a1a;line-height:1.7;white-space:pre-wrap;font-size:13px}
		.thanatos-page .case-link{display:inline-block;margin-top:10px;padding:5px 12px;border:1px solid #C8A96E;color:#8a7142;border-radius:2px;font-size:11px;letter-spacing:2px;text-transform:uppercase}
		.thanatos-page .case-link:hover{background:#C8A96E;color:#fff;text-decoration:none}
		.thanatos-page .result-raw{margin-top:14px;padding:12px;background:#0A0E1A;color:#C8A96E;font-family:monospace;font-size:11px;border-radius:3px;max-height:280px;overflow:auto;white-space:pre-wrap;line-height:1.5}
		.thanatos-page .disclaimer{margin-top:24px;padding-top:14px;border-top:1px solid #e7e7e2;color:#8a8a85;font-size:11px;line-height:1.7}
		.thanatos-page .disclaimer .brand{font-family:Georgia,serif;color:#8a7142;letter-spacing:1.5px}
		.thanatos-page .actions{margin-top:16px;text-align:center}
		.thanatos-page .btn-thn{background:#C8A96E;color:#0A0E1A;border:0;padding:11px 26px;letter-spacing:2px;font-weight:700;border-radius:3px;cursor:pointer;font-size:12px;text-transform:uppercase;transition:all .2s}
		.thanatos-page .btn-thn:hover:not(:disabled){background:#a8841f;color:#fff;transform:translateY(-1px)}
		.thanatos-page .btn-thn:disabled{background:rgba(200,169,110,0.25);color:rgba(10,14,26,0.5);cursor:not-allowed}
		</style>

		<div class="thanatos-page">
			<div class="hero">
				<span class="badge-conf">ART. 234-bis c.p.p. · SHA-256 · CUSTODY LOG</span>
				<h2>Acquisizione Evidenza</h2>
				<p>Caricamento di documenti reali (proforma, contratti, screenshot, email). Ogni file è salvato come <em>privato</em>, hash SHA-256 calcolato al salvataggio, inserito in catena di custodia immutabile. L'AI agent analizza i metadati e propone i servizi del catalogo applicabili.</p>
			</div>

			<div class="panel">
				<h4>1 · Identificazione caso</h4>
				<div class="form-group" style="margin-bottom:0">
					<div class="grid-row">
						<div>
							<label class="control-label small">Titolo del caso</label>
							<input type="text" class="form-control" id="thn_case_title" placeholder="es. Verifica MT760 — Cliente XY">
						</div>
						<div>
							<label class="control-label small">Tipologia</label>
							<select class="form-control" id="thn_case_type">
								<option value="Fraud">Frode</option>
								<option value="Corporate">Corporate</option>
								<option value="Cyber">Cyber</option>
								<option value="Seizure">Sequestro</option>
								<option value="Family">Famiglia</option>
								<option value="Asset Recovery">Recupero Beni</option>
							</select>
						</div>
					</div>
				</div>
			</div>

			<div class="panel">
				<h4>2 · Documenti</h4>
				<div class="dropzone" id="thn_dropzone">
					<div class="icon">⇪</div>
					<div class="lbl">Trascina qui i documenti</div>
					<div class="hint">o clicca per selezionare · PDF, DOC, JPG, PNG, EML, TXT · max 50 MB</div>
					<input type="file" id="thn_file_input" multiple style="display:none">
				</div>
				<div class="files" id="thn_file_list"></div>
			</div>

			<div class="actions">
				<button class="btn-thn" id="thn_btn_submit" disabled>⇪ Carica + Crea Caso + Analisi AI</button>
			</div>

			<div class="ai" id="thn_ai" style="display:none;">
				<h5>Bozza AI <span class="chip" id="thn_model"></span></h5>
				<div class="text" id="thn_ai_text">In elaborazione…</div>
				<a class="case-link" id="thn_case_link" href="#">Apri caso →</a>
			</div>

			<div class="result-raw" id="thn_raw" style="display:none;"></div>

			<div class="disclaimer">
				<div class="brand">THANATOS INVESTIGAZIONI S.R.L.</div>
				<div>CUI RO 46901022 · J13/3515/2022 · CAEN 8030 · Director: Lorenzo Marrocu · Constanța, România</div>
				<div>Solo Administrator e ruoli investigativi. File privati. SHA-256 al salvataggio. Catena custodia art. 234-bis c.p.p.</div>
			</div>
		</div>
	`);
	page.body.append($body);

	// Set today as default
	const today = frappe.datetime.now_date();
	$("#thn_case_title").val("Test " + today);

	// === drag & drop logic ===
	let pendingFiles = [];
	const dz = document.getElementById("thn_dropzone");
	const fi = document.getElementById("thn_file_input");
	const fl = document.getElementById("thn_file_list");
	const btn = document.getElementById("thn_btn_submit");
	const aiBox = document.getElementById("thn_ai");
	const aiText = document.getElementById("thn_ai_text");
	const aiChip = document.getElementById("thn_model");
	const caseLink = document.getElementById("thn_case_link");
	const raw = document.getElementById("thn_raw");

	function fmt(b) {
		if (b < 1024) return b + " B";
		if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
		return (b / 1024 / 1024).toFixed(1) + " MB";
	}

	function addFiles(files) {
		for (const f of files) {
			if (f.size > 50 * 1024 * 1024) {
				frappe.show_alert({ message: __("{0} supera 50 MB", [f.name]), indicator: "red" });
				continue;
			}
			pendingFiles.push(f);
			const row = document.createElement("div");
			row.className = "file";
			row.innerHTML = `<span class="name">${frappe.utils.escape_html(f.name)}</span><span class="size">${fmt(f.size)}</span><span class="status st-pending" data-file="${frappe.utils.escape_html(f.name)}">in coda</span>`;
			fl.appendChild(row);
		}
		btn.disabled = pendingFiles.length === 0;
	}

	dz.addEventListener("click", () => fi.click());
	dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragover"); });
	dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
	dz.addEventListener("drop", (e) => {
		e.preventDefault();
		dz.classList.remove("dragover");
		addFiles(e.dataTransfer.files);
	});
	fi.addEventListener("change", (e) => addFiles(e.target.files));

	btn.addEventListener("click", async () => {
		btn.disabled = true;
		btn.textContent = "⏳ Caricamento…";
		const title = document.getElementById("thn_case_title").value.trim() || "Test upload";
		const type = document.getElementById("thn_case_type").value;
		const fd = new FormData();
		for (const f of pendingFiles) fd.append("files", f, f.name);
		fd.append("case_title", title);
		fd.append("case_type", type);

		try {
			const r = await fetch("/api/method/thanatos_intel.www.upload_test.handle_upload", {
				method: "POST",
				headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
				body: fd,
			});
			const j = await r.json();
			const m = j.message || {};
			raw.style.display = "block";
			raw.textContent = JSON.stringify(m, null, 2);

			(m.uploaded || []).forEach((u) => {
				const el = document.querySelector(`[data-file="${CSS.escape(u.original_name)}"]`);
				if (el) {
					el.className = "status st-ok";
					el.textContent = "SHA " + u.sha256.substring(0, 10);
				}
			});
			(m.errors || []).forEach((e) => {
				const el = document.querySelector(`[data-file="${CSS.escape(e.name)}"]`);
				if (el) {
					el.className = "status st-err";
					el.textContent = "errore";
				}
			});

			if (m.case_name) {
				aiBox.style.display = "block";
				aiText.textContent = "AI in analisi…";
				caseLink.href = "/app/investigation-case/" + encodeURIComponent(m.case_name);

				const ar = await fetch("/api/method/thanatos_intel.www.upload_test.analyze_case", {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-Frappe-CSRF-Token": frappe.csrf_token,
					},
					body: JSON.stringify({ case_name: m.case_name }),
				});
				const aj = await ar.json();
				const am = aj.message || {};
				aiText.textContent = am.summary || "Nessuna sintesi disponibile";
				aiChip.textContent = am.model || "";
			}

			btn.textContent = "✓ Caricato — Carica altri";
			pendingFiles = [];
			btn.disabled = false;
			// Reset visual queue (lascia status badge)
			frappe.show_alert({ message: __("Evidenza acquisita: {0} file", [(m.uploaded || []).length]), indicator: "green" });
		} catch (e) {
			raw.style.display = "block";
			raw.textContent = "ERROR: " + e.message;
			btn.disabled = false;
			btn.textContent = "⚠ Riprova";
		}
	});
};
