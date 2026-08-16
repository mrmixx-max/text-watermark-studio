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
    "Desktop-Wrapper um die Core-Forensik (KGW-Detektion, Greenlist-"
    "Markierung, HTML-Bericht, signierte Befunde). Kein Server, kein "
    "Netzwerk — alle Aktionen rufen die Core-Funktionen direkt auf.\n\n"
    "Keys: data/key_registry.json (nur lesend). Key anlegen ueber "
    "POST /api/forensics/keys (`ai-wm serve`).\n\n"
    "Unsigniert — SmartScreen-Warnung beim Installieren ist erwartet."
)


class MainWindow(QMainWindow):
    """QMainWindow shell: menu bar, text editor, JSON results, status bar."""

    def __init__(self, controller: DesktopController | None = None):
        super().__init__()
        self.controller = controller or DesktopController()
        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 760)
        self._build_menu()
        self._build_ui()
        self._refresh_keys()

    # ------------------------------------------------------------- widgets
    def _build_menu(self) -> None:
        mbar = self.menuBar()

        m_file = mbar.addMenu("&Datei")
        act_open = QAction("&Oeffnen…", self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self.open_file)
        m_file.addAction(act_open)
        act_save = QAction("Ergebnis &speichern…", self)
        act_save.setShortcut(QKeySequence.Save)
        act_save.triggered.connect(self.save_result)
        m_file.addAction(act_save)
        m_file.addSeparator()
        act_quit = QAction("&Beenden", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_edit = mbar.addMenu("&Bearbeiten")
        act_find = QAction("&Suchen…", self)
        act_find.setShortcut(QKeySequence.Find)
        act_find.triggered.connect(self._show_find)
        m_edit.addAction(act_find)
        act_wrap = QAction("Zeilen&umbruch", self)
        act_wrap.setShortcut("Ctrl+Shift+W")
        act_wrap.setCheckable(True)
        act_wrap.setChecked(True)
        act_wrap.toggled.connect(self._toggle_wrap)
        m_edit.addAction(act_wrap)

        m_actions = mbar.addMenu("&Aktionen")
        self._menu_actions = {}
        for label, shortcut, slot in (
            ("&Detektieren", "Ctrl+D", self.detect),
            ("&Einbetten", "Ctrl+E", self.embed),
            ("&Bericht erstellen", "Ctrl+R", self.build_report),
            ("&Signieren", "Ctrl+S", self.sign),
            ("&Verifizieren", "Ctrl+Shift+V", self.verify),
            ("KGW-&Beispiel", "Ctrl+G", self.kgw_sample),
        ):
            act = QAction(label, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            m_actions.addAction(act)
            self._menu_actions[shortcut] = act

        m_help = mbar.addMenu("&Hilfe")
        act_about = QAction("&Ueber", self)
        act_about.triggered.connect(self.about)
        m_help.addAction(act_about)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)

        # --- left: editor + action row
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Schluessel:"))
        self.key_combo = QComboBox()
        self.key_combo.setMinimumWidth(220)
        self.key_combo.setToolTip(
            "Registrierte KGW-Keys mit Secret (data/key_registry.json)"
        )
        toolbar.addWidget(self.key_combo)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Sprache:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Deutsch", "de")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.setToolTip(
            "Sprache des Berichts (findings/report) — de oder en"
        )
        toolbar.addWidget(self.lang_combo)
        for label, slot in (
            ("Detektieren", self.detect),
            ("Einbetten", self.embed),
            ("Bericht", self.build_report),
            ("Signieren", self.sign),
            ("Verifizieren", self.verify),
            ("KGW-Beispiel", self.kgw_sample),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)
        left_layout.addLayout(toolbar)

        self.editor = EditorPane()
        self.editor.setPlaceholderText(
            "Text hier einfuegen, Datei > Oeffnen… waehlen oder Datei "\
            "hineinziehen.\n\n"
            "Detektieren: KGW-Z-Score + e-process gegen den gewaehlten Key "
            "(oder alle Keys).\n"
            "Einbetten: Text greenlist-markieren — die ersetzten Woerter "
            "werden gruen hervorgehoben (rueckgaengig mit Ctrl+Z).\n"
            "Bericht: HTML-Befund nach Downloads (oder tmp).\n"
            "Signieren/Verifizieren: JSON aus dem Ergebnis-Panel.\n"
            "Suchen: Ctrl+F · Zeilenumbruch: Ctrl+Shift+W."
        )
        self.editor.fileDropped.connect(self._on_file_dropped)
        left_layout.addWidget(self.editor)
        splitter.addWidget(left)

        # --- right: JSON results panel
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setPlaceholderText("Ergebnisse (JSON)")
        splitter.addWidget(self.results)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.setCentralWidget(splitter)
        self._pos_label = QLabel("Ln 1, Col 1 · 0 Zeichen")
        self.statusBar().addPermanentWidget(self._pos_label)
        self.editor.cursorPositionChanged.connect(self._update_status_pos)
        self.editor.textChanged.connect(self._update_status_pos)
        self.statusBar().showMessage("Bereit")

    def _refresh_keys(self) -> None:
        """Repopulate the key combo from the registry (keeps selection)."""
        current = self.key_combo.currentText()
        self.key_combo.clear()
        try:
            keys = self.controller.list_keys()
        except Exception as e:  # registry unreadable -> honest hint
            self.key_combo.addItem("(Registry nicht lesbar)")
            self.statusBar().showMessage(f"Key-Registry: {e}", 8000)
            return
        for k in keys:
            if k.get("family") == "kgw" and k.get("secret"):
                self.key_combo.addItem(str(k.get("key_id")))
        if self.key_combo.count() == 0:
            self.key_combo.addItem("(keine KGW-Keys)")
            self.key_combo.setEnabled(False)
        else:
            self.key_combo.setEnabled(True)
            idx = self.key_combo.findText(current)
            if idx >= 0:
                self.key_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------- helpers
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
                "Kein registrierter KGW-Key gewaehlt — Key anlegen "
                "(POST /api/forensics/keys via `ai-wm serve`) oder "
                "data/key_registry.json ergaenzen."
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
            self.statusBar().showMessage(f"Fehler: {e}", 8000)
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
            f"Ln {line}, Col {col} · {chars} Zeichen · {words} Woerter"
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
            self.statusBar().showMessage(f"Fehler: {e}", 8000)
            return
        self.editor.setPlainText(text)
        self.editor.clear_markings()
        self.results.setPlainText(
            json.dumps({"loaded": path, "chars": len(text)},
                       ensure_ascii=False, indent=2)
        )
        self.statusBar().showMessage(f"Geladen: {path}", 5000)

    # ------------------------------------------------------------- actions
    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Textdatei oeffnen", "", "Textdateien (*.txt *.md *.json);;Alle Dateien (*)"
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
            self.statusBar().showMessage(f"Fehler: {e}", 8000)
            return
        self.editor.setPlainText(text)
        self.results.setPlainText(
            json.dumps({"loaded": path, "chars": len(text)},
                       ensure_ascii=False, indent=2)
        )
        self.statusBar().showMessage(f"Geladen: {path}", 5000)

    def save_result(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Ergebnis speichern", "tws-result.json", "JSON (*.json);;Alle Dateien (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.results.toPlainText())
        except OSError as e:
            self.statusBar().showMessage(f"Fehler: {e}", 8000)
            return
        self.statusBar().showMessage(f"Gespeichert: {path}", 5000)

    def detect(self) -> None:
        self._run(
            lambda: self.controller.detect_text(self._editor_text(),
                                                self._selected_key(),
                                                lang=self._report_lang()),
            ok_status="Detektion abgeschlossen",
        )

    def embed(self) -> None:
        self._run(
            lambda: self.controller.embed_text(self._editor_text(),
                                               self._require_key()),
            ok_status="Text greenlist-markiert",
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
                "Woerter ersetzt (gruen markiert)", 8000,
            )

    def build_report(self) -> None:
        self._run(
            lambda: self.controller.build_report(
                self._editor_text(),
                self._require_key(),
                lang=self._report_lang()),
            ok_status="HTML-Bericht geschrieben",
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
            ok_status="Befund signiert",
        )

    def verify(self) -> None:
        self._run(
            lambda: self.controller.verify_report_json(
                self.controller.parse_json(self.results.toPlainText()),
                self._require_key()),
            ok_status="Signatur geprueft",
        )

    def kgw_sample(self) -> None:
        self._run(
            lambda: self.controller.kgw_sample(self._editor_text()),
            ok_status="KGW-Beispiel generiert",
        )

    def about(self) -> None:
        self.results.setPlainText(_ABOUT)
        self.statusBar().showMessage("Ueber Text Watermark Studio", 5000)


def main(argv: list[str] | None = None) -> int:
    """Entry point: ``python -m ai_watermark_toolkit.ui.desktop.app``."""
    if QApplication is None:  # pragma: no cover - missing optional dep
        print(
            "PySide6 fehlt — die Desktop-App ist ein optionaler GUI-Wrapper.\n"
            "Installieren: pip install PySide6\n"
            "Der Core (CLI/API/TUI) funktioniert ohne Qt.",
            file=sys.stderr,
        )
        return 2
    app = QApplication(sys.argv if argv is None else list(argv))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
