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

from ...llm.service import LocalLLMService
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
    "Desktop wrapper around the core forensics (KGW detection, greenlist "
    "marking, HTML report, signed findings). No server, no network — every "
    "action calls the core functions directly.\n\n"
    "Keys: data/key_registry.json (read-only). Create keys via "
    "POST /api/forensics/keys (`ai-wm serve`).\n\n"
    "Unsigned — expect a SmartScreen warning when installing."
)

# --------------------------------------------------------------------------
# i18n: the Language combo in the toolbar switches BOTH the report language
# (controller lang=) and the UI language (menus, toolbar, dialogs, status).
# Keys are stable identifiers; "de" is the startup default (combo index 0).
# --------------------------------------------------------------------------
_I18N: dict[str, dict[str, str]] = {
    "de": {
        "menu.file": "&Datei",
        "act.open": "&Öffnen…",
        "act.save": "Ergebnis &speichern…",
        "act.quit": "&Beenden",
        "menu.edit": "&Bearbeiten",
        "act.find": "&Suchen…",
        "act.wrap": "Zeilen&umbruch",
        "menu.actions": "&Aktionen",
        "act.detect": "&Erkennen",
        "act.embed": "&Einbetten",
        "act.build_report": "&Bericht erstellen",
        "act.sign": "&Signieren",
        "act.verify": "&Verifizieren",
        "act.kgw_sample": "KGW-&Beispiel",
        "menu.help": "&Hilfe",
        "act.about": "&Über",
        "sub.text_tools": "&Text-Werkzeuge",
        "act.clean_text": "&Unicode-Ebene bereinigen",
        "act.dilute_text": "KI-Formulierung &verwässern",
        "act.rewrite_text": "&Umschreiben (strukturell)",
        "act.pipeline": "&Pipeline (erkennen→bereinigen→verwässern→umschreiben)",
        "sub.file_tools": "&Datei-Werkzeuge",
        "act.inspect_file": "Metadaten &prüfen…",
        "act.clean_file": "Metadaten &bereinigen…",
        "act.embed_file": "Provenienz &einbetten…",
        "act.detect_prov": "Provenienz &erkennen…",
        "act.image_score": "&Bild-Score (SynthID)…",
        "act.watch_dir": "Ordner &überwachen…",
        "sub.findings": "&Befunde",
        "act.delta_z": "&ΔZ-Prüfung…",
        "act.finding_report": "&Befundbericht (A–D)…",
        "act.sign_report": "Befund-JSON &signieren…",
        "act.verify_report": "Signiertes JSON &verifizieren…",
        "act.gen_keypair": "ML-DSA-&Schlüsselpaar erzeugen…",
        "sub.benchmarks": "&Benchmarks",
        "act.attack_matrix": "&Angriffsmatrix…",
        "act.synthid_sweep": "&SynthID-Durchlauf…",
        "act.optimizer": "&Prompt-Optimierer…",
        "act.similarity": "&Korpus-Ähnlichkeit…",
        "sub.system": "&System",
        "act.system_state": "System&status",
        "act.check_update": "Nach &Updates suchen…",
        "act.install_model": "Lokales Modell &installieren…",
        "ui.key": "Schlüssel:",
        "ui.language": "Sprache:",
        "ui.llm": "LLM:",
        "ui.refresh": "Aktualisieren",
        "ui.detect": "Erkennen",
        "ui.embed": "Einbetten",
        "ui.report": "Bericht",
        "ui.sign": "Signieren",
        "ui.verify": "Verifizieren",
        "ui.kgw_sample": "KGW-Beispiel",
        "ui.ready": "Bereit",
        "ui.editor_placeholder": (
            "Text hier einfügen, Datei > Öffnen… wählen oder Datei ablegen.\n\n"
            "Erkennen: KGW-Z-Score + E-Prozess gegen den gewählten Schlüssel "
            "(oder alle Schlüssel).\n"
            "Einbetten: Text mit Greenlist markieren — ersetzte Wörter werden "
            "grün hervorgehoben (Rückgängig mit Strg+Z).\n"
            "Bericht: HTML-Befund nach Downloads (oder tmp).\n"
            "Signieren/Verifizieren: JSON aus dem Ergebnis-Panel.\n"
            "Suchen: Strg+F · Umbruch: Strg+Umschalt+W."
        ),
        "ui.results_placeholder": "Ergebnisse (JSON)",
        "tt.key": "Registrierte KGW-Schlüssel mit Geheimnis (data/key_registry.json)",
        "tt.lang": "UI- und Berichtssprache — Menüs und Berichte (de/en)",
        "tt.llm": (
            "Lokale Ollama-Modelle (Server: http://127.0.0.1:11434). "
            "Auswahl aktiviert das Modell für Umschreiben/Erklären."
        ),
        "tt.refresh": "Ollama-Modellliste neu laden",
        "dlg.open": "Textdatei öffnen",
        "dlg.save": "Ergebnis speichern",
        "dlg.install": "Lokales Modell installieren",
        "dlg.install_prompt": "Modellname (Ollama pull, z. B. llama3.2:3b):",
        "cap.inspect": "Metadaten prüfen",
        "cap.clean": "Metadaten bereinigen",
        "cap.embed": "Provenienz einbetten (HMAC-Signatur)",
        "cap.detect_prov": "Provenienz erkennen",
        "cap.image": "Bild-Score (SynthID)",
        "cap.watch": "Ordner überwachen (ein Durchlauf)",
        "cap.similarity_target": "Ähnlichkeits-Zieltext",
        "cap.corpus": "Korpus-Ordner",
        "cap.deltaz_before": "ΔZ-Prüfung — Datei vorher",
        "cap.deltaz_after": "ΔZ-Prüfung — Datei nachher",
        "cap.finding": "Befundbericht (A–D)",
        "cap.sign_json": "Befund-JSON signieren",
        "cap.verify_json": "Signiertes JSON verifizieren",
        "cap.keypair_dir": "Zielordner für ML-DSA-Schlüsselpaar",
        "status.detect_ok": "Erkennung abgeschlossen",
        "status.embed_ok": "Text mit Greenlist markiert",
        "status.report_ok": "HTML-Bericht geschrieben",
        "status.sign_ok": "Befund signiert",
        "status.verify_ok": "Signatur verifiziert",
        "status.kgw_ok": "KGW-Beispiel erzeugt",
        "status.clean_ok": "Unicode-Ebene bereinigt",
        "status.dilute_ok": "KI-Formulierung verwässert",
        "status.rewrite_ok": "Text umgeschrieben",
        "status.pipeline_ok": "Pipeline abgeschlossen",
        "status.inspect_ok": "Metadaten geprüft",
        "status.cleanfile_ok": "Metadaten bereinigt",
        "status.embfile_ok": "Datei signiert",
        "status.detectprov_ok": "Provenienz geprüft",
        "status.image_ok": "Bild bewertet",
        "status.watch_ok": "Ordner gescannt",
        "status.attack_ok": "Angriffsmatrix abgeschlossen",
        "status.sweep_ok": "SynthID-Durchlauf abgeschlossen",
        "status.optimizer_ok": "Optimierer abgeschlossen",
        "status.similarity_ok": "Ähnlichkeit geprüft",
        "status.sysstate_ok": "Systemstatus",
        "status.update_ok": "Update-Prüfung abgeschlossen",
        "status.install_ok": "Modell installiert",
        "status.deltaz_ok": "ΔZ-Prüfung abgeschlossen",
        "status.finding_ok": "Befundbericht erstellt",
        "status.keypair_ok": "Schlüsselpaar erzeugt",
        "msg.error": "Fehler: {e}",
        "msg.loaded": "Geladen: {path}",
        "msg.saved": "Gespeichert: {path}",
        "msg.greenlist": "Greenlist: {n} Wörter ersetzt (grün markiert)",
        "msg.key_error": "Schlüssel-Registry: {e}",
        "msg.ollama_error": "LLM/Ollama: {e}",
        "msg.llm_error": "LLM: {e}",
        "msg.llm_loaded": "Ollama: {n} Modelle geladen",
        "msg.llm_activated": "LLM-Modell aktiviert: {name}",
        "msg.about": "Über Text Watermark Studio",
    },
    "en": {
        "menu.file": "&File",
        "act.open": "&Open…",
        "act.save": "&Save Result…",
        "act.quit": "&Quit",
        "menu.edit": "&Edit",
        "act.find": "&Find…",
        "act.wrap": "&Wrap Lines",
        "menu.actions": "&Actions",
        "act.detect": "&Detect",
        "act.embed": "&Embed",
        "act.build_report": "&Build Report",
        "act.sign": "&Sign",
        "act.verify": "&Verify",
        "act.kgw_sample": "KGW &Sample",
        "menu.help": "&Help",
        "act.about": "&About",
        "sub.text_tools": "&Text Tools",
        "act.clean_text": "&Clean Unicode Layer",
        "act.dilute_text": "&Dilute AI Phrasing",
        "act.rewrite_text": "&Rewrite (Structural)",
        "act.pipeline": "&Pipeline (detect→clean→dilute→rewrite)",
        "sub.file_tools": "&File Tools",
        "act.inspect_file": "&Inspect Metadata…",
        "act.clean_file": "&Clean Metadata…",
        "act.embed_file": "&Embed Provenance…",
        "act.detect_prov": "&Detect Provenance…",
        "act.image_score": "&Image Score (SynthID)…",
        "act.watch_dir": "&Watch Directory…",
        "sub.findings": "&Findings",
        "act.delta_z": "&ΔZ Check…",
        "act.finding_report": "&Findings Report (A–D)…",
        "act.sign_report": "&Sign Findings JSON…",
        "act.verify_report": "&Verify Signed JSON…",
        "act.gen_keypair": "&Generate ML-DSA Keypair…",
        "sub.benchmarks": "&Benchmarks",
        "act.attack_matrix": "&Attack Matrix…",
        "act.synthid_sweep": "&SynthID Sweep…",
        "act.optimizer": "&Prompt Optimizer…",
        "act.similarity": "&Corpus Similarity…",
        "sub.system": "&System",
        "act.system_state": "&System State",
        "act.check_update": "&Check for Updates…",
        "act.install_model": "&Install Local Model…",
        "ui.key": "Key:",
        "ui.language": "Language:",
        "ui.llm": "LLM:",
        "ui.refresh": "Refresh",
        "ui.detect": "Detect",
        "ui.embed": "Embed",
        "ui.report": "Report",
        "ui.sign": "Sign",
        "ui.verify": "Verify",
        "ui.kgw_sample": "KGW Sample",
        "ui.ready": "Ready",
        "ui.editor_placeholder": (
            "Paste text here, choose File > Open… or drop a file in.\n\n"
            "Detect: KGW z-score + e-process against the selected key "
            "(or all keys).\n"
            "Embed: greenlist-mark the text — replaced words are "
            "highlighted green (undo with Ctrl+Z).\n"
            "Report: HTML finding to Downloads (or tmp).\n"
            "Sign/Verify: JSON from the results panel.\n"
            "Find: Ctrl+F · Wrap: Ctrl+Shift+W."
        ),
        "ui.results_placeholder": "Results (JSON)",
        "tt.key": "Registered KGW keys with secret (data/key_registry.json)",
        "tt.lang": "UI + report language — menus and reports (de/en)",
        "tt.llm": (
            "Local Ollama models (server: http://127.0.0.1:11434). Selecting activates the model for rewrite/explain."
        ),
        "tt.refresh": "Reload the Ollama model list",
        "dlg.open": "Open text file",
        "dlg.save": "Save result",
        "dlg.install": "Install local model",
        "dlg.install_prompt": "Model name (Ollama pull, e.g. llama3.2:3b):",
        "cap.inspect": "Inspect metadata",
        "cap.clean": "Clean metadata",
        "cap.embed": "Embed provenance (HMAC sign)",
        "cap.detect_prov": "Detect provenance",
        "cap.image": "Image score (SynthID)",
        "cap.watch": "Watch directory (one pass)",
        "cap.similarity_target": "Similarity target text",
        "cap.corpus": "Corpus directory",
        "cap.deltaz_before": "ΔZ check — before file",
        "cap.deltaz_after": "ΔZ check — after file",
        "cap.finding": "Findings report (A–D)",
        "cap.sign_json": "Sign findings JSON",
        "cap.verify_json": "Verify signed JSON",
        "cap.keypair_dir": "ML-DSA keypair target directory",
        "status.detect_ok": "Detection complete",
        "status.embed_ok": "Text greenlist-marked",
        "status.report_ok": "HTML report written",
        "status.sign_ok": "Finding signed",
        "status.verify_ok": "Signature verified",
        "status.kgw_ok": "KGW sample generated",
        "status.clean_ok": "Unicode layer cleaned",
        "status.dilute_ok": "AI phrasing diluted",
        "status.rewrite_ok": "Text rewritten",
        "status.pipeline_ok": "Pipeline complete",
        "status.inspect_ok": "Metadata inspected",
        "status.cleanfile_ok": "Metadata cleaned",
        "status.embfile_ok": "File signed",
        "status.detectprov_ok": "Provenance checked",
        "status.image_ok": "Image scored",
        "status.watch_ok": "Directory scanned",
        "status.attack_ok": "Attack matrix complete",
        "status.sweep_ok": "SynthID sweep complete",
        "status.optimizer_ok": "Optimizer complete",
        "status.similarity_ok": "Similarity checked",
        "status.sysstate_ok": "System state",
        "status.update_ok": "Update check complete",
        "status.install_ok": "Model installed",
        "status.deltaz_ok": "ΔZ check complete",
        "status.finding_ok": "Findings report built",
        "status.keypair_ok": "Keypair generated",
        "msg.error": "Error: {e}",
        "msg.loaded": "Loaded: {path}",
        "msg.saved": "Saved: {path}",
        "msg.greenlist": "Greenlist: {n} words replaced (green-marked)",
        "msg.key_error": "Key registry: {e}",
        "msg.ollama_error": "LLM/Ollama: {e}",
        "msg.llm_error": "LLM: {e}",
        "msg.llm_loaded": "Ollama: {n} model(s) loaded",
        "msg.llm_activated": "LLM model activated: {name}",
        "msg.about": "About Text Watermark Studio",
    },
}

