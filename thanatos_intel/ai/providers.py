"""
Thin AI dispatcher used by news ingestion to rewrite excerpts/body in Thanatos voice.
Tries Ollama (local) first, then Claude CLI, then no-op fallback.
"""
import json
import re
import shutil
import subprocess
import frappe


SYSTEM_PROMPT = (
	"Sei l'editor di Thanatos Intel, agenzia europea di intelligence investigativa. "
	"Riscrivi la notizia con tono autorevole, sobrio, professionale, senza sensazionalismo. "
	"Non inventare dati. Non aggiungere virgolette. Conserva i fatti. "
	"Lingua: {lang}. "
	"Restituisci JSON con chiavi: excerpt (max 280 caratteri, no HTML), "
	"body_html (HTML semplice con <p>, <ul>, <li>, <strong> — niente immagini, niente link a meno che non siano nell'originale)."
)


def _user_prompt(title: str, body: str) -> str:
	return (
		f"Titolo originale: {title}\n\n"
		f"Corpo originale (testo grezzo):\n{body[:3500]}\n\n"
		"Rispondi SOLO con JSON valido."
	)


def _try_ollama(prompt: str, system: str, model: str | None = None) -> str | None:
	model = model or frappe.conf.get("ollama_news_model") or "llama3.1:8b"
	host = frappe.conf.get("ollama_host") or "http://10.10.0.4:11434"
	try:
		import requests
		r = requests.post(
			f"{host}/api/generate",
			json={"model": model, "system": system, "prompt": prompt,
			      "stream": False, "format": "json",
			      "options": {"temperature": 0.4}},
			timeout=60,
		)
		if r.ok:
			j = r.json() or {}
			usage = {"provider": "OpenCode", "model": "ollama:" + model,
			         "tokens_in": j.get("prompt_eval_count", 0),
			         "tokens_out": j.get("eval_count", 0)}
			return (j.get("response"), usage)
	except Exception:
		return (None, None)
	return (None, None)


def _try_claude_cli(prompt: str, system: str) -> str | None:
	cli = shutil.which("claude") or "/usr/local/bin/claude"
	if not cli:
		return None
	try:
		full = f"<system>{system}</system>\n\n{prompt}"
		r = subprocess.run([cli, "--print", "--output-format", "json"], input=full,
		                   capture_output=True, text=True, timeout=90)
		if r.returncode == 0 and r.stdout.strip():
			try:
				j = json.loads(r.stdout)
				u = j.get("usage") or {}
				usage = {"provider": "Anthropic", "model": j.get("model") or "claude",
				         "tokens_in": u.get("input_tokens", 0),
				         "tokens_out": u.get("output_tokens", 0)}
				return (j.get("result") or "", usage)
			except Exception:
				return (r.stdout.strip(), None)
	except Exception:
		return (None, None)
	return (None, None)


def _extract_json(text: str) -> dict | None:
	if not text:
		return None
	# direct
	try:
		return json.loads(text)
	except Exception:
		pass
	# strip ```json
	m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
	if m:
		try:
			return json.loads(m.group(1))
		except Exception:
			pass
	# first {...}
	m = re.search(r"\{[\s\S]+\}", text)
	if m:
		try:
			return json.loads(m.group(0))
		except Exception:
			return None
	return None


def rewrite_news(title: str, body: str, language: str = "it") -> dict | None:
	system = SYSTEM_PROMPT.format(lang=language)
	prompt = _user_prompt(title, body)
	for provider in (_try_ollama, _try_claude_cli):
		raw, usage = provider(prompt, system)
		js = _extract_json(raw) if raw else None
		if js and (js.get("excerpt") or js.get("body_html")):
			_meter(usage, "news_rewrite")
			return js
	return None


def _meter(usage, reference=None, client=None):
	"""Conta i token di una chiamata AI (consumo bench Thanatos)."""
	if not usage:
		return
	try:
		from thanatos_intel.billing.ai_meter import record_usage
		record_usage(client, usage.get("model"), usage.get("tokens_in", 0),
		             usage.get("tokens_out", 0), provider=usage.get("provider"),
		             reference=reference)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ai_meter news")
