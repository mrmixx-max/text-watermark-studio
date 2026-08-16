"""V100: Real text editor — greenlist substitution positions + EditorPane UI.

Covers the "echter Texteditor" feature:
1. Core: ``mark_greenlist`` now returns ``substitutions`` — exact character
   ranges of every token the watermarking replaced, measured against the
   FINAL (post-substitution) text so the editor can paint them directly.
2. Controller: ``embed_text`` forwards ``substitutions`` (via ``**result``).
3. EditorPane (PySide6, optional dep): line-number sidebar, find bar,
   wrap toggle, drag&drop signal, and marking paint with offsets that
   actually slice the editor text.

UI smoke runs ONLY when PySide6 is importable (optional GUI dependency):
QT_QPA_PLATFORM=offscreen, no event loop, no network, no data/ writes.
All key material lives in tmp_path.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from ai_watermark_toolkit.forensics.kgw import mark_greenlist

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

_PLAIN = ("This important change shows a new way to use the tool and "
          "helps people find the right result in time. ") * 6


@pytest.fixture()
def controller(tmp_path):
    from ai_watermark_toolkit.ui.desktop import DesktopController
    from ai_watermark_toolkit.forensics.key_registry import KeyRegistry
    registry = tmp_path / "registry.json"
    KeyRegistry(registry).add_key(dict(REG_KEY))
    return DesktopController(registry_path=registry)


# --------------------------------------------------------------- core
def test_mark_greenlist_returns_substitutions():
    """mark_greenlist reports WHERE it replaced, not just how many."""
    result = mark_greenlist(_PLAIN, REG_KEY["secret"], REG_KEY["gamma"])
    subs = result["substitutions"]
    assert result["replacements"] == len(subs)
    assert subs, "long input must produce substitutions"
    for s in subs:
        assert set(s) >= {"start", "end", "original", "replacement"}
        assert s["end"] > s["start"]
        assert s["original"]
        assert s["replacement"]
    # Offsets point into the FINAL text and slice the replacement word.
    final = result["text"]
    for s in subs:
        assert final[s["start"]:s["end"]] == s["replacement"]


def test_mark_greenlist_substitution_offsets_match_final_text():
    """Offsets must be post-substitution (length changes shift them)."""
    result = mark_greenlist(_PLAIN, REG_KEY["secret"], REG_KEY["gamma"])
    for s in result["substitutions"]:
        assert result["text"][s["start"]:s["end"]] == s["replacement"]
        assert s["original"] != s["replacement"]


def test_mark_greenlist_substitutions_abwärtskompatibel():
    """Existing return keys unchanged; new key is additive."""
    result = mark_greenlist(_PLAIN, REG_KEY["secret"], REG_KEY["gamma"])
    assert set(result) >= {"text", "replacements", "total_tokens",
                           "green_rate_after", "substitutions"}


def test_mark_greenlist_short_text_may_have_empty_substitutions():
    """Tiny inputs can hit the no-window bootstrap — substitutions may be
    empty but the call must still succeed with all keys present."""
    result = mark_greenlist("The quick brown fox", REG_KEY["secret"],
                            REG_KEY["gamma"])
    assert "substitutions" in result
    assert result["text"]


# ------------------------------------------------------------- controller
def test_embed_text_forwards_substitutions(controller):
    result = controller.embed_text(_PLAIN, REG_KEY["key_id"])
    assert result["replacements"] > 0
    assert len(result["substitutions"]) == result["replacements"]
    for s in result["substitutions"]:
        assert result["text"][s["start"]:s["end"]] == s["replacement"]


# ------------------------------------------------------------------ UI
def test_editor_pane_offscreen(monkeypatch):
    """EditorPane constructible offscreen: markings, find, wrap, drag signal."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ai_watermark_toolkit.ui.desktop.editor import EditorPane

    app = QApplication.instance() or QApplication([])
    ed = EditorPane()
    ed.setPlainText(_PLAIN)
    assert ed.blockCount() >= 1
    assert ed.wrap_enabled is True
    ed.toggle_wrap()
    assert ed.wrap_enabled is False
    ed.set_wrap(True)
    assert ed.wrap_enabled is True

    # marking paint: offsets slice the FINAL (post-substitution) text —
    # that is the documented contract: feed set_markings() the text that
    # embed() put into the editor, together with its substitutions.
    result = mark_greenlist(_PLAIN, REG_KEY["secret"], REG_KEY["gamma"])
    subs = result["substitutions"]
    ed.setPlainText(result["text"])
    ed.set_markings(subs)
    assert len(ed._markings) == len(subs)
    text = ed.toPlainText()
    for m in ed._markings:
        assert text[m["start"]:m["end"]] == m["replacement"]
    ed.clear_markings()
    assert ed._markings == []

    # find bar interaction
    ed.show_find_bar()
    ed._find_input.setText("important")
    ed.find_next()
    assert not ed._find_input.text().isspace()
    ed.hide_find_bar()

    # drag&drop: URL drop emits fileDropped with the local path
    dropped = []
    ed.fileDropped.connect(dropped.append)
    from PySide6.QtCore import QMimeData, QUrl, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtCore import QPointF
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("C:/tmp/sample.txt")])
    ev = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    ed.dropEvent(ev)
    assert dropped == ["C:/tmp/sample.txt"]


