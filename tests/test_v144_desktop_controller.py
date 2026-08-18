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
    # P0-4: the raw secret is masked in the reported key_id
    from ai_watermark_toolkit.forensics.key_registry import mask_secret_key_id
    assert result["key_id"] == mask_secret_key_id("raw-secret-value")
    assert result["key_id"] != "raw-secret-value"
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


# ================================================== TUI-Paritaet (Text-Tools)
def test_clean_text_strips_unicode_layer(controller):
    result = controller.clean_text("hallo\u200b welt\ufe0f")
    assert result["unicode_removed"] >= 1
    assert "hallo welt" in result["text"]


def test_clean_text_empty_raises(controller):
    with pytest.raises(ValueError):
        controller.clean_text("   ")


def test_dilute_text_rewrites_phrasing(controller):
    text = ("In conclusion, it is important to note that the utilization "
            "of this methodology demonstrates significant potential. "
            "Furthermore, the implementation thereof yields results. ") * 3
    result = controller.dilute_text(text)
    assert result["changed"] >= 1
    assert isinstance(result["text"], str)
    assert result["intensity"] == "standard"


def test_rewrite_text_structural(controller):
    text = ("The quick brown fox jumps over the lazy dog. "
            "It is a beautiful day in the neighborhood. ") * 4
    result = controller.rewrite_text(text, mode="structural")
    assert result["rewritten"]
    assert result["mode"] == "structural"
    assert "similarity_ratio" in result.get("metrics", {})


def test_run_pipeline_full_chain(controller):
    text = ("This is a completely normal sentence without any markers. "
            "The weather is nice and people are happy. ") * 8
    result = controller.run_pipeline(text)
    assert "output" in result
    assert "report" in result
    assert isinstance(result["report"], dict)


