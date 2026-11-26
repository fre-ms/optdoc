"""The errors optdoc reports: a fixed kind, the details its wording needs, and that
wording in English and German.

The kinds every tool of reprodoc has (a file missing, a configuration broken, the network
refused …) and the mechanism are doccor's (:mod:`doccor.errors`); optdoc's own kinds are
registered there.  A document may hold anything, and its file name may name a patient: no
message quotes the content or the path of a document.  A program that calls optdoc decides
by the kind; a person reads :func:`describe_error` in the language of the interface.
"""

from __future__ import annotations

from doccor import errors as _core
from doccor.errors import LANGUAGES, REASONS, DocError, describe_error

_OWN: dict[str, dict[str, str]] = {
    "unsupported": {
        "en": "{tool} cannot open files of type {suffix}.",
        "de": "Dateien vom Typ {suffix} kann {tool} nicht öffnen.",
    },
    "no-heic": {
        "en": "HEIC and HEIF photos need pillow-heif, which comes with the extra 'ocr'.",
        "de": "HEIC- und HEIF-Fotos brauchen pillow-heif, das mit dem Extra „ocr“ kommt.",
    },
    "unreadable": {
        "en": "The file cannot be read; it may be damaged or not what its name says.",
        "de": "Die Datei lässt sich nicht lesen; sie ist vielleicht beschädigt oder nicht, "
              "was ihr Name sagt.",
    },
    "encrypted": {
        "en": "The PDF is protected by a password.",
        "de": "Das PDF ist mit einem Kennwort geschützt.",
    },
    "paper": {
        "en": "Unknown paper size: {name} (a4, a5, a3, letter, legal, image).",
        "de": "Unbekanntes Papierformat: {name} (a4, a5, a3, letter, legal, image).",
    },
    "unknown-reader": {
        "en": "Unknown OCR engine: {name} (auto, rapidocr, tesseract, none).",
        "de": "Unbekannte Texterkennung: {name} (auto, rapidocr, tesseract, none).",
    },
    "no-reader": {
        "en": "The OCR engine {reader} is not installed.",
        "de": "Die Texterkennung {reader} ist nicht installiert.",
    },
    "reader-failed": {
        "en": "The OCR engine {reader} failed on a page.",
        "de": "Die Texterkennung {reader} ist an einer Seite gescheitert.",
    },
    "not-ocr": {
        "en": "Page {page} was not read by OCR; its text cannot be corrected.",
        "de": "Seite {page} wurde nicht per Texterkennung gelesen; ihr Text lässt sich nicht "
              "berichtigen.",
    },
    "clean-up-failed": {
        "en": "A page could not be cleaned up.",
        "de": "Eine Seite ließ sich nicht aufbereiten.",
    },
    "page-text": {
        "en": "Page text {page}: the character lists do not fit the text.",
        "de": "Seitentext {page}: die Zeichenlisten passen nicht zum Text.",
    },
}

_core.register(_OWN)
KINDS = _core.KINDS  # every kind optdoc may report, the common ones with its own
__all__ = ["KINDS", "LANGUAGES", "REASONS", "DocError", "OCRError", "OptdocError",
           "describe_error"]


class OptdocError(DocError):
    """An error optdoc can word for a person: its kind (a key of :data:`KINDS`) and the
    details the wording needs.  ``str(error)`` is the English message."""

    tool = "optdoc"


class OCRError(OptdocError):
    """An OCR engine is missing, unknown, or failed on a page."""
