"""Every word the window shows, in English and German.

The window takes the language of the application that opens it (``--language``), else
that of the system.  Text that comes from optdoc's core (the description of a clean-up,
an error) has its own two languages (:func:`optdoc.cleanup.describe`,
:func:`optdoc.errors.describe_error`).
"""

from __future__ import annotations

import locale
import os

WORDS: dict[str, tuple[str, str]] = {  # key: (English, German)
    "title": ("optdoc: {name}", "optdoc: {name}"),
    "page": ("Page {number}", "Seite {number}"),
    "page_corrected": ("Page {number} ✎", "Seite {number} ✎"),
    "tab_cleanup": ("1 Clean up", "1 Aufbereiten"),
    "tab_text": ("2 Check the text", "2 Text prüfen"),
    "apply": ("Apply", "Übernehmen"),
    "later": ("Save and continue later", "Speichern und später weitermachen"),
    "cancel": ("Cancel", "Abbrechen"),
    "discard_title": ("Discard the work?", "Arbeit verwerfen?"),
    "discard_text": ("Nothing will be written. Discard what was done in this window?",
                     "Es wird nichts geschrieben. Das in diesem Fenster Getane verwerfen?"),
    "reading_page": ("Reading page {number} of {total} …", "Lese Seite {number} von {total} …"),
    "read_all": ("Every page read.", "Alle Seiten gelesen."),
    "failed": ("That did not work: {error}", "Das ging nicht: {error}"),
    # clean-up
    "before": ("Before", "Vorher"),
    "after": ("After (as OCR sees it; drag erases an area white, Cmd/Ctrl+Z takes it back; "
              "Shift/Option + drag moves both views)",
              "Nachher (so sieht es die Texterkennung; Ziehen löscht den Bereich weiß, "
              "Cmd/Strg+Z holt ihn zurück; Umschalt/Option + Ziehen verschiebt beide Ansichten)"),
    "steps": ("Steps for this page", "Schritte für diese Seite"),
    "straighten": ("Straighten the tilt", "Schräglage begradigen"),
    "unwarp": ("Unwarp the photographed sheet", "Fotografiertes Blatt entzerren"),
    "upscale": ("Upscale", "Hochskalieren"),
    "not": ("not", "nicht"),
    "upscale_tip": ("OCR reads the page at that multiple of the resolution (up to 4×, at most "
                    "9000 pixels); the page itself is not stored enlarged.",
                    "Die Texterkennung liest die Seite mit dem Vielfachen der Auflösung (bis 4×, "
                    "höchstens 9000 Pixel); die Seite selbst wird nicht vergrößert gespeichert."),
    "letter_mode": ("Letter mode: Lanczos enlargement, strokes sharpened",
                    "Buchstabenmodus: Lanczos-Vergrößerung, Striche geschärft"),
    "letter_tip": ("Enlarges with Lanczos and sharpens the strokes in grey. A hard black-and-white "
                   "threshold made recognition much worse in measurements, so the image stays "
                   "grey. Replaces background, sharpening and black-and-white.",
                   "Vergrößert mit Lanczos und schärft die Striche in Graustufen. Eine harte "
                   "Schwarz-Weiß-Schwelle verschlechterte die Erkennung in Messungen deutlich, "
                   "deshalb bleibt das Bild grau. Ersetzt Hintergrund, Schärfen und Schwarz-Weiß."),
    "background": ("Even out the background (shadows, grey paper)",
                   "Hintergrund glätten (Schatten, graues Papier)"),
    "black_white": ("Black and white", "Schwarz-Weiß"),
    "further": ("Further steps", "Weitere Schritte"),
    "borders": ("Clean dark borders", "Dunkle Ränder säubern"),
    "remove_colour": ("Remove coloured ink (stamps, highlighter)",
                      "Farbige Tinte entfernen (Stempel, Marker)"),
    "denoise": ("Denoise (grain, dust)", "Entrauschen (Körnung, Staub)"),
    "contrast": ("Raise the contrast (faint copies)", "Kontrast anheben (blasse Kopien)"),
    "sharpen": ("Sharpen", "Schärfen"),
    "remove_lines": ("Remove lines (forms, tables)", "Linien entfernen (Formulare, Tabellen)"),
    "strength": ("Strength 1 (gentle) to 5 (strong)", "Stärke 1 (sanft) bis 5 (kräftig)"),
    "orientation": ("Detect the orientation", "Ausrichtung erkennen"),
    "orientation_tip": ("Portrait or landscape from the text lines; whether the text stands on its "
                        "head is decided by a short OCR comparison (takes a few seconds).",
                        "Hoch- oder Querformat aus den Textzeilen; ob der Text auf dem Kopf steht, "
                        "entscheidet ein kurzer Vergleich der Texterkennung (dauert einige "
                        "Sekunden)."),
    "rotate": ("Rotate", "Drehen"),
    "undo_mask": ("Take back the last area (Cmd/Ctrl+Z)",
                  "Letzten Bereich zurückholen (Cmd/Strg+Z)"),
    "clear_masks": ("Take back all", "Alle zurückholen"),
    "restore": ("Restore the suggestion", "Vorschlag wiederherstellen"),
    "skip": ("Do not clean up this page", "Diese Seite nicht aufbereiten"),
    "to_all": ("Copy the steps to every page", "Schritte auf alle Seiten übertragen"),
    "no_opencv": ("Cleaning up needs OpenCV and NumPy (extra 'ocr').",
                  "Aufbereiten braucht OpenCV und NumPy (Extra „ocr“)."),
    "has_layer": ("This page has a text layer of its own; it is read as it is, not cleaned up.",
                  "Diese Seite hat eine eigene Textebene; sie wird gelesen, wie sie ist, nicht "
                  "aufbereitet."),
    "no_sheet": ("no photographed sheet found", "kein fotografiertes Blatt erkannt"),
    "orientation_failed": ("Orientation not found: {error}", "Ausrichtung nicht erkannt: {error}"),
    "cleanup_failed": ("Clean-up failed: {error}", "Aufbereitung fehlgeschlagen: {error}"),
    # text
    "page_image": ("The page as OCR read it (click a word to find it in the text; yellow: "
                   "read with little confidence)",
                   "Die Seite, wie die Texterkennung sie gelesen hat (Klick auf ein Wort findet "
                   "es im Text; gelb: unsicher gelesen)"),
    "text_ocr": ("Recognised text, to be corrected by hand. A gap between table cells is a tab; "
                 "the correction goes into the PDF's text layer, the reading and the Markdown.",
                 "Erkannter Text, von Hand zu berichtigen. Eine Lücke zwischen Tabellenzellen ist "
                 "ein Tabulator; die Berichtigung kommt in die Textebene des PDFs, die Lesung "
                 "und das Markdown."),
    "text_layer": ("Text of the text layer (cannot be changed)",
                   "Text der Textebene (nicht veränderbar)"),
    "text_none": ("No text on this page.", "Kein Text auf dieser Seite."),
    "reset_text": ("Back to the OCR text", "Auf den erkannten Text zurücksetzen"),
    "corrected": ("corrected", "berichtigt"),
    "as_read": ("as read", "wie gelesen"),
    "uncertain": ("{n} word(s) read with little confidence", "{n} Wort/Wörter unsicher gelesen"),
    "zoom_reset": ("1:1", "1:1"),
}

LANGUAGES = ("en", "de")


def system_language() -> str:
    """The language of the system: German where it is set so, else English."""
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if value and value not in ("C", "POSIX"):
            return "de" if value.lower().startswith("de") else "en"
    current = locale.getlocale()[0] or ""
    return "de" if current.lower().startswith("de") else "en"


class Words:
    """The words of one language: ``words("page", number=2)``."""

    def __init__(self, language: str | None = None) -> None:
        self.language = language if language in LANGUAGES else system_language()

    def __call__(self, key: str, **values: object) -> str:
        """The word ``key`` in this language, its placeholders filled in."""
        english, german = WORDS[key]
        return (german if self.language == "de" else english).format(**values)
