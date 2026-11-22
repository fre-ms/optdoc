"""Shared fixtures: an invented report, and settings taken from the environment only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from optdoc.einstellungen import setze_einstellungen
from tests.synthetisch import erzeuge_befund


@pytest.fixture
def befund(tmp_path: Path) -> Path:
    """The invented two-page report as a PDF with a text layer."""
    return erzeuge_befund(tmp_path / "befund.pdf")


@pytest.fixture(autouse=True)
def _einstellungen_der_umgebung() -> Iterator[None]:
    """No test leaves settings behind for the next one."""
    setze_einstellungen(None)
    yield
    setze_einstellungen(None)
