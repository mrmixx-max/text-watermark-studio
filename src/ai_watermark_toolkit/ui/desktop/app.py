"""Text Watermark Studio — Windows desktop shell (PySide6).

A thin GUI over :class:`DesktopController`: no server, no network. Every
menu action and button maps 1:1 to a controller method; results render as
JSON in the right-hand panel; errors render into the panel and the status
bar instead of modal dialogs (file dialogs excepted — those are native).

PySide6 is an OPTIONAL GUI-only dependency (the core stays stdlib-first
and is NOT coupled to Qt)::

    pip install PySide6
    python -m ai_watermark_toolkit.ui.desktop.app

Window title: "Text Watermark Studio".
"""

from __future__ import annotations

import json
import sys

from .controller import DesktopController
from .editor import EditorPane
from ...llm.service import LocalLLMService

try:  # optional GUI layer — import fails gracefully, main() explains
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction, QKeySequence, QTextCursor
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - handled in main()
    QApplication = None  # type: ignore[assignment,misc]

APP_TITLE = "Text Watermark Studio"
_ABOUT = (
    "Text Watermark Studio 2.0.0\n\n"
    "Desktop wrapper around the core forensics (KGW detection, greenlist "
    "marking, HTML report, signed findings). No server, no network — every "
    "action calls the core functions directly.\n\n"
    "Keys: data/key_registry.json (read-only). Create keys via "
    "POST /api/forensics/keys (`ai-wm serve`).\n\n"
    "Unsigned — expect a SmartScreen warning when installing."
)


