"""The window of optdoc: prepare a document by eye (``optdoc edit``).  Needs PySide6 (the
extra "gui").  The panel is a widget of its own, so that an application can put it into
its own window."""

from __future__ import annotations

import importlib.util


def available() -> bool:
    """True when PySide6 is installed; it is not loaded for that."""
    return importlib.util.find_spec("PySide6") is not None
