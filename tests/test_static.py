import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "thanatos_intel"


def test_required_app_files_exist():
    required = [
        APP / "hooks.py",
        APP / "modules.txt",
        APP / "install.py",
        APP / "api.py",
        APP / "permissions.py",
    ]
    for path in required:
        assert path.exists(), f"Missing required file: {path}"


def test_all_python_files_parse():
    for path in APP.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_all_json_files_parse():
    for path in ROOT.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_mvp_doctype_files_exist():
    doctypes = [
        "investigation_case",
        "investigation_entity",
        "investigation_evidence",
        "investigation_report",
        "risk_score",
        "chain_of_custody_event",
    ]
    for name in doctypes:
        folder = APP / "thanatos_core" / "doctype" / name
        assert folder.exists(), f"Missing DocType folder: {name}"
        assert (folder / f"{name}.json").exists(), f"Missing DocType JSON: {name}"


def test_investigation_case_has_core_links():
    """Schema attuale: relazioni con entities/evidence/report via Table (case_entities) anziche Link diretti."""
    data = json.loads((APP / "thanatos_core" / "doctype" / "investigation_case" / "investigation_case.json").read_text())
    fields = {field["fieldname"]: field for field in data["fields"]}
    # campi core attesi nello schema attuale
    assert "case_title" in fields, "missing case_title"
    assert "status" in fields, "missing status"
    assert "client" in fields, "missing client (Customer link)"
    assert "case_entities" in fields, "missing case_entities child table"
    assert fields["client"]["options"] in ("Customer", "Investigation Client")


def test_evidence_and_report_link_to_case():
    evidence = json.loads((APP / "thanatos_core" / "doctype" / "investigation_evidence" / "investigation_evidence.json").read_text())
    report = json.loads((APP / "thanatos_core" / "doctype" / "investigation_report" / "investigation_report.json").read_text())
    evidence_fields = {field["fieldname"]: field for field in evidence["fields"]}
    report_fields = {field["fieldname"]: field for field in report["fields"]}
    assert evidence_fields["investigation_case"]["options"] == "Investigation Case"
    assert report_fields["investigation_case"]["options"] == "Investigation Case"
