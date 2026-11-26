"""The errors optdoc reports: a fixed kind, the details its wording needs, and that
wording in English and German.

The kinds every tool of docrepro has (a file missing, a configuration broken, the network
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
        "en": "HEIC and HEIF photos need pillow-heif, which comes with the extra 'cleanup'.",
        "de": "HEIC- und HEIF-Fotos brauchen pillow-heif, das mit dem Extra „cleanup“ kommt.",
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
    "clean-up-failed": {
        "en": "A page could not be cleaned up.",
        "de": "Eine Seite ließ sich nicht aufbereiten.",
    },
}

_core.register(_OWN)
KINDS = _core.KINDS  # every kind optdoc may report, the common ones with its own
__all__ = ["KINDS", "LANGUAGES", "REASONS", "DocError", "OptdocError", "describe_error"]


class OptdocError(DocError):
    """An error optdoc can word for a person: its kind (a key of :data:`KINDS`) and the
    details the wording needs.  ``str(error)`` is the English message."""

    tool = "optdoc"