class MainWindow(QMainWindow):
    """QMainWindow shell: menu bar, text editor, JSON results, status bar."""

    def __init__(self, controller: DesktopController | None = None):
        super().__init__()
        self.controller = controller or DesktopController()
        self.llm = LocalLLMService()
        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 760)
        self._build_menu()
        self._build_ui()
        self._refresh_keys()
        self._refresh_llm_models()

    # ------------------------------------------------------------- widgets
    def _build_menu(self) -> None:
        mbar = self.menuBar()

        m_file = mbar.addMenu("&File")
        act_open = QAction("&Open…", self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self.open_file)
        m_file.addAction(act_open)
        act_save = QAction("&Save Result…", self)
        act_save.setShortcut(QKeySequence.Save)
        act_save.triggered.connect(self.save_result)
        m_file.addAction(act_save)
        m_file.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_edit = mbar.addMenu("&Edit")
        act_find = QAction("&Find…", self)
        act_find.setShortcut(QKeySequence.Find)
        act_find.triggered.connect(self._show_find)
        m_edit.addAction(act_find)
        act_wrap = QAction("&Wrap Lines", self)
        act_wrap.setShortcut("Ctrl+Shift+W")
        act_wrap.setCheckable(True)
        act_wrap.setChecked(True)
        act_wrap.toggled.connect(self._toggle_wrap)
        m_edit.addAction(act_wrap)

        m_actions = mbar.addMenu("&Actions")
        self._menu_actions = {}
        for label, shortcut, slot in (
            ("&Detect", "Ctrl+D", self.detect),
            ("&Embed", "Ctrl+E", self.embed),
            ("&Build Report", "Ctrl+R", self.build_report),
            ("&Sign", "Ctrl+S", self.sign),
            ("&Verify", "Ctrl+Shift+V", self.verify),
            ("KGW &Sample", "Ctrl+G", self.kgw_sample),
        ):
            act = QAction(label, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            m_actions.addAction(act)
            self._menu_actions[shortcut] = act

        m_help = mbar.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self.about)
        m_help.addAction(act_about)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)

        # --- left: editor + action row
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Key:"))
        self.key_combo = QComboBox()
        self.key_combo.setMinimumWidth(220)
        self.key_combo.setToolTip(
            "Registered KGW keys with secret (data/key_registry.json)"
        )
        toolbar.addWidget(self.key_combo)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Deutsch", "de")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.setToolTip(
            "Report language (findings/report) — de or en"
        )
        toolbar.addWidget(self.lang_combo)
        toolbar.addWidget(QLabel("LLM:"))
        self.llm_combo = QComboBox()
        self.llm_combo.setMinimumWidth(180)
        self.llm_combo.setToolTip(
            "Local Ollama models (server: http://127.0.0.1:11434). "
            "Selecting activates the model for rewrite/explain."
        )
        toolbar.addWidget(self.llm_combo)
        btn_llm = QPushButton("Refresh")
        btn_llm.setToolTip("Reload the Ollama model list")
        btn_llm.clicked.connect(self._refresh_llm_models)
        toolbar.addWidget(btn_llm)
        self.llm_combo.currentIndexChanged.connect(self._llm_selected)
        for label, slot in (
            ("Detect", self.detect),
            ("Embed", self.embed),
            ("Report", self.build_report),
            ("Sign", self.sign),
            ("Verify", self.verify),
            ("KGW Sample", self.kgw_sample),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)
        left_layout.addLayout(toolbar)

        self.editor = EditorPane()
        self.editor.setPlaceholderText(
            "Paste text here, choose File > Open… or drop a file in.\n\n"
            "Detect: KGW z-score + e-process against the selected key "
            "(or all keys).\n"
            "Embed: greenlist-mark the text — replaced words are "
            "highlighted green (undo with Ctrl+Z).\n"
            "Report: HTML finding to Downloads (or tmp).\n"
            "Sign/Verify: JSON from the results panel.\n"
            "Find: Ctrl+F · Wrap: Ctrl+Shift+W."
        )
        self.editor.fileDropped.connect(self._on_file_dropped)
        left_layout.addWidget(self.editor)
        splitter.addWidget(left)

        # --- right: JSON results panel
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setPlaceholderText("Results (JSON)")
        splitter.addWidget(self.results)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.setCentralWidget(splitter)
        self._pos_label = QLabel("Ln 1, Col 1 · 0 chars")
        self.statusBar().addPermanentWidget(self._pos_label)
        self.editor.cursorPositionChanged.connect(self._update_status_pos)
        self.editor.textChanged.connect(self._update_status_pos)
        self.statusBar().showMessage("Ready")

    def _refresh_keys(self) -> None:
        """Repopulate the key combo from the registry (keeps selection)."""
        current = self.key_combo.currentText()
        self.key_combo.clear()
        try:
            keys = self.controller.list_keys()
        except Exception as e:  # registry unreadable -> honest hint
            self.key_combo.addItem("(registry unreadable)")
            self.statusBar().showMessage(f"Key registry: {e}", 8000)
            return
        for k in keys:
            if k.get("family") == "kgw" and k.get("secret"):
                self.key_combo.addItem(str(k.get("key_id")))
        if self.key_combo.count() == 0:
            self.key_combo.addItem("(no KGW keys)")
            self.key_combo.setEnabled(False)
        else:
            self.key_combo.setEnabled(True)
            idx = self.key_combo.findText(current)
            if idx >= 0:
                self.key_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------- helpers
    def _refresh_llm_models(self) -> None:
        """Repopulate the LLM combo from the local Ollama server."""
        self.llm_combo.blockSignals(True)
        self.llm_combo.clear()
        try:
            models = self.llm.list_models()
        except Exception as e:  # Ollama offline/unreachable -> honest hint
            self.llm_combo.addItem("(Ollama unreachable)")
            self.llm_combo.setEnabled(False)
            self.statusBar().showMessage(f"LLM/Ollama: {e}", 8000)
            self.llm_combo.blockSignals(False)
            return
        for model in models:
            name = model.get("name", "")
            if name:
                self.llm_combo.addItem(name)
        if self.llm_combo.count() == 0:
            self.llm_combo.addItem("(no models)")
            self.llm_combo.setEnabled(False)
        else:
            self.llm_combo.setEnabled(True)
            current = self.llm.status().get("model_variant", "")
            idx = self.llm_combo.findText(current) if current else -1
            if idx >= 0:
                self.llm_combo.setCurrentIndex(idx)
            self.statusBar().showMessage(
                f"Ollama: {self.llm_combo.count()} model(s) loaded", 5000
            )
        self.llm_combo.blockSignals(False)

    def _llm_selected(self, index: int) -> None:
        """Persist the chosen model so rewrite/explain use it."""
        if index < 0:
            return
        name = self.llm_combo.currentText()
        if name.startswith("("):
            return
        try:
            self.llm.use_model(name)
            self.statusBar().showMessage(f"LLM model activated: {name}", 5000)
        except Exception as e:
            self.statusBar().showMessage(f"LLM: {e}", 8000)

    def _selected_key(self) -> str | None:
        key = self.key_combo.currentText()
        if not key or key.startswith("("):
            return None
        return key

    def _require_key(self) -> str:
        """Raise a readable error when no registry key is selected."""
        key = self._selected_key()
        if key is None:
            raise ValueError(
                "No registered KGW key selected — create one "
                "(POST /api/forensics/keys via `ai-wm serve`) or add it to "
                "data/key_registry.json."
            )
        return key

    def _editor_text(self) -> str:
        return self.editor.toPlainText()

    def _run(self, fn, ok_status: str = "OK") -> None:
        """Execute a controller call; JSON into the panel, errors non-modal."""
        try:
            result = fn()
        except Exception as e:  # all controller errors surface here
            self.results.setPlainText(
                json.dumps(
                    {"error": type(e).__name__, "message": str(e)},
                    ensure_ascii=False, indent=2,
                )
            )
            self.statusBar().showMessage(f"Error: {e}", 8000)
            return
        if isinstance(result, dict):
            self.results.setPlainText(
                json.dumps(result, ensure_ascii=False, indent=2)
            )
        elif result is not None:
            self.results.setPlainText(str(result))
        self.statusBar().showMessage(ok_status, 8000)

    # ------------------------------------------------- editor status/edits
    def _update_status_pos(self) -> None:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        chars = len(self.editor.toPlainText())
        words = len(self.editor.toPlainText().split())
        self._pos_label.setText(
            f"Ln {line}, Col {col} · {chars} chars · {words} words"
        )

    def _show_find(self) -> None:
        self.editor.show_find_bar()

    def _toggle_wrap(self, checked: bool) -> None:
        self.editor.set_wrap(checked)

    def _on_file_dropped(self, path: str) -> None:
        try:
            text = self.controller.load_file(path)
        except Exception as e:
            self.results.setPlainText(
                json.dumps(
                    {"error": type(e).__name__, "message": str(e)},
                    ensure_ascii=False, indent=2,
                )
            )
            self.statusBar().showMessage(f"Error: {e}", 8000)
            return
        self.editor.setPlainText(text)
        self.editor.clear_markings()
        self.results.setPlainText(
            json.dumps({"loaded": path, "chars": len(text)},
                       ensure_ascii=False, indent=2)
        )
        self.statusBar().showMessage(f"Loaded: {path}", 5000)

    # ------------------------------------------------------------- actions
    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open text file", "", "Text files (*.txt *.md *.json);;All files (*)"
        )
        if not path:
            return
        try:
            text = self.controller.load_file(path)
        except Exception as e:
            self.results.setPlainText(
                json.dumps(
                    {"error": type(e).__name__, "message": str(e)},
                    ensure_ascii=False, indent=2,
                )
            )
            self.statusBar().showMessage(f"Error: {e}", 8000)
            return
        self.editor.setPlainText(text)
        self.results.setPlainText(
            json.dumps({"loaded": path, "chars": len(text)},
                       ensure_ascii=False, indent=2)
        )
        self.statusBar().showMessage(f"Loaded: {path}", 5000)

    def save_result(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save result", "tws-result.json", "JSON (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.results.toPlainText())
        except OSError as e:
            self.statusBar().showMessage(f"Error: {e}", 8000)
            return
        self.statusBar().showMessage(f"Saved: {path}", 5000)

    def detect(self) -> None:
        self._run(
            lambda: self.controller.detect_text(self._editor_text(),
                                                self._selected_key(),
                                                lang=self._report_lang()),
            ok_status="Detection complete",
        )

    def embed(self) -> None:
        self._run(
            lambda: self.controller.embed_text(self._editor_text(),
                                               self._require_key()),
            ok_status="Text greenlist-marked",
        )
        # Non-destructive takeover of the marked text (undoable via Ctrl+Z),
        # then paint the greenlist substitutions so the user SEES the marks.
        try:
            data = json.loads(self.results.toPlainText())
            marked = data.get("text")
        except Exception:
            data, marked = None, None
        if marked:
            cursor = self.editor.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(marked)
            self.editor.textCursor().clearSelection()
            self.editor.set_markings(
                (data or {}).get("substitutions") or []
            )
            self.statusBar().showMessage(
                f"Greenlist: {len((data or {}).get('substitutions') or [])} "
                "words replaced (green-marked)", 8000,
            )

    def build_report(self) -> None:
        self._run(
            lambda: self.controller.build_report(
                self._editor_text(),
                self._require_key(),
                lang=self._report_lang()),
            ok_status="HTML report written",
        )

    def _report_lang(self) -> str:
        """Selected report language from the toolbar combo (default de)."""
        combo = getattr(self, "lang_combo", None)
        if combo is None:
            return "de"
        return str(combo.currentData() or "de")

    def sign(self) -> None:
        self._run(
            lambda: self.controller.sign_report_json(
                self.controller.parse_json(self.results.toPlainText()),
                self._require_key()),
            ok_status="Finding signed",
        )

    def verify(self) -> None:
        self._run(
            lambda: self.controller.verify_report_json(
                self.controller.parse_json(self.results.toPlainText()),
                self._require_key()),
            ok_status="Signature verified",
        )

    def kgw_sample(self) -> None:
        self._run(
            lambda: self.controller.kgw_sample(self._editor_text()),
            ok_status="KGW sample generated",
        )

    def about(self) -> None:
        self.results.setPlainText(_ABOUT)
        self.statusBar().showMessage("About Text Watermark Studio", 5000)


def main(argv: list[str] | None = None) -> int:
    """Entry point: ``python -m ai_watermark_toolkit.ui.desktop.app``."""
    if QApplication is None:  # pragma: no cover - missing optional dep
        print(
            "PySide6 is missing — the desktop app is an optional GUI wrapper.\n"
            "Install: pip install PySide6\n"
            "The core (CLI/API/TUI) works without Qt.",
            file=sys.stderr,
        )
        return 2
    app = QApplication(sys.argv if argv is None else list(argv))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
