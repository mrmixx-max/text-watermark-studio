"""D2: Desktop-App (Windows) — Qt-free DesktopController + UI smoke.

Controller tests run in a plain CPython process (no Qt): every core call
(detect / embed / report / sign / verify / list_keys / kgw_sample) is
exercised against a tmp-path KeyRegistry, plus the error paths.

UI smoke runs ONLY when PySide6 is importable (optional GUI dependency):
QT_QPA_PLATFORM=offscreen, window title, close() — no event loop, no
network, no data/ writes. All key material lives in tmp_path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ai_watermark_toolkit.ui.desktop import DesktopController
from ai_watermark_toolkit.ui.desktop.controller import _key_hint

# One registry key used across the controller tests (secret is a real
# detection secret; KGW is a demo-scale text-only scheme).
REG_KEY = {
    "key_id": "desktop-test-1",
    "family": "kgw",
    "status": "active",
    "owner": "test",
    "trigger_phrase": "",
    "notes": "test key",
    "secret": "desktop-test-secret-0001",
    "gamma": 0.25,
}


@pytest.fixture()
def controller(tmp_path) -> DesktopController:
    """Controller bound to a tmp registry seeded with one KGW key."""
    registry = tmp_path / "registry.json"
    from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
    KeyRegistry(registry).add_key(dict(REG_KEY))
    return DesktopController(registry_path=registry)


@pytest.fixture()
def empty_controller(tmp_path) -> DesktopController:
    return DesktopController(registry_path=tmp_path / "empty-registry.json")


def _marked_text() -> str:
    """Sampler text generated with the REG_KEY secret (mark→detect roundtrip)."""
    from ai_watermark_toolkit.generation.kgw_sampler import generate_marked_text
    return generate_marked_text(key=REG_KEY["secret"], gamma=0.25,
                                bias_strength=2.0, n_tokens=250, seed=42)["text"]


# ------------------------------------------------------------ registry / keys
def test_list_keys_from_tmp_registry(controller):
    keys = controller.list_keys()
    assert len(keys) == 1
    assert keys[0]["key_id"] == REG_KEY["key_id"]
    assert keys[0]["secret"] == REG_KEY["secret"]


def test_list_keys_empty_registry(empty_controller):
    assert empty_controller.list_keys() == []


def test_detect_without_keys_reports_hint(empty_controller):
    with pytest.raises(ValueError) as exc:
        empty_controller.detect_text("some text that is long enough to detect")
    assert "Keine KGW-Keys" in str(exc.value)
    assert "data/key_registry.json" in _key_hint(Path("data/key_registry.json"))


def test_resolve_empty_key_is_error(controller):
    with pytest.raises(ValueError) as exc:
        controller.detect_text("some text", "   ")
    assert "Kein Key angegeben" in str(exc.value)


def test_unknown_key_id_is_raw_secret_fallback(controller):
    """CLI contract: a non-registry argument is a raw secret, not an error."""
    result = controller.detect_text("some plain text", "raw-secret-value")
    assert result["key_id"] == "raw-secret-value"
    assert result["tested_keys"] == 1


# ------------------------------------------------------------------ detect
def test_detect_file_finds_watermark(controller, tmp_path):
    marked = _marked_text()
    path = tmp_path / "marked.txt"
    path.write_text(marked, encoding="utf-8")
    result = controller.detect_file(str(path), REG_KEY["key_id"])
    assert result["verdict"] == "watermark_detected"
    assert result["key_id"] == REG_KEY["key_id"]
    assert result["z_score"] >= 4.0
    assert result["tested_keys"] == 1
    # e-process companion (stdlib, always available)
    assert result["e_value"]["detected"] is True
    assert result["e_value"]["verdict"] == "e_value_detected"


def test_detect_file_raw_secret(controller, tmp_path):
    path = tmp_path / "marked.txt"
    path.write_text(_marked_text(), encoding="utf-8")
    result = controller.detect_file(str(path), REG_KEY["secret"])
    assert result["verdict"] == "watermark_detected"


def test_detect_clean_text_no_signal(controller):
    result = controller.detect_text("The quick brown fox jumps over the lazy "
                                    "dog while the sun sets behind the hills.")
    # The honest guarantee is "no strong signal": clean text must never
    # produce a watermark/redlist verdict with a random key.
    assert result["verdict"] not in ("watermark_detected", "redlist_detected")


def test_detect_all_keys_multi(controller):
    # Two keys: only the real one matches -> multi-key path must pick it.
    from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
    KeyRegistry(controller.registry_path).add_key({
        "key_id": "desktop-test-2", "family": "kgw",
        "secret": "completely-different-secret", "gamma": 0.25,
    })
    result = controller.detect_text(_marked_text())
    assert result["tested_keys"] == 2
    assert result["key_id"] == REG_KEY["key_id"]
    assert "bonferroni" in result["note"]


# ------------------------------------------------------------------- embed
def test_embed_text_marks_and_roundtrips(controller):
    plain = ("This important change shows a new way to use the tool and "
             "helps people find the right result in time. ") * 6
    result = controller.embed_text(plain, REG_KEY["key_id"])
    assert result["key_id"] == REG_KEY["key_id"]
    assert result["replacements"] > 0
    assert result["green_rate_after"] > 0.25
    assert result["text"] != plain
    # The marked text must detect with the same key.
    det = controller.detect_text(result["text"], REG_KEY["key_id"])
    assert det["verdict"] == "watermark_detected"


def test_embed_unknown_key_is_error(controller):
    with pytest.raises(ValueError) as exc:
        controller.embed_text("some text", "not-registered")
    assert "nicht in der Registry" in str(exc.value)


# ------------------------------------------------------------------ report
def test_build_report_writes_html(controller, tmp_path):
    out_dir = tmp_path / "reports"
    result = controller.build_report(_marked_text(), REG_KEY["key_id"],
                                     output_dir=out_dir)
    html_path = Path(result["html_path"])
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "Forensik-Befund" in html
    assert "WASSERZEICHEN NACHGEWIESEN" in html
    assert "desktop-test-1" in html  # key label, secret never shown
    assert REG_KEY["secret"] not in html
    assert result["verdict"] == "watermark_detected"


def test_build_report_default_dir_is_downloads_or_tmp(controller, monkeypatch):
    # Force the fallback branch: no Downloads dir -> tmp is used.
    import tempfile
    fake_home = tempfile.mkdtemp()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: Path(fake_home)))
    result = controller.build_report(_marked_text(), REG_KEY["key_id"])
    out = Path(result["html_path"])
    assert out.exists()
    assert out.suffix == ".html"


# ------------------------------------------------------------ sign / verify
def test_sign_verify_roundtrip(controller):
    payload = {"verdict": "watermark_detected", "z_score": 4.5,
               "key_id": REG_KEY["key_id"], "text_sample": "abc"}
    signed = controller.sign_report_json(payload, REG_KEY["key_id"])
    assert signed["signature"]["algorithm"] == "hmac-sha256"
    assert signed["signature"]["key_id"] == REG_KEY["key_id"]
    assert "digest" in signed["signature"]
    verify = controller.verify_report_json(signed, REG_KEY["key_id"])
    assert verify["valid"] is True
    assert verify["reason"] == "ok"


def test_verify_detects_tampering(controller):
    payload = {"verdict": "watermark_detected", "z_score": 4.5}
    signed = controller.sign_report_json(payload, REG_KEY["key_id"])
    signed["z_score"] = 99.9
    verify = controller.verify_report_json(signed, REG_KEY["key_id"])
    assert verify["valid"] is False
    assert verify["tampered_fields"] == ["z_score"]


def test_sign_wrong_key_is_error(controller):
    with pytest.raises(ValueError) as exc:
        controller.sign_report_json({"a": 1}, "not-registered")
    assert "nicht in der Registry" in str(exc.value)


# ------------------------------------------------------------------ sampler
def test_kgw_sample_generates_and_detects(controller):
    result = controller.kgw_sample(seed=7)
    assert result["generated"]["n_tokens"] >= 200
    assert result["generated"]["green_rate"] > 0.5
    assert result["detected"]["verdict"] == "watermark_detected"
    assert result["seed"] == 7


# -------------------------------------------------------------- error paths
def test_load_file_missing_raises(controller, tmp_path):
    with pytest.raises(FileNotFoundError):
        controller.load_file(tmp_path / "missing.txt")


def test_load_file_directory_raises(controller, tmp_path):
    with pytest.raises(IsADirectoryError):
        controller.load_file(tmp_path)


def test_detect_empty_text_raises(controller):
    with pytest.raises(ValueError):
        controller.detect_text("   ")


def test_parse_json_invalid(controller):
    with pytest.raises(ValueError):
        controller.parse_json("{not json")
    with pytest.raises(ValueError):
        controller.parse_json("[1, 2, 3]")  # list, not dict
    with pytest.raises(ValueError):
        controller.parse_json("")


def test_controller_module_has_no_qt(controller):
    """The controller must import and run without Qt installed."""
    import re
    import sys
    mod = sys.modules["ai_watermark_toolkit.ui.desktop.controller"]
    src = Path(mod.__file__).read_text(encoding="utf-8")
    # No Qt import statements (the word may appear in docs — imports are
    # what would couple the controller to the GUI layer).
    assert not re.search(r"^\s*(import|from)\s+(PySide6|PyQt)", src, re.M)


# ============================================================== UI smoke
def test_ui_smoke_offscreen(monkeypatch):
    """Window constructible offscreen: title, widgets, clean close.

    Skipped when PySide6 is not installed (optional GUI dependency).
    """
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ai_watermark_toolkit.ui.desktop import app as app_mod

    qt_app = QApplication.instance() or QApplication([])
    window = app_mod.MainWindow()
    try:
        assert window.windowTitle() == app_mod.APP_TITLE == "Text Watermark Studio"
        assert window.editor is not None
        assert window.results.isReadOnly() is True
        assert window.key_combo is not None
        # Menu structure present
        menus = [a.text() for a in window.menuBar().actions()]
        assert any("Datei" in m for m in menus)
        assert any("Aktionen" in m for m in menus)
        assert any("Hilfe" in m for m in menus)
        # Action wiring: menu actions exist for detect/embed
        assert callable(window.detect)
        assert callable(window.embed)
        assert callable(window.build_report)
        assert callable(window.sign)
        assert callable(window.verify)
        assert callable(window.kgw_sample)
        assert callable(app_mod.main)
    finally:
        window.close()
        qt_app.processEvents()
