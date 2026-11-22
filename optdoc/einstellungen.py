"""Settings of the OCR layer: which engine "auto" means, where Tesseract lives, which
language packs it reads with.

optdoc keeps no configuration file of its own.  An application that embeds it hands
over its settings with :func:`setze_einstellungen` (any object with the three
attributes will do); without that the environment decides:

``OPTDOC_OCR``
    the engine "auto" stands for: ``rapidocr``, ``tesseract`` or ``aus`` (none).
``OPTDOC_TESSERACT``
    the path of the Tesseract program, where it is not found on its own.
``OPTDOC_TESSERACT_LANGUAGES``
    Tesseract's language packs, joined by ``+`` (``deu+eng``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


class EinstellungenArt(Protocol):
    """What the OCR layer reads from a settings object."""

    ocr_backend: str
    tesseract_pfad: str
    tesseract_sprachen: str


@dataclass
class Einstellungen:
    """The settings of the OCR layer; empty strings mean "decide by yourself"."""

    ocr_backend: str = "auto"
    tesseract_pfad: str = ""
    tesseract_sprachen: str = ""


_gesetzt: EinstellungenArt | None = None


def setze_einstellungen(einstellungen: EinstellungenArt | None) -> None:
    """Use these settings from now on (an embedding application's own); None returns to
    the environment."""
    global _gesetzt
    _gesetzt = einstellungen


def lade_einstellungen() -> EinstellungenArt:
    """The settings an application set, else those of the environment."""
    if _gesetzt is not None:
        return _gesetzt
    return Einstellungen(
        ocr_backend=os.environ.get("OPTDOC_OCR", "auto").strip() or "auto",
        tesseract_pfad=os.environ.get("OPTDOC_TESSERACT", "").strip(),
        tesseract_sprachen=os.environ.get("OPTDOC_TESSERACT_LANGUAGES", "").strip(),
    )
