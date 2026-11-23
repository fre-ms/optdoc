"""The window of optdoc: clean up a document by eye and correct the recognised text
(``optdoc edit``).  Needs PySide6 (the extra "gui").  The panels are widgets of their own,
so that an application can put them into its own window."""

from __future__ import annotations

import importlib.util


def available() -> bool:
    """True when PySide6 is installed; it is not loaded for that."""
    return importlib.util.find_spec("PySide6") is not None
