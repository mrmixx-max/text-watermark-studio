"""test_v139_tui_api_truth.py — Runde-2-Funde F5/F6 (selbst abgeschlossen).

F5: TUI nutzt Registry statt demo-Hardcode, level/context in Actions, keyed-detect.
F6: API-Detect rechnet KGW EINMAL (kgw_results-Reuse), embed_kgw deprecated.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from ai_watermark_toolkit.forensics.ensemble import ensemble_detect
from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
from ai_watermark_toolkit.forensics.kgw import (
    detect_kgw, embed_kgw, mark_greenlist,
)
import ai_watermark_toolkit.forensics.kgw as kgw_mod
import ai_watermark_toolkit.api.routes.forensics as forensics_route
from ai_watermark_toolkit.api.fastapi_app import app as fastapi_app

from fastapi.testclient import TestClient

KEY_A = "kgw-secret-a-0001"


# ---- F6: Ensemble reuses detect_multi_key results --------------------------

def test_ensemble_reuses_kgw_results(monkeypatch):
    text = "The quick brown fox jumps over the lazy dog near the river bank."
    keys = [{"key_id": "a", "family": "kgw", "secret": KEY_A}]
    precomputed = detect_kgw(text, KEY_A)
    calls = {"n": 0}

    def counting_detect_kgw(*a, **k):
        calls["n"] += 1
        return detect_kgw(*a, **k)

    monkeypatch.setattr(kgw_mod, "detect_kgw", counting_detect_kgw)
    result = ensemble_detect(text, keys, kgw_results={"a": precomputed})
    assert calls["n"] == 0, "kgw_results must be reused, no re-hash"
    assert result["per_key"][0]["z_score"] == precomputed["z_score"]
    assert result["per_key"][0]["verdict"] == precomputed["verdict"]


def test_api_detect_single_kgw_pass(monkeypatch, tmp_path):
    """Route calls detect_multi_key exactly once; response shape intact."""
    reg = KeyRegistry(path=tmp_path / "reg.json")
    reg.add_key({"key_id": "a", "family": "kgw", "secret": KEY_A})
    monkeypatch.setattr(forensics_route, "keys", reg)
    monkeypatch.setattr(forensics_route, "audit", _NullAudit())
    calls = {"n": 0}
    real = forensics_route.detect_multi_key

    def counting(text, registry, **kw):
        calls["n"] += 1
        return real(text, registry, **kw)

    monkeypatch.setattr(forensics_route, "detect_multi_key", counting)
    c = TestClient(fastapi_app)
    text = mark_greenlist(
        "The quick brown fox jumps over the lazy dog near the river bank "
        "while the sun sets slowly behind the old mill and the children "
        "play in the field with great joy every evening.",
        KEY_A, 0.25, seed=42, level="word", context=1)["text"]
    r = c.post("/api/forensics/detect", json={"text": text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert calls["n"] == 1, "detect_multi_key must run exactly once"
    assert {"verdict", "result", "kgw", "plugin_hits"} <= set(body)
    assert body["kgw"]["best"]["key_id"] == "a"
    assert body["kgw"]["best"]["verdict"] in (
        "watermark_detected", "redlist_detected")


def test_embed_kgw_deprecated_docstring():
    doc = (embed_kgw.__doc__ or "").upper()
    assert "DEPRECATED" in doc
    assert "MARK_GREENLIST" in doc


# ---- F5: TUI helpers + no demo hardcode ------------------------------------

def test_tui_parse_level_context():
    from ai_watermark_toolkit.ui.tui import StudioTUI
    assert StudioTUI._parse_level_context("file.txt") == ("word", 1)
    assert StudioTUI._parse_level_context("file.txt --level bpe") == ("bpe", 1)
    assert StudioTUI._parse_level_context("file.txt --context 4") == ("word", 4)
    assert StudioTUI._parse_level_context(
        "file.txt --level bpe --context 8") == ("bpe", 8)


def test_tui_file_actions_no_demo_hardcode():
    src = Path(kgw_mod.__file__).parent.parent / "ui" / "tui.py"
    content = src.read_text(encoding="utf-8")
    # file-embed/file-detect must resolve keys from the registry now
    action_block = content[content.index("def action_file_embed"):]
    assert "demo-kgw-1" not in action_block
    assert "_kgw_key()" in action_block
    assert "def action_file_detect" in content
    detect_block = content[content.index("def action_file_detect"):]
    assert "demo-kgw-1" not in detect_block
    assert "_provenance_secrets()" in detect_block


def test_tui_provenance_secrets_from_registry(tmp_path, monkeypatch):
    from ai_watermark_toolkit.ui.tui import StudioTUI
    reg_path = tmp_path / "data" / "key_registry.json"
    reg_path.parent.mkdir(exist_ok=True)
    reg_path.write_text(json.dumps({"keys": [
        {"key_id": "real-key", "family": "kgw", "secret": "real-secret",
         "status": "active"}], }), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    secrets = StudioTUI()._provenance_secrets()
    assert secrets == {"real-key": "real-secret"}


def test_tui_kgw_keys_filters_secretless(tmp_path, monkeypatch):
    from ai_watermark_toolkit.ui.tui import StudioTUI
    reg_path = tmp_path / "data" / "key_registry.json"
    reg_path.parent.mkdir(exist_ok=True)
    reg_path.write_text(json.dumps({"keys": [
        {"key_id": "with-secret", "family": "kgw", "secret": "s1",
         "status": "active"},
        {"key_id": "no-secret", "family": "kgw", "status": "active"},
    ]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    keys = StudioTUI()._kgw_keys()
    assert [k["key_id"] for k in keys] == ["with-secret"]


class _NullAudit:
    def log(self, *a, **k):
        return None

    def write(self, *a, **k):
        return None