_TOP_I18N = {"File": "menu.file", "Edit": "menu.edit", "Actions": "menu.actions", "Help": "menu.help"}
_SUBMENU_I18N = {
    "Text Tools": "sub.text_tools",
    "File Tools": "sub.file_tools",
    "Findings": "sub.findings",
    "Benchmarks": "sub.benchmarks",
    "System": "sub.system",
}


class MainWindow(QMainWindow):
    """QMainWindow shell: menu bar, text editor, JSON results, status bar."""

    def __init__(self, controller: DesktopController | None = None):
        super().__init__()
        self.controller = controller or DesktopController()
        self.llm = LocalLLMService()
        self._lang = "de"  # toolbar combo index 0; drives UI + report language
        self._actions: dict[str, QAction] = {}
        self._ui_labels: dict[str, QWidget] = {}
        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 760)
        self._build_menu()
        self._build_ui()
        self._refresh_keys()
        self._refresh_llm_models()

    # ------------------------------------------------------------ i18n
    def _tr(self, key: str) -> str:
        """Resolve an i18n key for the current UI language (fallback en)."""
        return _I18N.get(self._lang, _I18N["en"]).get(key, _I18N["en"].get(key, key))

    def _apply_language(self, _index: int | None = None) -> None:
        """Retranslate the whole UI from the toolbar language combo."""
        combo = getattr(self, "lang_combo", None)
        if combo is not None:
            self._lang = str(combo.currentData() or "de")
        for key, act in self._actions.items():
            act.setText(self._tr(key))
        for reg_name, menu in self._top_menus.items():
            menu.setTitle(self._tr(_TOP_I18N.get(reg_name, "menu." + reg_name.lower())))
        for reg_name, menu in self._submenu_menus.items():
            menu.setTitle(self._tr(_SUBMENU_I18N.get(reg_name, "sub." + reg_name.lower())))
        for key, widget in self._ui_labels.items():
            widget.setText(self._tr(key))
        self.key_combo.setToolTip(self._tr("tt.key"))
        self.lang_combo.setToolTip(self._tr("tt.lang"))
        self.llm_combo.setToolTip(self._tr("tt.llm"))
        self.editor.setPlaceholderText(self._tr("ui.editor_placeholder"))
        self.results.setPlaceholderText(self._tr("ui.results_placeholder"))
        self.statusBar().showMessage(self._tr("ui.ready"))

    # ------------------------------------------------------------- widgets
    def _build_menu(self) -> None:
        mbar = self.menuBar()

        m_file = mbar.addMenu(self._tr("menu.file"))
        act_open = QAction(self._tr("act.open"), self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self.open_file)
        m_file.addAction(act_open)
        self._actions["act.open"] = act_open
        act_save = QAction(self._tr("act.save"), self)
        act_save.setShortcut(QKeySequence.Save)
        act_save.triggered.connect(self.save_result)
        m_file.addAction(act_save)
        self._actions["act.save"] = act_save
        m_file.addSeparator()
        act_quit = QAction(self._tr("act.quit"), self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)
        self._actions["act.quit"] = act_quit

        m_edit = mbar.addMenu(self._tr("menu.edit"))
        act_find = QAction(self._tr("act.find"), self)
        act_find.setShortcut(QKeySequence.Find)
        act_find.triggered.connect(self._show_find)
        m_edit.addAction(act_find)
        self._actions["act.find"] = act_find
        act_wrap = QAction(self._tr("act.wrap"), self)
        act_wrap.setShortcut("Ctrl+Shift+W")
        act_wrap.setCheckable(True)
        act_wrap.setChecked(True)
        act_wrap.toggled.connect(self._toggle_wrap)
        m_edit.addAction(act_wrap)
        self._actions["act.wrap"] = act_wrap

        m_actions = mbar.addMenu(self._tr("menu.actions"))
        self._top_menus = {"File": m_file, "Edit": m_edit, "Actions": m_actions}
        self._menu_actions = {}
        for key, shortcut, slot in (
            ("act.detect", "Ctrl+D", self.detect),
            ("act.embed", "Ctrl+E", self.embed),
            ("act.build_report", "Ctrl+R", self.build_report),
            ("act.sign", "Ctrl+S", self.sign),
            ("act.verify", "Ctrl+Shift+V", self.verify),
            ("act.kgw_sample", "Ctrl+G", self.kgw_sample),
        ):
            act = QAction(self._tr(key), self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            m_actions.addAction(act)
            self._menu_actions[shortcut] = act
            self._actions[key] = act

        m_actions.addSeparator()

        # Alle Untermenüs + Aktionen werden im Window referenziert, damit
        # PySide6 sie nicht vorzeitig garbage-collected (C++-Seite lebt).
        self._submenus: dict[str, list] = {}
        self._submenu_menus: dict[str, object] = {}

        # --- Text Tools (TUI-Parität 2/3/5/7) ---------------------------
        m_text = m_actions.addMenu(self._tr("sub.text_tools"))
        self._submenu_menus["Text Tools"] = m_text
        self._submenus["Text Tools"] = []
        for key, slot in (
            ("act.clean_text", self.clean_text),
            ("act.dilute_text", self.dilute_text),
            ("act.rewrite_text", self.rewrite_text),
            ("act.pipeline", self.run_pipeline),
        ):
            act = QAction(self._tr(key), self)
            act.triggered.connect(slot)
            m_text.addAction(act)
            self._submenus["Text Tools"].append(act)
            self._actions[key] = act

        # --- File Tools (TUI-Parität 8-13) ------------------------------
        m_files = m_actions.addMenu(self._tr("sub.file_tools"))
        self._submenu_menus["File Tools"] = m_files
        self._submenus["File Tools"] = []
        for key, slot in (
            ("act.inspect_file", self.inspect_file),
            ("act.clean_file", self.clean_file),
            ("act.embed_file", self.embed_file),
            ("act.detect_prov", self.detect_file_prov),
            ("act.image_score", self.image_score),
            ("act.watch_dir", self.watch_once),
        ):
            act = QAction(self._tr(key), self)
            act.triggered.connect(slot)
            m_files.addAction(act)
            self._submenus["File Tools"].append(act)
            self._actions[key] = act

        # --- Findings (TUI-Parität 21-25) -------------------------------
        m_findings = m_actions.addMenu(self._tr("sub.findings"))
        self._submenu_menus["Findings"] = m_findings
        self._submenus["Findings"] = []
        for key, slot in (
            ("act.delta_z", self.delta_z),
            ("act.finding_report", self.finding_report),
            ("act.sign_report", self.sign_report_file),
            ("act.verify_report", self.verify_report_file),
            ("act.gen_keypair", self.generate_keypair),
        ):
            act = QAction(self._tr(key), self)
            act.triggered.connect(slot)
            m_findings.addAction(act)
            self._submenus["Findings"].append(act)
            self._actions[key] = act

        # --- Benchmarks (TUI-Parität 14-15, 19) -------------------------
        m_bench = m_actions.addMenu(self._tr("sub.benchmarks"))
        self._submenu_menus["Benchmarks"] = m_bench
        self._submenus["Benchmarks"] = []
        for key, slot in (
            ("act.attack_matrix", self.attack_matrix),
            ("act.synthid_sweep", self.synthid_sweep),
            ("act.optimizer", self.run_optimizer),
            ("act.similarity", self.similarity),
        ):
            act = QAction(self._tr(key), self)
            act.triggered.connect(slot)
            m_bench.addAction(act)
            self._submenus["Benchmarks"].append(act)
            self._actions[key] = act

        # --- System (TUI-Parität 16-18, 20) -----------------------------
        m_sys = m_actions.addMenu(self._tr("sub.system"))
        self._submenu_menus["System"] = m_sys
        self._submenus["System"] = []
        for key, slot in (
            ("act.system_state", self.system_state),
            ("act.check_update", self.check_update),
            ("act.install_model", self.install_llm_model),
        ):
            act = QAction(self._tr(key), self)
            act.triggered.connect(slot)
            m_sys.addAction(act)
            self._submenus["System"].append(act)
            self._actions[key] = act

        m_help = mbar.addMenu(self._tr("menu.help"))
        self._top_menus["Help"] = m_help
        act_about = QAction(self._tr("act.about"), self)
        act_about.triggered.connect(self.about)
        m_help.addAction(act_about)
        self._actions["act.about"] = act_about

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)

        # --- left: editor + action row
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        lbl_key = QLabel(self._tr("ui.key"))
        self._ui_labels["ui.key"] = lbl_key
        toolbar.addWidget(lbl_key)
        self.key_combo = QComboBox()
        self.key_combo.setMinimumWidth(220)
        self.key_combo.setToolTip(self._tr("tt.key"))
        toolbar.addWidget(self.key_combo)
        toolbar.addStretch(1)
        lbl_lang = QLabel(self._tr("ui.language"))
        self._ui_labels["ui.language"] = lbl_lang
        toolbar.addWidget(lbl_lang)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Deutsch", "de")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.setToolTip(self._tr("tt.lang"))
        self.lang_combo.currentIndexChanged.connect(self._apply_language)
        toolbar.addWidget(self.lang_combo)
        lbl_llm = QLabel(self._tr("ui.llm"))
        self._ui_labels["ui.llm"] = lbl_llm
        toolbar.addWidget(lbl_llm)
        self.llm_combo = QComboBox()
        self.llm_combo.setMinimumWidth(180)
        self.llm_combo.setToolTip(self._tr("tt.llm"))
        toolbar.addWidget(self.llm_combo)
        btn_llm = QPushButton(self._tr("ui.refresh"))
        btn_llm.setToolTip(self._tr("tt.refresh"))
        btn_llm.clicked.connect(self._refresh_llm_models)
        self._ui_labels["ui.refresh"] = btn_llm
        toolbar.addWidget(btn_llm)
        self.llm_combo.currentIndexChanged.connect(self._llm_selected)
        for key, slot in (
            ("ui.detect", self.detect),
            ("ui.embed", self.embed),
            ("ui.report", self.build_report),
            ("ui.sign", self.sign),
            ("ui.verify", self.verify),
            ("ui.kgw_sample", self.kgw_sample),
        ):
            btn = QPushButton(self._tr(key))
            btn.clicked.connect(slot)
            self._ui_labels[key] = btn
            toolbar.addWidget(btn)
        left_layout.addLayout(toolbar)

        self.editor = EditorPane()
        self.editor.setPlaceholderText(self._tr("ui.editor_placeholder"))
        self.editor.fileDropped.connect(self._on_file_dropped)
        left_layout.addWidget(self.editor)
        splitter.addWidget(left)

        # --- right: JSON results panel
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setPlaceholderText(self._tr("ui.results_placeholder"))
        splitter.addWidget(self.results)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.setCentralWidget(splitter)
        self._pos_label = QLabel("Ln 1, Col 1 · 0 chars")
        self.statusBar().addPermanentWidget(self._pos_label)
        self.editor.cursorPositionChanged.connect(self._update_status_pos)
        self.editor.textChanged.connect(self._update_status_pos)
        self.statusBar().showMessage(self._tr("ui.ready"))

    def _refresh_keys(self) -> None:
        """Repopulate the key combo from the registry (keeps selection)."""
        current = self.key_combo.currentText()
        self.key_combo.clear()
        try:
            keys = self.controller.list_keys()
        except Exception as e:  # registry unreadable -> honest hint
            self.key_combo.addItem("(registry unreadable)")
            self.statusBar().showMessage(self._tr("msg.key_error").format(e=e), 8000)
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
            self.statusBar().showMessage(self._tr("msg.ollama_error").format(e=e), 8000)
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
            self.statusBar().showMessage(f"Ollama: {self.llm_combo.count()} model(s) loaded", 5000)
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
            self.statusBar().showMessage(self._tr("msg.llm_activated").format(name=name), 5000)
        except Exception as e:
            self.statusBar().showMessage(self._tr("msg.llm_error").format(e=e), 8000)

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
                "data/key_registry.json.",
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
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            self.statusBar().showMessage(self._tr("msg.error").format(e=e), 8000)
            return
        if isinstance(result, dict):
            self.results.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
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
        self._pos_label.setText(f"Ln {line}, Col {col} · {chars} chars · {words} words")

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
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            self.statusBar().showMessage(self._tr("msg.error").format(e=e), 8000)
            return
        self.editor.setPlainText(text)
        self.editor.clear_markings()
        self.results.setPlainText(json.dumps({"loaded": path, "chars": len(text)}, ensure_ascii=False, indent=2))
        self.statusBar().showMessage(self._tr("msg.loaded").format(path=path), 5000)

    # ------------------------------------------------------------- actions
    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("dlg.open"),
            "",
            "Text files (*.txt *.md *.json);;All files (*)",
        )
        if not path:
            return
        try:
            text = self.controller.load_file(path)
        except Exception as e:
            self.results.setPlainText(
                json.dumps(
                    {"error": type(e).__name__, "message": str(e)},
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            self.statusBar().showMessage(self._tr("msg.error").format(e=e), 8000)
            return
        self.editor.setPlainText(text)
        self.results.setPlainText(json.dumps({"loaded": path, "chars": len(text)}, ensure_ascii=False, indent=2))
        self.statusBar().showMessage(self._tr("msg.loaded").format(path=path), 5000)

    def save_result(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("dlg.save"),
            "tws-result.json",
            "JSON (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.results.toPlainText())
        except OSError as e:
            self.statusBar().showMessage(self._tr("msg.error").format(e=e), 8000)
            return
        self.statusBar().showMessage(self._tr("msg.saved").format(path=path), 5000)

    def detect(self) -> None:
        self._run(
            lambda: self.controller.detect_text(self._editor_text(), self._selected_key(), lang=self._report_lang()),
            ok_status=self._tr("status.detect_ok"),
        )

    def embed(self) -> None:
        self._run(
            lambda: self.controller.embed_text(self._editor_text(), self._require_key()),
            ok_status=self._tr("status.embed_ok"),
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
            self.editor.set_markings((data or {}).get("substitutions") or [])
            self.statusBar().showMessage(
                self._tr("msg.greenlist").format(n=len((data or {}).get("substitutions") or [])),
                8000,
            )

    def build_report(self) -> None:
        self._run(
            lambda: self.controller.build_report(self._editor_text(), self._require_key(), lang=self._report_lang()),
            ok_status=self._tr("status.report_ok"),
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
                self._require_key(),
            ),
            ok_status=self._tr("status.sign_ok"),
        )

    def verify(self) -> None:
        self._run(
            lambda: self.controller.verify_report_json(
                self.controller.parse_json(self.results.toPlainText()),
                self._require_key(),
            ),
            ok_status=self._tr("status.verify_ok"),
        )

    def kgw_sample(self) -> None:
        self._run(
            lambda: self.controller.kgw_sample(self._editor_text()),
            ok_status=self._tr("status.kgw_ok"),
        )

    # --------------------------------------------- TUI-Paritaet: neue Slots
    # Text-Tools: wirken auf den Editor-Inhalt (wie Detect/Embed).
    def clean_text(self) -> None:
        self._run(lambda: self.controller.clean_text(self._editor_text()), ok_status=self._tr("status.clean_ok"))

    def dilute_text(self) -> None:
        self._run(lambda: self.controller.dilute_text(self._editor_text()), ok_status=self._tr("status.dilute_ok"))

    def rewrite_text(self) -> None:
        self._run(lambda: self.controller.rewrite_text(self._editor_text()), ok_status=self._tr("status.rewrite_ok"))

    def run_pipeline(self) -> None:
        self._run(lambda: self.controller.run_pipeline(self._editor_text()), ok_status=self._tr("status.pipeline_ok"))

    # Datei-basierte Aktionen: Pfad kommt aus einem native Dialog.
    def _pick_file(self, caption: str, filter_: str = "All files (*)") -> str | None:
        path, _ = QFileDialog.getOpenFileName(self, caption, "", filter_)
        return path or None

    def _pick_dir(self, caption: str) -> str | None:
        path = QFileDialog.getExistingDirectory(self, caption, "")
        return path or None

    def inspect_file(self) -> None:
        p = self._pick_file(self._tr("cap.inspect"))
        if not p:
            return
        self._run(lambda: self.controller.inspect_file(p), ok_status=self._tr("status.inspect_ok"))

    def clean_file(self) -> None:
        p = self._pick_file(self._tr("cap.clean"))
        if not p:
            return
        self._run(lambda: self.controller.clean_file(p), ok_status=self._tr("status.cleanfile_ok"))

    def embed_file(self) -> None:
        p = self._pick_file(self._tr("cap.embed"))
        if not p:
            return
        key = self._selected_key()
        self._run(lambda: self.controller.embed_file(p, key), ok_status=self._tr("status.embfile_ok"))

    def detect_file_prov(self) -> None:
        p = self._pick_file(self._tr("cap.detect_prov"))
        if not p:
            return
        self._run(lambda: self.controller.detect_file_provenance(p), ok_status=self._tr("status.detectprov_ok"))

    def image_score(self) -> None:
        p = self._pick_file(self._tr("cap.image"), "Images (*.png *.jpg *.jpeg *.webp);;All files (*)")
        if not p:
            return
        self._run(lambda: self.controller.image_score(p), ok_status=self._tr("status.image_ok"))

    def watch_once(self) -> None:
        p = self._pick_dir(self._tr("cap.watch"))
        if not p:
            return
        self._run(lambda: self.controller.watch_once(p), ok_status=self._tr("status.watch_ok"))

    def attack_matrix(self) -> None:
        self._run(lambda: self.controller.attack_matrix(), ok_status=self._tr("status.attack_ok"))

    def synthid_sweep(self) -> None:
        self._run(lambda: self.controller.synthid_sweep(), ok_status=self._tr("status.sweep_ok"))

    def run_optimizer(self) -> None:
        self._run(lambda: self.controller.run_optimizer(), ok_status=self._tr("status.optimizer_ok"))

    def similarity(self) -> None:
        target = self._pick_file(self._tr("cap.similarity_target"), "Text files (*.txt *.md);;All files (*)")
        if not target:
            return
        corpus = self._pick_dir(self._tr("cap.corpus"))
        if not corpus:
            return
        self._run(lambda: self.controller.similarity(target, corpus), ok_status=self._tr("status.similarity_ok"))

    def system_state(self) -> None:
        self._run(lambda: self.controller.system_state(), ok_status=self._tr("status.sysstate_ok"))

    def check_update(self) -> None:
        self._run(lambda: self.controller.check_update(), ok_status=self._tr("status.update_ok"))

    def install_llm_model(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        model, ok = QInputDialog.getText(self, self._tr("dlg.install"), self._tr("dlg.install_prompt"))
        if not ok or not model.strip():
            return
        self._run(lambda: self.controller.install_llm_model(model.strip()), ok_status=self._tr("status.install_ok"))

    def delta_z(self) -> None:
        before = self._pick_file(self._tr("cap.deltaz_before"), "Text files (*.txt *.md);;All files (*)")
        if not before:
            return
        after = self._pick_file(self._tr("cap.deltaz_after"), "Text files (*.txt *.md);;All files (*)")
        if not after:
            return
        key = self._selected_key()
        self._run(lambda: self.controller.delta_z(before, after, key), ok_status=self._tr("status.deltaz_ok"))

    def finding_report(self) -> None:
        p = self._pick_file(self._tr("cap.finding"), "Text files (*.txt *.md);;All files (*)")
        if not p:
            return
        key = self._selected_key()
        self._run(lambda: self.controller.finding_report(p, key_id=key), ok_status=self._tr("status.finding_ok"))

    def sign_report_file(self) -> None:
        p = self._pick_file(self._tr("cap.sign_json"), "JSON (*.json);;All files (*)")
        if not p:
            return
        key = self._selected_key()
        self._run(lambda: self.controller.sign_report_file(p, key_id=key), ok_status=self._tr("status.sign_ok"))

    def verify_report_file(self) -> None:
        p = self._pick_file(self._tr("cap.verify_json"), "JSON (*.json);;All files (*)")
        if not p:
            return
        key = self._selected_key()
        self._run(lambda: self.controller.verify_report_file(p, key_id=key), ok_status=self._tr("status.verify_ok"))

    def generate_keypair(self) -> None:
        target = self._pick_dir(self._tr("cap.keypair_dir"))
        if not target:
            return
        self._run(lambda: self.controller.generate_keypair(target), ok_status=self._tr("status.keypair_ok"))

    def about(self) -> None:
        self.results.setPlainText(_ABOUT)
        self.statusBar().showMessage("About Text Watermark Studio", 5000)


def main(argv: list[str] | None = None) -> int:
    """Entry point: ``python -m ai_watermark_toolkit.ui.desktop.app``."""
    if QApplication is None:  # pragma: no cover - missing optional dep
        return 2
    app = QApplication(sys.argv if argv is None else list(argv))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
