"""Contatore consumo AI: conta i token di ogni chiamata fatta dal bench Thanatos,
applica la tariffa nota del modello (= COSTO REALE MMOS verso il provider) e il markup
(= COSTO CLIENTE), e registra in AI Usage Log. NON servono le API usage dei provider:
contiamo noi i token (dal campo usage della risposta) perche i clienti comprano da noi.
Tariffe override-abili via site_config ai_pricing (dict model->[in,out] EUR per 1M token).
"""
import frappe

# Tariffe COSTO REALE provider in EUR per 1.000.000 token (input, output). ~USD*0.92.
PRICING = {
	"claude-opus":   (13.8, 69.0),
	"claude-sonnet": (2.76, 13.8),
	"claude-haiku":  (0.74, 3.7),
	"gpt-4o":        (2.3, 9.2),
	"gpt-4":         (27.6, 55.2),
	"deepseek":      (0.0, 0.0),
	"ollama":        (0.0, 0.0),
	"llama":         (0.0, 0.0),
	"default":       (2.76, 13.8),
}


# Tariffa FLAT di rivendita per i modelli che a noi costano 0 (free: llama/gemini/
# opencode/codex/ollama/deepseek): EUR per 1.000.000 token (input, output). Indipendente
# dal nostro costo. Override via site_config ai_flat_resale = [in, out].
FREE_FLAT = (0.5, 1.5)

# Forfait per-CHIAMATA quando i token non sono disponibili (gateway senza usage,
# chiamata legacy senza response.usage). EUR/chiamata. Override via
# site_config ai_flat_per_call. Impostare a 0 per non fatturare le chiamate untracked.
FLAT_PER_CALL_EUR = 0.02


def _flat_resale():
	v = frappe.conf.get("ai_flat_resale")
	if v and len(v) == 2:
		return float(v[0]), float(v[1])
	return FREE_FLAT


def _rate(model):
	cfg = frappe.conf.get("ai_pricing") or {}
	m = (model or "").lower()
	for key, val in list(cfg.items()) + list(PRICING.items()):
		if key != "default" and key in m:
			return tuple(val)
	return tuple(cfg.get("default") or PRICING["default"])


def _markup(client=None):
	if client:
		mk = frappe.db.get_value("Investigation Client", client, "ai_markup")
		if mk:
			return float(mk)
	try:
		return float(frappe.conf.get("infra_markup") or 3.0)
	except Exception:
		return 3.0


def real_cost(model, tokens_in, tokens_out):
	rin, rout = _rate(model)
	return round((float(tokens_in or 0) * rin + float(tokens_out or 0) * rout) / 1_000_000.0, 6)


@frappe.whitelist()
def record_usage(client, model, tokens_in=0, tokens_out=0, provider=None, reference=None, usage_date=None):
	"""Registra un consumo AI contato. client=Investigation Client."""
	from frappe.utils import nowdate
	rc = real_cost(model, tokens_in, tokens_out)
	fin, fout = _flat_resale()
	flat = round((float(tokens_in or 0) * fin + float(tokens_out or 0) * fout) / 1_000_000.0, 6)
	# Fallback per-chiamata se non abbiamo token (gateway senza usage): forfait fisso.
	# Utile per assicurare che TUTTE le chiamate AI producano revenue.
	if not (tokens_in or tokens_out):
		flat_per_call = float(frappe.conf.get("ai_flat_per_call") or FLAT_PER_CALL_EUR)
		flat = max(flat, round(flat_per_call, 6))
	cc = round(max(rc * _markup(client), flat), 6)
	prov = provider or _guess_provider(model)
	doc = frappe.get_doc({
		"doctype": "AI Usage Log", "client": client, "provider": prov, "model": model,
		"tokens_in": int(tokens_in or 0), "tokens_out": int(tokens_out or 0),
		"real_cost": rc, "client_cost": cc, "reference": reference,
		"usage_date": usage_date or nowdate(),
	})
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return {"log": doc.name, "real_cost": rc, "client_cost": cc}


def _guess_provider(model):
	m = (model or "").lower()
	if "claude" in m: return "Anthropic"
	if "gpt" in m or "openai" in m: return "OpenAI"
	if "deepseek" in m or "openrouter" in m: return "OpenRouter"
	return "Other"
