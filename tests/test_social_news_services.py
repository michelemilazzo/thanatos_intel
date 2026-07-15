"""Test statici per l'allineamento News/Servizi → Facebook/Instagram."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "thanatos_intel"


def _funcs(rel):
    tree = ast.parse((APP / rel).read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def test_social_publisher_api():
    f = _funcs("thanatos_social/social_publisher.py")
    for fn in ("on_news_article_update", "sync_published_news",
               "publish_service_spotlight", "publish_service_now",
               "_create_and_publish_from_news", "_skip_news"):
        assert fn in f, f"manca {fn} in social_publisher"


def test_graph_has_instagram():
    f = _funcs("integrations/facebook_graph.py")
    for fn in ("get_ig_user_id", "publish_instagram", "instagram_available"):
        assert fn in f, f"manca {fn} nel client Graph"


def test_hooks_wired():
    hooks = (APP / "hooks.py").read_text(encoding="utf-8")
    assert "social_publisher.on_news_article_update" in hooks
    assert "social_publisher.sync_published_news" in hooks
    assert "social_publisher.publish_service_spotlight" in hooks


def test_facebook_post_new_fields():
    data = json.loads((APP / "thanatos_social" / "doctype" / "facebook_post" / "facebook_post.json").read_text())
    names = {f["fieldname"] for f in data["fields"]}
    assert {"also_instagram", "image_url", "source_doctype", "source_name", "instagram_post_id"} <= names


def test_facebook_settings_new_fields():
    data = json.loads((APP / "thanatos_social" / "doctype" / "facebook_settings" / "facebook_settings.json").read_text())
    names = {f["fieldname"] for f in data["fields"]}
    assert {"ig_user_id", "also_instagram", "auto_publish_news",
            "auto_publish_news_all", "service_spotlight_enabled"} <= names
