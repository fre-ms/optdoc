"""Open the window on a project and wait until it closes (``optdoc edit``)."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from optdoc.gui.window import EditWindow
from optdoc.gui.words import Words
from optdoc.project import Project


def edit(project: Project, language: str | None = None, self_test: bool = False) -> str:
    """Show the window on ``project``, brought to the front (it is opened from another
    program), and return how it closed: "applied", "saved" or "cancelled".  With
    ``self_test`` it goes through once by itself (the check of the standalone program)."""
    app = QApplication.instance() or QApplication(["optdoc"])
    app.setApplicationName("optdoc")
    window = EditWindow(project, Words(language), synchronous=self_test)
    window.show()
    window.raise_()
    window.activateWindow()
    if self_test:
        QTimer.singleShot(0, window.self_test)
    app.exec()
    return window.outcome or "cancelled"
