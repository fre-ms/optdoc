"""The window of ``optdoc edit``: the pages on the left, the preparation of the page shown
before and after, and three ways out.

- **Apply** closes; the command line then writes the result, exactly as ``run`` would
  from the same configuration.
- **Save and continue later** closes; the command line writes the configuration, from
  which ``edit --config`` goes on.
- **Cancel** (or closing the window) closes; nothing is written.

Reading the pages and their areas is ocrdoc's window, which takes optdoc's PDF.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from optdoc import cleanup
from optdoc.gui.cleanup_panel import CleanupPanel
from optdoc.gui.words import Words
from optdoc.project import Project


class EditWindow(QMainWindow):
    """The window on one project.  ``outcome`` is "applied", "saved" or "cancelled" once
    it closes.  ``synchronous`` asks nothing (the tests, the self-test)."""

    def __init__(self, project: Project, words: Words, synchronous: bool = False) -> None:
        super().__init__()
        self.project = project
        self.w = words
        self.synchronous = synchronous
        self.outcome: str | None = None
        self.changed = False
        self.setWindowTitle(self.w("title", tool="optdoc", name=project.source.name))
        self.resize(1280, 820)
        self.cleanup = CleanupPanel(project, words)
        self.cleanup.changed.connect(self._plan_changed)
        central = QWidget()
        v = QVBoxLayout(central)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.pages = QListWidget()
        self.pages.setMaximumWidth(160)
        splitter.addWidget(self.pages)
        splitter.addWidget(self.cleanup)
        splitter.setSizes([140, 1140])
        v.addWidget(splitter, 1)
        v.addLayout(self._build_bar())
        self.setCentralWidget(central)
        for n in range(len(project.pages)):
            self.pages.addItem(self.w("page", number=n + 1))
        self.pages.setCurrentRow(0)  # before the signal is connected: shown just below
        self.pages.currentRowChanged.connect(self._show)
        self._show(0)  # the row is 0 already, so no signal shows it

    def _build_bar(self) -> QHBoxLayout:
        """Status, how pages in colour are stored (for the whole document), and the three
        ways out."""
        bar = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        bar.addWidget(self.status, 1)
        bar.addWidget(QLabel(self.w("colour_pages")))
        self.colour_pages = QComboBox()
        for name in cleanup.COLOUR_PAGES:
            self.colour_pages.addItem(self.w(f"colour_{name}"), name)
        self.colour_pages.setToolTip(self.w("colour_pages_tip"))
        self.colour_pages.setCurrentIndex(
            max(0, self.colour_pages.findData(self.project.options.colour_pages)))
        self.colour_pages.currentIndexChanged.connect(self._colour_pages)
        bar.addWidget(self.colour_pages)
        self.cancel_button = QPushButton(self.w("cancel"))
        self.cancel_button.clicked.connect(self.cancel)
        self.later_button = QPushButton(self.w("later"))
        self.later_button.clicked.connect(self.later)
        self.apply_button = QPushButton(self.w("apply"))
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.apply)
        for button in (self.cancel_button, self.later_button, self.apply_button):
            button.setMinimumHeight(32)
            bar.addWidget(button)
        return bar

    def _show(self, n: int) -> None:
        """Show page ``n``."""
        if n >= 0:
            self.cleanup.show_page(n)

    def _plan_changed(self, _n: int) -> None:
        """A plan changed."""
        self.changed = True

    def _colour_pages(self, _index: int) -> None:
        """How pages in colour are stored, for the whole document."""
        self.project.options.colour_pages = str(self.colour_pages.currentData())
        self.changed = True

    # -- the ways out --------------------------------------------------------------------------
    def apply(self) -> None:
        """Close with "applied": the result is to be written."""
        self.outcome = "applied"
        self.close()

    def later(self) -> None:
        """Close with "saved": the configuration is to be written."""
        self.outcome = "saved"
        self.close()

    def cancel(self) -> None:
        """Close with "cancelled": nothing is written."""
        self.outcome = "cancelled"
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Closing the window without a choice cancels; after changes, ask first."""
        if self.outcome is None:
            if self.changed and not self.synchronous and QMessageBox.question(
                    self, self.w("discard_title"), self.w("discard_text")) \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.outcome = "cancelled"
        event.accept()

    # -- the self-test of a standalone program --------------------------------------------------
    def self_test(self) -> None:
        """Go through the window once without a person: show every page, and apply."""
        for n in range(len(self.project.pages)):
            self.pages.setCurrentRow(n)
        self.apply()
