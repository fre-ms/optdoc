"""Shared fixtures: an invented report, and settings taken from the environment only."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from optdoc.settings import set_settings
from tests.synthetic import make_report


def pytest_configure(config: pytest.Config) -> None:
    """The window's tests draw without a screen."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def report(tmp_path: Path) -> Path:
    """The invented two-page report as a PDF with a text layer."""
    return make_report(tmp_path / "befund.pdf")


@pytest.fixture(autouse=True)
def _settings_from_environment() -> Iterator[None]:
    """No test leaves settings behind for the next one."""
    set_settings(None)
    yield
    set_settings(None)
