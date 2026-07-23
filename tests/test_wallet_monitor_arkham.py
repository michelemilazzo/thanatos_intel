"""Il monitor wallet non deve intasare l'Error Log quando Arkham è giù.

Quando l'API Arkham risponde 401/402/403 (chiave/abbonamento) il monitor deve
sospendere l'attribuzione e loggare una sola volta, non un traceback per ogni
wallet a ogni giro. Test statici (no bench Frappe)."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "thanatos_intel"


def _src(rel):
    return (APP / rel).read_text(encoding="utf-8")


def test_arkham_defines_unavailable_and_handles_payment():
    src = _src("osint/arkham.py")
    tree = ast.parse(src)
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert "ArkhamUnavailable" in classes, "manca l'eccezione ArkhamUnavailable"
    # _get deve gestire 401/402/403 sollevando ArkhamUnavailable (non un 402 grezzo)
    getfn = next((n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_get"), None)
    assert getfn is not None, "manca _get in arkham"
    body = ast.get_source_segment(src, getfn)
    assert "402" in body and "ArkhamUnavailable" in body, \
        "_get deve tradurre 401/402/403 in ArkhamUnavailable"


def test_monitor_suspends_attribution_gracefully():
    src = _src("osint/wallet_monitor.py")
    tree = ast.parse(src)
    # check_wallet deve poter saltare l'attribuzione
    cw = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "check_wallet"), None)
    assert cw is not None, "manca check_wallet"
    args = {a.arg for a in cw.args.args}
    assert "with_attribution" in args, "check_wallet deve accettare with_attribution"
    # snapshot_case deve gestire ArkhamUnavailable (log una volta, prosegue)
    snap = next((n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "snapshot_case"), None)
    assert snap is not None, "manca snapshot_case"
    body = ast.get_source_segment(src, snap)
    assert "ArkhamUnavailable" in body, \
        "snapshot_case deve intercettare ArkhamUnavailable per non loggare per-indirizzo"
