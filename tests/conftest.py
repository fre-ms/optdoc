"""Shared fixtures: an invented report."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.synthetic import make_report


def pytest_configure(config: pytest.Config) -> None:
    """The window's tests draw without a screen."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def report(tmp_path: Path) -> Path:
    """The invented two-page report as a PDF with a text layer."""
    return make_report(tmp_path / "befund.pdf")
