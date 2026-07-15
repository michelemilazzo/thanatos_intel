"""Test dell'estrattore di contenuto dei messaggi WhatsApp (ingest/whatsapp.py).

Esegue `_extract_content` in isolamento (senza importare frappe) compilando
solo quella funzione dall'AST del modulo, così gira anche nella CI statica.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "thanatos_intel" / "ingest" / "whatsapp.py").read_text(encoding="utf-8")


def _load_extract():
    tree = ast.parse(SRC)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_extract_content":
            module = ast.Module(body=[node], type_ignores=[])
            ns: dict = {}
            exec(compile(module, "<extract>", "exec"), ns)
            return ns["_extract_content"]
    raise AssertionError("_extract_content non trovata in whatsapp.py")


def test_parse_meta_uses_extractor():
    # il vecchio blocco che generava "[unsupported]" non deve più esistere
    assert "_extract_content(msg)" in SRC
    assert "or f\"[{msg.get('type', 'media')}]\"" not in SRC


def test_extract_reads_every_message_type():
    f = _load_extract()
    # testo (es. codice OTP) -> letto per intero
    assert f({"type": "text", "text": {"body": "Codice 123456"}}) == "Codice 123456"
    # caption dei media
    assert f({"type": "image", "image": {"id": "x", "caption": "foto"}}) == "foto"
    # risposta a pulsante rapido
    assert f({"type": "button", "button": {"text": "Sì, confermo"}}) == "Sì, confermo"
    # messaggi interattivi
    assert f({"type": "interactive", "interactive": {"button_reply": {"title": "Conferma"}}}) == "Conferma"
    assert f({"type": "interactive", "interactive": {"list_reply": {"title": "A", "description": "d"}}}) == "A — d"
    # reazione, posizione, contatti
    assert "reazione" in f({"type": "reaction", "reaction": {"emoji": "👍"}})
    assert f({"type": "location", "location": {"name": "Ufficio"}}) == "Ufficio"
    assert "Mario" in f({"type": "contacts", "contacts": [{"name": {"formatted_name": "Mario Rossi"}}]})


def test_unsupported_is_informative_not_silent():
    f = _load_extract()
    out = f({"type": "unsupported", "errors": [{"title": "Message type is not currently supported"}]})
    assert "non supportato" in out and "supported" in out
    # un tipo sconosciuto non perde comunque l'informazione del tipo
    assert f({"type": "sticker"}) == "[sticker]"
