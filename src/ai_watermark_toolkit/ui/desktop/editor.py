"""EditorPane — the real text editor for the Text Watermark Studio shell.

A QPlainTextEdit subclass that is actually usable as an editor:
line numbers, find bar (Ctrl+F), current-line highlight, word-wrap
toggle, drag&drop file open, and — the part that makes it a *watermark*
editor — greenlist substitution highlighting. After an embed the caller
feeds :meth:`set_markings` with the ``substitutions`` list returned by
``mark_greenlist`` (via the controller) and every token that was replaced
by the watermarking step is painted with a tinted background, so the user
SEES what the watermark did to the text.

Design rules (mirroring the desktop shell):
- This module is part of the Qt shell layer (``ui.desktop``), so Qt is
  expected here — unlike ``controller.py`` which must stay Qt-free.
- No core logic: everything renderable comes in as plain data
  (``set_markings``), everything interactive goes out as signals
  (``fileDropped``). The shell wires those to the controller.
- No network, no server, no file writes (file I/O stays in the
  controller; drag&drop only emits the dropped path).
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Greenlist substitution background (tinted, readable with dark text).
_SUB_BG = QColor("#C8E6C9")  # light green
# Search match backgrounds.
_SEARCH_BG = QColor("#FFF59D")  # soft yellow, current match
_SEARCH_ALL_BG = QColor("#FFF9C4")  # lighter yellow, other matches


class _LineNumberArea(QWidget):
    """Sidebar painting the visible line numbers."""

    def __init__(self, editor: "EditorPane"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):  # noqa: N802 (Qt naming)
        return self._editor._line_number_area_size()

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        self._editor._line_number_area_paint(event)


class EditorPane(QPlainTextEdit):
    """A real editor: line numbers, find, wrap, drag&drop, mark painting.

    Signals
    -------
    fileDropped(str): a file path was dropped onto the editor. The shell
        owns file I/O (controller.load_file); this widget only forwards.
    """

    fileDropped = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._line_numbers = _LineNumberArea(self)
        self._markings: list[dict] = []
        self._markings_text: str | None = None
        self._wrap = True

        # --- find bar -------------------------------------------------
        self._find_bar = QWidget(self)
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Suchen…")
        self._find_input.setClearButtonEnabled(True)
        self._btn_prev = QToolButton()
        self._btn_prev.setText("▲")
        self._btn_prev.setToolTip("Vorheriger Treffer (Shift+Enter)")
        self._btn_next = QToolButton()
        self._btn_next.setText("▼")
        self._btn_next.setToolTip("Nächster Treffer (Enter)")
        self._btn_close = QToolButton()
        self._btn_close.setText("✕")
        self._btn_close.setToolTip("Schließen (Esc)")
        bar_layout = QHBoxLayout(self._find_bar)
        bar_layout.setContentsMargins(4, 2, 4, 2)
        bar_layout.setSpacing(4)
        bar_layout.addWidget(self._find_input, 1)
        bar_layout.addWidget(self._btn_prev)
        bar_layout.addWidget(self._btn_next)
        bar_layout.addWidget(self._btn_close)
        self._find_bar.hide()

        # --- signals ----------------------------------------------------
        self.textChanged.connect(self._on_text_changed)
        self.blockCountChanged.connect(self._update_line_numbers)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._find_input.textChanged.connect(self._find_all)
        self._find_input.returnPressed.connect(self.find_next)
        self._btn_next.clicked.connect(self.find_next)
        self._btn_prev.clicked.connect(self.find_prev)
        self._btn_close.clicked.connect(self.hide_find_bar)

        # --- defaults ---------------------------------------------------
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(10)
        self.setFont(mono)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth if self._wrap
                             else QPlainTextEdit.NoWrap)
        self.setAcceptDrops(True)

    # ------------------------------------------------------------- layout
    def resizeEvent(self, event):  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._update_line_numbers()
        self._position_find_bar()

    def _position_find_bar(self) -> None:
        w = self._find_bar.sizeHint().width()
        self._find_bar.setGeometry(
            self.width() - w - 12, 8, w, self._find_bar.sizeHint().height()
        )
        self._find_bar.raise_()

    def show_find_bar(self) -> None:
        self._find_bar.show()
        self._position_find_bar()
        self._find_input.setFocus()
        self._find_input.selectAll()

    def hide_find_bar(self) -> None:
        self._find_bar.hide()
        self.setFocus()

    # ------------------------------------------------------- line numbers
    def _line_number_area_size(self) -> QPoint:
        digits = max(2, len(str(max(1, self.blockCount()))))
        metrics = QFontMetrics(self.font())
        return QPoint(metrics.horizontalAdvance("9") * digits + 14, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_numbers.scroll(0, dy)
        else:
            self._line_numbers.update(0, rect.y(), self._line_numbers.width(),
                                      rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_numbers()

    def _update_line_numbers(self) -> None:
        self._line_numbers.setGeometry(
            QRect(self.contentsRect().left(),
                  self.contentsRect().top(),
                  self._line_number_area_size().x(),
                  self.contentsRect().height()))
        self._line_numbers.update()

    def _line_number_area_paint(self, event) -> None:
        painter = QPainter(self._line_numbers)
        painter.fillRect(event.rect(), QColor("#2B2B2B"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(
            self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#7F7F7F") if number != current
                               else QColor("#E0E0E0"))
                painter.drawText(
                    0, top, self._line_numbers.width() - 6,
                    self.fontMetrics().height(), Qt.AlignRight,
                    str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

    # -------------------------------------------------------- edit extras
    def _highlight_current_line(self) -> None:
        self._repaint_markings()

    def _repaint_markings(self) -> None:
        """Combine current-line + substitution + search selections."""
        selections = []

        # current line (subtle)
        line_fmt = QTextCharFormat()
        line_fmt.setBackground(QColor("#333333"))
        cursor = self.textCursor()
        cursor.clearSelection()
        cursor.select(QTextCursor.LineUnderCursor)
        selections.append((cursor, line_fmt))

        # greenlist substitutions
        for m in self._markings:
            fmt = QTextCharFormat()
            fmt.setBackground(_SUB_BG)
            c = QTextCursor(self.document())
            c.setPosition(m["start"])
            c.setPosition(m["end"], QTextCursor.KeepAnchor)
            selections.append((c, fmt))

        # search matches
        search = self._find_input.text()
        if search:
            cur_pos = self.textCursor().position()
            doc = self.document()
            block = doc.begin()
            pos = 0
            while block.isValid():
                text = block.text()
                idx = 0
                while True:
                    idx = text.find(search, idx)
                    if idx < 0:
                        break
                    start = pos + idx
                    end = start + len(search)
                    fmt = QTextCharFormat()
                    fmt.setBackground(_SEARCH_ALL_BG if start != cur_pos
                                      else _SEARCH_BG)
                    c = QTextCursor(doc)
                    c.setPosition(start)
                    c.setPosition(end, QTextCursor.KeepAnchor)
                    selections.append((c, fmt))
                    idx += len(search)
                pos += block.length()
                block = block.next()

        extra = []
        for c, fmt in selections:
            sel = self._selection_from(c, fmt)
            extra.append(sel)
        self.setExtraSelections(extra)

    @staticmethod
    def _selection_from(cursor: QTextCursor, fmt: QTextCharFormat):
        from PySide6.QtWidgets import QTextEdit
        sel = QTextEdit.ExtraSelection()
        sel.cursor = cursor
        sel.format = fmt
        return sel

    # ----------------------------------------------------------- markings
    def set_markings(self, markings: list[dict]) -> None:
        """Paint greenlist substitution ranges (from mark_greenlist).

        Each item: ``{"start": int, "end": int, "original": str,
        "replacement": str}`` — offsets into the CURRENT editor text.
        """
        self._markings = list(markings or [])
        self._markings_text = self.toPlainText() if self._markings else None
        self._repaint_markings()

    def clear_markings(self) -> None:
        self.set_markings([])

    def _on_text_changed(self) -> None:
        """Invalidate greenlist markings when the text they were computed
        against no longer matches — typing, undo, paste, wrap all change
        offsets, and stale highlights would paint the wrong words."""
        if self._markings and self.toPlainText() != self._markings_text:
            self.clear_markings()

    # --------------------------------------------------------------- find
    def find_next(self) -> None:
        search = self._find_input.text()
        if not search:
            return
        if not self.find(search):
            # wrap around
            self.moveCursor(QTextCursor.Start)
            self.find(search)

    def find_prev(self) -> None:
        search = self._find_input.text()
        if not search:
            return
        flags = QTextDocument.FindBackward
        if not self.find(search, flags):
            self.moveCursor(QTextCursor.End)
            self.find(search, flags)

    def _find_all(self) -> None:
        self._repaint_markings()

    # ------------------------------------------------------------ wrap
    def toggle_wrap(self) -> None:
        self.set_wrap(not self._wrap)

    def set_wrap(self, enabled: bool) -> None:
        """Set wrap explicitly (idempotent) — used by the menu action."""
        self._wrap = bool(enabled)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth if self._wrap
                             else QPlainTextEdit.NoWrap)

    @property
    def wrap_enabled(self) -> bool:
        return self._wrap

    # ------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event):  # noqa: N802 (Qt naming)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):  # noqa: N802 (Qt naming)
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            path = url.toLocalFile()
            if path:
                self.fileDropped.emit(path)
                event.acceptProposedAction()
                return
        super().dropEvent(event)



