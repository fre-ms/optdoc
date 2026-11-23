"""Work that takes a while (OCR, building the result) off the window's thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal


class Worker(QThread):
    """Runs ``job`` in a thread of its own; ``done`` brings its result, ``failed`` its
    exception.  With ``inline`` (the tests), the job runs at once on the caller's thread
    and the signals come before :meth:`go` returns."""

    done = Signal(object)
    failed = Signal(object)

    def __init__(self, job: Callable[[], Any], parent: QObject | None = None,
                 inline: bool = False) -> None:
        super().__init__(parent)
        self._job = job
        self._inline = inline

    def go(self) -> None:
        """Start the job."""
        if self._inline:
            self.run()
        else:
            self.start()

    def run(self) -> None:
        """Do the job and report."""
        try:
            result = self._job()
        except Exception as e:  # reported to the window, which says what went wrong
            self.failed.emit(e)
            return
        self.done.emit(result)
