"""Settings of the OCR layer: which engine "auto" means, where Tesseract lives, which
language packs it reads with.

optdoc keeps no configuration file of its own.  An application that embeds it hands
over its settings with :func:`set_settings` (any object with the three
attributes will do); without that the environment decides:

``OPTDOC_OCR``
    the engine "auto" stands for: ``rapidocr``, ``tesseract`` or ``none``.
``OPTDOC_TESSERACT``
    the path of the Tesseract program, where it is not found on its own.
``OPTDOC_TESSERACT_LANGUAGES``
    Tesseract's language packs, joined by ``+`` (``deu+eng``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


class SettingsLike(Protocol):
    """What the OCR layer reads from a settings object."""

    ocr_backend: str
    tesseract_path: str
    tesseract_languages: str


@dataclass
class Settings:
    """The settings of the OCR layer; empty strings mean "decide by yourself"."""

    ocr_backend: str = "auto"
    tesseract_path: str = ""
    tesseract_languages: str = ""


_current: SettingsLike | None = None


def set_settings(settings: SettingsLike | None) -> None:
    """Use these settings from now on (an embedding application's own); None returns to
    the environment."""
    global _current
    _current = settings


def load_settings() -> SettingsLike:
    """The settings an application set, else those of the environment."""
    if _current is not None:
        return _current
    return Settings(
        ocr_backend=os.environ.get("OPTDOC_OCR", "auto").strip() or "auto",
        tesseract_path=os.environ.get("OPTDOC_TESSERACT", "").strip(),
        tesseract_languages=os.environ.get("OPTDOC_TESSERACT_LANGUAGES", "").strip(),
    )
