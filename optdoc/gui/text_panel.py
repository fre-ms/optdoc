"""The recognised text of one page next to the page, to be corrected by hand.

From PseudonyMed's step "Texterkennung".  Words read with little confidence are marked
yellow on the page (a unit like "U/l" read as "U/I" is the kind of thing to look for);
a click on a word in the page selects it in the text.  The correction goes into the
project when the page is left, the window is applied or saved, or :meth:`commit` is
called (:meth:`Project.set_correction`).
"""

from __future__ import annotations

from collections.abc import Callable

from doccor.gui.view import PREVIEW_DPI, YELLOW, PageView
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from optdoc import ocr as ocrlib
from optdoc.gui.words import Words
from optdoc.project import Project


class TextPanel(QWidget):
    """The text of the page :meth:`show_page` names.  Reading a page that is not read yet
    is the window's (it may take seconds); the panel asks through ``read_page``."""

    def __init__(self, project: Project, words: Words,
                 read_page: Callable[[int, Callable[[], None]], None],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.w = words
        self.read_page = read_page  # read page n, then call back
        self.number: int | None = None
        self._shown: str | None = None  # the text put into the editor last
        outer = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        title = QLabel(self.w("page_image"))
        title.setWordWrap(True)
        lv.addWidget(title)
        self.view = PageView()
        self.view.point_selected.connect(self.select_word_at)
        lv.addWidget(self.view, 1)
        splitter.addWidget(left)
        splitter.addWidget(self._build_text())
        splitter.setSizes([600, 540])
        outer.addWidget(splitter)

    def _build_text(self) -> QWidget:
        """The editor with its title, the reset button and the note."""
        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("")
        self.title.setWordWrap(True)
        r.addWidget(self.title)
        self.text = QPlainTextEdit()
        self.text.setTabStopDistance(32)
        r.addWidget(self.text, 1)
        line = QHBoxLayout()
        self.reset = QPushButton(self.w("reset_text"))
        self.reset.clicked.connect(self.reset_text)
        self.note = QLabel("")
        line.addWidget(self.reset)
        line.addWidget(self.note, 1)
        r.addLayout(line)
        return right

    # -- the page ------------------------------------------------------------------------------
    def show_page(self, number: int) -> None:
        """Show page ``number``, reading it first where needed."""
        self.commit()
        self.number = number
        self._shown = None
        if self.project.needs_reading(number):
            self.view.show_empty()
            self.text.setPlainText("")
            self.text.setReadOnly(True)
            self.read_page(number, lambda: self._draw() if self.number == number else None)
            return
        self._draw()

    def _draw(self) -> None:
        """The page as OCR read it with its uncertain words, and its text."""
        n = self.number
        if n is None:
            return
        self.view.scale_factor = PREVIEW_DPI / 72.0
        ocr = self.project.ocr_text(n)
        uncertain = [] if ocr is None else _uncertain(ocr)
        self.view.display(self.project.page_png(n, PREVIEW_DPI),
                          [(box, YELLOW, text) for box, text in uncertain])
        text = self.project.text(n)
        self.text.setPlainText(text)
        self._shown = text
        editable = ocr is not None
        self.text.setReadOnly(not editable)
        self.reset.setEnabled(editable)
        if not editable:
            self.title.setText(self.w("text_layer") if text.strip() else self.w("text_none"))
            self.note.setText("")
            return
        self.title.setText(self.w("text_ocr"))
        self._note(len(uncertain))

    def _note(self, uncertain: int) -> None:
        """Corrected or as read, and how many words are uncertain."""
        n = self.number
        parts = [self.w("corrected") if n is not None and self.project.pages[n].correction
                 is not None else self.w("as_read")]
        if uncertain:
            parts.append(self.w("uncertain", n=uncertain))
        self.note.setText(" · ".join(parts))

    # -- the correction ------------------------------------------------------------------------
    def commit(self) -> None:
        """Take what was typed into the project as the correction of the page."""
        n = self.number
        if n is None or self._shown is None or self.text.isReadOnly():
            return
        text = self.text.toPlainText()
        if text != self._shown:
            self.project.set_correction(n, text)
            self._shown = text
            ocr = self.project.ocr_text(n)
            self._note(len(_uncertain(ocr)) if ocr is not None else 0)

    def reset_text(self) -> None:
        """Back to the text as OCR read it."""
        n = self.number
        ocr = self.project.ocr_text(n) if n is not None else None
        if n is None or ocr is None:
            return
        self.project.set_correction(n, ocr.text)
        self._draw()

    def select_word_at(self, x: float, y: float) -> None:
        """Select in the text the word printed at ``x``, ``y`` (page points), where the text
        is still as read (a corrected text no longer lines up with the page)."""
        n = self.number
        ocr = self.project.ocr_text(n) if n is not None else None
        if ocr is None or self.text.toPlainText() != ocr.text:
            return
        for a, b in ocr.words():
            for r in ocr.rects(a, b):
                if r.x0 - 1 <= x <= r.x1 + 1 and r.y0 - 1 <= y <= r.y1 + 1:
                    cursor = self.text.textCursor()
                    cursor.setPosition(a)
                    cursor.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                    self.text.setTextCursor(cursor)
                    self.text.setFocus()
                    return


def _uncertain(ocr) -> list[tuple[tuple[float, float, float, float], str]]:
    """The boxes and texts of the words OCR read with little confidence."""
    found: list[tuple[tuple[float, float, float, float], str]] = []
    spans = ocr.words()
    if len(ocr.confidences) != len(spans):
        return found
    for (a, b), confidence in zip(spans, ocr.confidences, strict=True):
        if confidence < ocrlib.UNCERTAIN_CONFIDENCE:
            for r in ocr.rects(a, b):
                found.append(((r.x0, r.y0, r.x1, r.y1), f"{ocr.text[a:b]} ({confidence:.2f})"))
    return found
