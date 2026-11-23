"""The errors optdoc reports: a fixed kind, the details its wording needs, and that
wording in English and German.

A document may hold anything, and its file name may name a patient.  So no message
quotes the content or the path of a document, and the details are only what is safe
to show: a file name extension, the name of an engine or a paper size, a page number,
the name of an exception class.  A program that calls optdoc decides by the kind; a
person reads :func:`describe_error` in the language of the interface.
"""

from __future__ import annotations

KINDS: dict[str, dict[str, str]] = {
    "missing": {
        "en": "The file or folder does not exist.",
        "de": "Die Datei oder den Ordner gibt es nicht.",
    },
    "unsupported": {
        "en": "optdoc cannot open files of type {suffix}.",
        "de": "Dateien vom Typ {suffix} kann optdoc nicht öffnen.",
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
    "bad-config": {
        "en": "The configuration cannot be used: {reason}.",
        "de": "Die Konfiguration ist nicht verwendbar: {reason}.",
    },
    "config-mismatch": {
        "en": "The configuration belongs to another file.",
        "de": "Die Konfiguration gehört zu einer anderen Datei.",
    },
    "not-ocr": {
        "en": "Page {page} was not read by OCR; its text cannot be corrected.",
        "de": "Seite {page} wurde nicht per Texterkennung gelesen; ihr Text lässt sich nicht "
              "berichtigen.",
    },
    "cancelled": {
        "en": "The work was cancelled; nothing was written.",
        "de": "Die Arbeit wurde abgebrochen; nichts wurde geschrieben.",
    },
    "no-gui": {
        "en": "The window needs PySide6, which comes with the extra 'gui'.",
        "de": "Das Fenster braucht PySide6, das mit dem Extra „gui“ kommt.",
    },
    "same-as-source": {
        "en": "The results would overwrite the document itself; choose another folder.",
        "de": "Die Ergebnisse würden das Dokument selbst überschreiben; bitte einen anderen "
              "Ordner wählen.",
    },
    "unwritable": {
        "en": "The results cannot be written to the folder given.",
        "de": "Die Ergebnisse lassen sich nicht in den angegebenen Ordner schreiben.",
    },
    "clean-up-failed": {
        "en": "A page could not be cleaned up.",
        "de": "Eine Seite ließ sich nicht aufbereiten.",
    },
    "page-text": {
        "en": "Page text {page}: the character lists do not fit the text.",
        "de": "Seitentext {page}: die Zeichenlisten passen nicht zum Text.",
    },
    "network": {
        "en": "Something tried to reach the network, which optdoc never does; it was stopped "
              "and nothing was sent.",
        "de": "Etwas wollte ins Netz, was optdoc nie tut; es wurde angehalten, nichts wurde "
              "gesendet.",
    },
    "usage": {
        "en": "The command line is not valid; see optdoc --help.",
        "de": "Die Kommandozeile ist nicht gültig; siehe optdoc --help.",
    },
    "internal": {
        "en": "optdoc failed unexpectedly ({error}).",
        "de": "optdoc ist unerwartet gescheitert ({error}).",
    },
}

# the reasons a configuration is refused, worded for "bad-config"
REASONS: dict[str, dict[str, str]] = {
    "json": {"en": "it is no JSON that can be read",
             "de": "sie ist kein lesbares JSON"},
    "format": {"en": "it is no configuration of this version of optdoc",
               "de": "sie ist keine Konfiguration dieser Fassung von optdoc"},
    "page": {"en": "it does not have one entry for each page of the document",
             "de": "sie hat nicht für jede Seite des Dokuments einen Eintrag"},
    "field": {"en": "a value is of the wrong kind",
              "de": "ein Wert ist von der falschen Art"},
}

LANGUAGES = ("en", "de")


class OptdocError(Exception):
    """An error optdoc can word for a person: its kind (a key of :data:`KINDS`) and the
    details the wording needs.  ``str(error)`` is the English message."""

    def __init__(self, kind: str, **details: str | int) -> None:
        if kind not in KINDS:
            raise KeyError(f"unknown kind of error: {kind}")
        self.kind = kind
        self.details = details
        super().__init__(self.message("en"))

    def message(self, language: str = "en") -> str:
        """The message in ``language`` ("en" or "de"; any other means English)."""
        wording = KINDS[self.kind]
        details = dict(self.details)
        if self.kind == "bad-config":
            reason = REASONS.get(str(details.get("reason")), REASONS["json"])
            details["reason"] = reason.get(language, reason["en"])
        return wording.get(language, wording["en"]).format(**details)


class OCRError(OptdocError):
    """An OCR engine is missing, unknown, or failed on a page."""


def describe_error(error: BaseException, language: str = "en") -> str:
    """The message of an error for a person, in English (``"en"``) or German (``"de"``);
    an error that is not optdoc's keeps its own message."""
    if isinstance(error, OptdocError):
        return error.message(language)
    return str(error)