def test_editor_pane_controller_module_still_qt_free(controller):
    """The controller must stay Qt-free — the editor lives in the shell."""
    import inspect
    from ai_watermark_toolkit.ui.desktop import controller as cmod
    src = inspect.getsource(cmod)
    assert not re.search(r"^\s*(import|from)\s+(PySide6|PyQt)", src, re.M)


def test_main_window_embed_paints_markings(monkeypatch):
    """Full MainWindow: embed() replaces text AND paints the greenlist."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ai_watermark_toolkit.ui.desktop.app import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.editor.setPlainText(_PLAIN)

    win.embed()
    data = json.loads(win.results.toPlainText())
    assert data["replacements"] > 0
    assert len(win.editor._markings) == data["replacements"]
    text = win.editor.toPlainText()
    for m in win.editor._markings:
        assert text[m["start"]:m["end"]] == m["replacement"]
    assert "green-marked" in win.statusBar().currentMessage()


def test_editor_markings_invalidate_on_text_change(monkeypatch):
    """Typing or undo after embed must drop stale green highlights."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ai_watermark_toolkit.ui.desktop.editor import EditorPane

    app = QApplication.instance() or QApplication([])
    ed = EditorPane()
    result = mark_greenlist(_PLAIN, REG_KEY["secret"], REG_KEY["gamma"])
    subs = result["substitutions"]
    assert subs

    ed.setPlainText(result["text"])
    ed.set_markings(subs)
    assert ed._markings

    # typing anywhere shifts offsets -> highlights must vanish
    ed.insertPlainText("XY")
    assert ed._markings == []

    # undo back to the marked text: no stale highlights either
    ed.undo()
    assert ed.toPlainText() == result["text"]
    assert ed._markings == []

    # re-embed after edits: fresh markings work again
    ed.set_markings(subs)
    assert len(ed._markings) == len(subs)
    assert ed.toPlainText() == result["text"]


def test_paste_shortcut_not_hijacked(monkeypatch):
    """Ctrl+V must stay free for paste — no menu action may claim it."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QAction, QKeySequence
    from PySide6.QtWidgets import QApplication
    from ai_watermark_toolkit.ui.desktop.app import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()

    hijacked = []
    for act in win.findChildren(QAction):
        for seq in act.shortcuts():
            if seq.toString().lower().replace(" ", "") == "ctrl+v":
                hijacked.append((act.text(), seq.toString()))
    assert hijacked == [], f"Paste-Shortcut (Ctrl+V) durch Aktionen belegt: {hijacked}"

    # Verify bleibt erreichbar (jetzt Ctrl+Shift+V)
    verify = [a for a in win.findChildren(QAction)
              if a.text() == "&Verify"]
    assert verify and any(
        s.matches(QKeySequence("Ctrl+Shift+V")) != 0
        for s in verify[0].shortcuts()
    )


def test_llm_widget_lists_models_and_activates(monkeypatch):
    """LLM combo lists local Ollama models; selection activates one."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from ai_watermark_toolkit.ui.desktop import app as appmod

    activated = []
    monkeypatch.setattr(appmod.LocalLLMService, "list_models", lambda self: [
        {"name": "gemma-4-E4B"}, {"name": "qwen3-30b-a3b"}])
    monkeypatch.setattr(appmod.LocalLLMService, "use_model",
                        lambda self, name: activated.append(name) or {})
    monkeypatch.setattr(appmod.LocalLLMService, "status",
                        lambda self: {"model_variant": ""})

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = appmod.MainWindow()

    assert win.llm_combo.isEnabled()
    assert win.llm_combo.count() == 2
    win.llm_combo.setCurrentIndex(1)
    assert activated == ["qwen3-30b-a3b"]


def test_llm_widget_graceful_without_ollama(monkeypatch):
    """Ollama down -> combo disabled with an honest placeholder, no crash."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from ai_watermark_toolkit.ui.desktop import app as appmod

    def _boom(self):
        raise RuntimeError("ollama_unreachable: connection refused")
    monkeypatch.setattr(appmod.LocalLLMService, "list_models", _boom)

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = appmod.MainWindow()

    assert not win.llm_combo.isEnabled()
    assert win.llm_combo.currentText() == "(Ollama unreachable)"