# =============================================== TUI-Paritaet (Datei-Aktionen)
def test_inspect_file_unsupported_format_hint(controller, tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x00\x01\x02binary")
    result = controller.inspect_file(p)
    assert result.get("format") == "bin"
    assert "unsupported_format" in result.get("actions", [])


def test_inspect_file_missing_raises(controller, tmp_path):
    with pytest.raises(FileNotFoundError):
        controller.inspect_file(tmp_path / "missing.bin")


def test_clean_file_writes_clean_copy(controller, tmp_path):
    p = tmp_path / "meta.txt"
    p.write_text("# T\n<meta name='generator' content='X'>\nbody", encoding="utf-8")
    result = controller.clean_file(p)
    out = Path(result["output_path"])
    assert out.exists()
    assert out.name == "meta-clean.txt"


def test_embed_file_signs_and_detects_roundtrip(controller, tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text("provenance roundtrip payload", encoding="utf-8")
    emb = controller.embed_file(p, REG_KEY["key_id"])
    assert emb["key_id"] == REG_KEY["key_id"]
    out = Path(emb["output_path"])
    assert out.exists()
    det = controller.detect_file_provenance(out)
    assert det["found"] is True
    assert det["valid"] is True
    assert det["key_id"] == REG_KEY["key_id"]


def test_detect_file_provenance_no_secrets_raises(empty_controller, tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text("plain", encoding="utf-8")
    with pytest.raises(ValueError):
        empty_controller.detect_file_provenance(p)


def test_watch_once_scans_directory(controller, tmp_path):
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / "b.md").write_text("two", encoding="utf-8")
    result = controller.watch_once(tmp_path)
    assert result["reported"] >= 2
    assert any("a.txt" in line for line in result["lines"])


def test_watch_once_requires_directory(controller, tmp_path):
    p = tmp_path / "file.txt"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        controller.watch_once(p)


def test_benchmark_missing_script_hint(controller):
    with pytest.raises(FileNotFoundError):
        controller._run_benchmark("does-not-exist.py")


def test_system_state_returns_version_and_banner(controller):
    result = controller.system_state()
    assert result["local"] is True
    assert result["telemetry"] == "none"
    assert result["version"]


def test_check_update_network_failure_is_error(controller, monkeypatch):
    import urllib.request

    def _boom(*_a, **_k):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    with pytest.raises(OSError):
        controller.check_update()


def test_install_llm_model_empty_name_raises(controller):
    with pytest.raises(ValueError):
        controller.install_llm_model("   ")


def test_similarity_requires_corpus_dir(controller, tmp_path):
    target = tmp_path / "t.txt"
    target.write_text("some text", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        controller.similarity(target, tmp_path / "no-such-dir")


def test_delta_z_without_keys_raises(empty_controller, tmp_path):
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text("alpha beta gamma", encoding="utf-8")
    after.write_text("alpha beta gamma delta", encoding="utf-8")
    with pytest.raises(ValueError):
        empty_controller.delta_z(before, after)


def test_finding_report_builds(controller, tmp_path):
    p = tmp_path / "marked.txt"
    p.write_text(_marked_text(), encoding="utf-8")
    report = controller.finding_report(p, key_id=REG_KEY["key_id"])
    assert "category" in report or "findings" in report
    assert report.get("key_id") == REG_KEY["key_id"]


def test_sign_verify_report_file_roundtrip(controller, tmp_path):
    payload = {"verdict": "watermark_detected", "z_score": 4.5}
    src = tmp_path / "finding.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    signed = controller.sign_report_file(src, key_id=REG_KEY["key_id"])
    out = Path(signed["output_path"])
    assert out.exists()
    assert signed["key_id"] == REG_KEY["key_id"]
    verify = controller.verify_report_file(out, key_id=REG_KEY["key_id"])
    assert verify["valid"] is True
    assert verify["reason"] == "ok"


def test_generate_keypair_requires_mldsa_or_hint(controller, tmp_path):
    """Either cryptography is available (real keypair) or we get the
    honest install hint — never a crash."""
    try:
        result = controller.generate_keypair(tmp_path)
    except RuntimeError as e:
        assert "install" in str(e).lower() or "cryptography" in str(e).lower()
        return
    assert (tmp_path / "mldsa_private.pem").exists()
    assert (tmp_path / "mldsa_public.pem").exists()
    assert result["algorithm"].startswith("mldsa")


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
        # Menu structure present (German UI default, submenus)
        menus = [a.text() for a in window.menuBar().actions()]
        assert menus == ["&Datei", "&Bearbeiten", "&Aktionen", "&Hilfe"], menus
        # Action wiring: menu actions exist for detect/embed
        assert callable(window.detect)
        assert callable(window.embed)
        assert callable(window.build_report)
        assert callable(window.sign)
        assert callable(window.verify)
        assert callable(window.kgw_sample)
        # TUI-Parität: neue Untermenü-Slots sind verdrahtet
        for slot in ("clean_text", "dilute_text", "rewrite_text",
                     "run_pipeline", "inspect_file", "clean_file",
                     "embed_file", "detect_file_prov", "image_score",
                     "watch_once", "attack_matrix", "synthid_sweep",
                     "run_optimizer", "similarity", "system_state",
                     "check_update", "install_llm_model", "delta_z",
                     "finding_report", "sign_report_file",
                     "verify_report_file", "generate_keypair"):
            assert callable(getattr(window, slot)), slot
        # Untermenü-Struktur im Actions-Menü (TUI-Parität, deterministisch)
        actions_menu = window._top_menus["Actions"]
        # Submenu QActions are alive and attached to the Actions menu
        # (C++-owned; the underlying QMenu is retained by the window).
        sub_actions = [a for a in actions_menu.actions()
                       if a.menu() is not None]
        sub_titles = [a.text() for a in sub_actions]
        assert sub_titles == ["&Text-Werkzeuge", "&Datei-Werkzeuge",
                              "&Befunde", "&Benchmarks", "&System"], sub_titles
        expected_items = {
            "Text Tools": ["act.clean_text", "act.dilute_text",
                           "act.rewrite_text", "act.pipeline"],
            "File Tools": ["act.inspect_file", "act.clean_file",
                           "act.embed_file", "act.detect_prov",
                           "act.image_score", "act.watch_dir"],
            "Findings": ["act.delta_z", "act.finding_report",
                         "act.sign_report", "act.verify_report",
                         "act.gen_keypair"],
            "Benchmarks": ["act.attack_matrix", "act.synthid_sweep",
                           "act.optimizer", "act.similarity"],
            "System": ["act.system_state", "act.check_update",
                       "act.install_model"],
        }
        for key, act_keys in expected_items.items():
            # Read through the window's retained Python references (they keep
            # the C++ QMenu alive); the QAction→menu mapping was verified above.
            sub = window._submenu_menus[key]
            got = [a.text() for a in sub.actions()
                   if not a.isSeparator()]
            want = [window._tr(k) for k in act_keys]
            assert got == want, f"{key}: {got}"
        # i18n: switching the language combo retranslates menus + toolbar
        window.lang_combo.setCurrentIndex(1)  # English
        qt_app.processEvents()
        en_menus = [a.text() for a in window.menuBar().actions()]
        assert en_menus == ["&File", "&Edit", "&Actions", "&Help"], en_menus
        assert window._actions["act.detect"].text() == "&Detect"
        assert window._ui_labels["ui.detect"].text() == "Detect"
        assert window._submenu_menus["Text Tools"].title() == "&Text Tools"
        assert window._report_lang() == "en"
        window.lang_combo.setCurrentIndex(0)  # back to German
        qt_app.processEvents()
        assert window._actions["act.detect"].text() == "&Erkennen"
        assert window._report_lang() == "de"
        assert callable(app_mod.main)
    finally:
        window.close()
        qt_app.processEvents()
