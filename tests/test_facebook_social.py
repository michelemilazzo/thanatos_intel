"""Test statici per il modulo Thanatos Social (integrazione Facebook).

Non richiedono un bench Frappe: verificano struttura DocType, presenza dei
job scheduler negli hooks e coerenza del client Graph.
"""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "thanatos_intel"
SOCIAL = APP / "thanatos_social"


def _load_module_source(rel_path: str) -> str:
    return (APP / rel_path).read_text(encoding="utf-8")


def test_social_module_registered():
    modules = (APP / "modules.txt").read_text(encoding="utf-8").splitlines()
    assert "Thanatos Social" in modules, "Thanatos Social non registrato in modules.txt"


def test_facebook_doctype_files_exist():
    for name in ("facebook_settings", "facebook_post"):
        folder = SOCIAL / "doctype" / name
        assert folder.exists(), f"Manca la cartella DocType: {name}"
        assert (folder / f"{name}.json").exists(), f"Manca il JSON: {name}"
        assert (folder / f"{name}.py").exists(), f"Manca il controller: {name}"


def test_facebook_post_schema():
    data = json.loads((SOCIAL / "doctype" / "facebook_post" / "facebook_post.json").read_text())
    assert data["module"] == "Thanatos Social"
    fields = {f["fieldname"]: f for f in data["fields"]}
    for expected in ("post_type", "status", "message", "scheduled_time", "fb_post_id"):
        assert expected in fields, f"Campo mancante: {expected}"
    status_opts = fields["status"]["options"].split("\n")
    for st in ("Bozza", "Programmato", "Pubblicato", "Fallito", "Annullato"):
        assert st in status_opts, f"Stato mancante: {st}"


def test_facebook_post_naming_series_expands():
    """L'autoname deve espandere la naming series in un progressivo.

    Con ``field:naming_series`` Frappe userebbe il valore GREZZO del campo
    (la stringa 'FB-POST-.#####') come nome del documento, identico per ogni
    record: dal secondo insert in poi si avrebbe un errore di chiave primaria
    duplicata, rompendo l'auto-pubblicazione. Serve ``naming_series:`` che
    tratta il valore come pattern ed espande '.#####' in un contatore."""
    data = json.loads((SOCIAL / "doctype" / "facebook_post" / "facebook_post.json").read_text())
    assert data.get("autoname") == "naming_series:", (
        "autoname deve essere 'naming_series:' per espandere il progressivo, "
        f"trovato {data.get('autoname')!r}")
    ns = next((f for f in data["fields"] if f["fieldname"] == "naming_series"), None)
    assert ns is not None and "#" in (ns.get("options") or ""), \
        "il campo naming_series deve avere un pattern con '#' (es. FB-POST-.#####)"


def test_facebook_settings_is_single():
    data = json.loads((SOCIAL / "doctype" / "facebook_settings" / "facebook_settings.json").read_text())
    assert data.get("issingle") == 1
    fields = {f["fieldname"] for f in data["fields"]}
    assert {"page_id", "page_token", "enabled"} <= fields


def test_scheduler_jobs_wired_in_hooks():
    hooks = _load_module_source("hooks.py")
    assert "facebook_post.publish_due_posts" in hooks, "publish_due_posts non schedulato"
    assert "facebook_post.refresh_published_insights" in hooks, "refresh insights non schedulato"


def test_foto_validate_accepts_image_url():
    """La validazione di un post 'Foto' deve accettare sia un file allegato
    (`image`) sia un URL immagine (`image_url`): l'automazione News passa solo
    `image_url`, quindi il controllo non deve pretendere il solo `image`."""
    src = _load_module_source(
        "thanatos_social/doctype/facebook_post/facebook_post.py")
    tree = ast.parse(src)
    validate = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "validate"), None)
    assert validate is not None, "metodo validate mancante"
    body = ast.get_source_segment(src, validate)
    assert "image_url" in body, (
        "validate() non considera image_url per i post Foto: "
        "l'auto-pubblicazione delle news con immagine fallirebbe")


def test_graph_client_defines_public_api():
    tree = ast.parse(_load_module_source("integrations/facebook_graph.py"))
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for fn in ("publish_text", "publish_photo", "fetch_post_metrics",
               "fetch_page_insights", "is_enabled", "get_settings"):
        assert fn in funcs, f"Funzione mancante nel client Graph: {fn}"
