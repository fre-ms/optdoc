"""The window of ``optdoc edit``: the pages on the left, clean-up, areas and text as
three tabs, in FineReader's order, and three ways out.

- **Apply** reads every page not read yet (with progress) and closes; the command line
  then writes the result, exactly as ``prepare`` would from the same configuration.
- **Save and continue later** closes; the command line writes the configuration, from
  which ``edit --config`` goes on.
- **Cancel** (or closing the window) closes; nothing is written.

One piece of work runs at a time, off the window's thread; while it runs, the clean-up
cannot change the page under it.
"""

from __future__ import annotations

from collections.abc import Callable

from doccor.gui.worker import Worker
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from optdoc.errors import describe_error
from optdoc.gui.cleanup_panel import CleanupPanel
from optdoc.gui.regions_panel import RegionsPanel
from optdoc.gui.text_panel import TextPanel
from optdoc.gui.words import Words
from optdoc.project import Project


class EditWindow(QMainWindow):
    """The window on one project.  ``outcome`` is "applied", "saved" or "cancelled" once
    it closes.  ``synchronous`` runs every piece of work at once on the window's thread
    and asks nothing (the tests, the self-test)."""

    progressed = Signal(int, int)

    def __init__(self, project: Project, words: Words, synchronous: bool = False) -> None:
        super().__init__()
        self.project = project
        self.w = words
        self.synchronous = synchronous
        self.outcome: str | None = None
        self.changed = False
        self._worker: Worker | None = None
        self._pending: tuple[Callable[[], object], Callable[[], None]] | None = None
        self.setWindowTitle(self.w("title", name=project.source.name))
        self.resize(1280, 820)
        self.cleanup = CleanupPanel(project, words)
        self.cleanup.changed.connect(self._plan_changed)
        self.areas = RegionsPanel(project, words, self._find_regions)
        self.areas.changed.connect(self._plan_changed)
        self.text = TextPanel(project, words, self._read_page)
        central = QWidget()
        v = QVBoxLayout(central)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.pages = QListWidget()
        self.pages.setMaximumWidth(160)
        splitter.addWidget(self.pages)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.cleanup, self.w("tab_cleanup"))
        self.tabs.addTab(self.areas, self.w("tab_regions"))
        self.tabs.addTab(self.text, self.w("tab_text"))
        splitter.addWidget(self.tabs)
        splitter.setSizes([140, 1140])
        v.addWidget(splitter, 1)
        v.addLayout(self._build_bar())
        self.setCentralWidget(central)
        self._fill_pages()
        self.pages.setCurrentRow(0)  # before the signal is connected: shown just below
        self.pages.currentRowChanged.connect(self._show)
        self.tabs.currentChanged.connect(lambda _i: self._show(self.pages.currentRow()))
        self.progressed.connect(self._progress)
        if not any(project.cleanable(n) for n in range(len(project.pages))):
            self.tabs.setCurrentWidget(self.text)  # a born-digital PDF: nothing to clean up
        self._show(0)  # the row is 0 already, so no signal shows it

    def _build_bar(self) -> QHBoxLayout:
        """Status, progress and the three ways out."""
        bar = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        bar.addWidget(self.status, 1)
        bar.addWidget(self.progress)
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

    # -- pages ---------------------------------------------------------------------------------
    def _fill_pages(self) -> None:
        """One entry per page."""
        for n in range(len(self.project.pages)):
            self.pages.addItem(self.w("page", number=n + 1))
        self._mark_pages()

    def _show(self, n: int) -> None:
        """Show page ``n`` in the tab that is open (what was typed on the page before is
        kept first)."""
        if n < 0:
            return
        self.text.commit()
        self._mark_pages()
        if self.tabs.currentWidget() is self.text:
            self.text.show_page(n)
        elif self.tabs.currentWidget() is self.areas:
            self.areas.show_page(n)
        else:
            self.cleanup.show_page(n)

    def _mark_pages(self) -> None:
        """Mark the pages whose text was corrected."""
        for n, page in enumerate(self.project.pages):
            key = "page_corrected" if page.correction is not None else "page"
            item = self.pages.item(n)
            if item is not None:
                item.setText(self.w(key, number=n + 1))

    def _plan_changed(self, _n: int) -> None:
        """A plan or the areas of a page changed."""
        self.changed = True

    # -- work off the window's thread ----------------------------------------------------------
    def _run(self, job: Callable[[], object], then: Callable[[], None]) -> None:
        """Do ``job``, then ``then``; one at a time, the latest request waits."""
        if self._worker is not None:
            self._pending = (job, then)
            return
        self.cleanup.setEnabled(False)
        self.areas.setEnabled(False)
        for button in (self.later_button, self.apply_button):
            button.setEnabled(False)
        self._worker = Worker(job, self, inline=self.synchronous)
        self._worker.done.connect(lambda _r: self._finished(then))
        self._worker.failed.connect(self._failed)
        self._worker.go()

    def _finished(self, then: Callable[[], None]) -> None:
        """A job is done: free the window, go on with what waited, then ``then``."""
        self._release()
        then()

    def _failed(self, error: Exception) -> None:
        """A job failed: say so in the status line; the window stays open."""
        self._release()
        self.progress.hide()
        self.status.setText(self.w("failed", error=describe_error(error, self.w.language)))
        if self.synchronous:
            raise error

    def _release(self) -> None:
        """Nothing runs any more; start what waited."""
        self._worker = None
        self.cleanup.setEnabled(True)
        self.areas.setEnabled(True)
        for button in (self.later_button, self.apply_button):
            button.setEnabled(True)
        if self._pending is not None:
            job, then = self._pending
            self._pending = None
            self._run(job, then)

    def _read_page(self, n: int, then: Callable[[], None]) -> None:
        """Read page ``n`` (for the text panel), then call back."""
        self.status.setText(self.w("reading_page", number=n + 1, total=len(self.project.pages)))

        def done() -> None:
            self.status.setText("")
            then()

        self._run(lambda: self.project.read(n), done)

    def _find_regions(self, n: int, then: Callable[[], None]) -> None:
        """Read page ``n`` and find its areas (for the areas panel), then call back."""
        self.status.setText(self.w("finding_regions", number=n + 1))

        def done() -> None:
            self.status.setText("")
            then()

        self._run(lambda: self.project.regions(n), done)

    def _progress(self, n: int, total: int) -> None:
        """Progress of reading every page."""
        self.progress.setRange(0, total)
        self.progress.setValue(n - 1)
        self.progress.show()
        self.status.setText(self.w("reading_page", number=n, total=total))

    # -- the ways out --------------------------------------------------------------------------
    def apply(self) -> None:
        """Read what is not read yet, then close with "applied"."""
        self.text.commit()
        self._run(lambda: self.project.read_all(self.progressed.emit), self._applied)

    def _applied(self) -> None:
        self.progress.hide()
        self.status.setText(self.w("read_all"))
        self.outcome = "applied"
        self.close()

    def later(self) -> None:
        """Close with "saved": the configuration is to be written."""
        self.text.commit()
        self.outcome = "saved"
        self.close()

    def cancel(self) -> None:
        """Close with "cancelled": nothing is written."""
        self.outcome = "cancelled"
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Closing the window without a choice cancels; after changes, ask first."""
        if self.outcome is None:
            self.text.commit()
            worked = self.changed or bool(self.project.corrected)
            if worked and not self.synchronous and QMessageBox.question(
                    self, self.w("discard_title"), self.w("discard_text")) \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.outcome = "cancelled"
        if self._worker is not None:
            self._worker.wait()
        event.accept()

    # -- the self-test of the standalone program ------------------------------------------------
    def self_test(self) -> None:
        """Go through the window once without a person: show the clean-up of the first
        page, its areas, turn to its text, and apply."""
        self.tabs.setCurrentWidget(self.cleanup)
        self.cleanup.show_page(0)
        self.tabs.setCurrentWidget(self.areas)
        self.tabs.setCurrentWidget(self.text)
        self.text.commit()
        self.apply()
