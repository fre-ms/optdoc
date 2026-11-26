"""Every word optdoc's window shows, in English and German, registered with the words of
doccor (:mod:`doccor.gui.words`), which give them in the language of the application that
opens the window (``--language``), else that of the system.  A tool's name is a
placeholder (``{tool}``), and a key another tool of docrepro words otherwise has a name of
its own here, so that the words of several tools can live in one program.  Text that
comes from optdoc's core (the description of a preparation, an error) has its own two
languages (:func:`optdoc.cleanup.describe`, :func:`optdoc.errors.describe_error`).
"""

from __future__ import annotations

from doccor.gui import words as _words
from doccor.gui.words import LANGUAGES, Words, system_language

WORDS: dict[str, tuple[str, str]] = {  # key: (English, German)
    "title": ("{tool}: {name}", "{tool}: {name}"),
    "page": ("Page {number}", "Seite {number}"),
    "apply": ("Apply", "Übernehmen"),
    "later": ("Save and continue later", "Speichern und später weitermachen"),
    "cancel": ("Cancel", "Abbrechen"),
    "discard_title": ("Discard the work?", "Arbeit verwerfen?"),
    "discard_text": ("Nothing will be written. Discard what was done in this window?",
                     "Es wird nichts geschrieben. Das in diesem Fenster Getane verwerfen?"),
    "failed": ("That did not work: {error}", "Das ging nicht: {error}"),
    "colour_pages": ("Pages in colour as", "Farbseiten als"),
    "colour_jpeg": ("JPEG (small)", "JPEG (klein)"),
    "colour_png": ("PNG (lossless)", "PNG (verlustfrei)"),
    "colour_pages_tip": ("How the pages that keep their colours are stored in the PDF: JPEG at "
                         "quality 92, or lossless PNG, some ten times the size. Pages without "
                         "colour are always stored losslessly in grey.",
                         "Wie die Seiten, die ihre Farben behalten, im PDF abgelegt werden: JPEG "
                         "in Qualität 92 oder verlustfrei als PNG, etwa zehnmal so groß. Seiten "
                         "ohne Farbe liegen immer verlustfrei in Graustufen."),
    # clean-up
    "before": ("Before (drag the blue corners onto the sheet's corners to unwarp it)",
               "Vorher (die blauen Ecken auf die Ecken des Blatts ziehen, um es zu entzerren)"),
    "after": ("After (as it goes into the PDF; drag erases an area white, Cmd/Ctrl+Z takes it "
              "back; Shift/Option + drag moves both views)",
              "Nachher (so kommt es ins PDF; Ziehen löscht den Bereich weiß, Cmd/Strg+Z holt ihn "
              "zurück; Umschalt/Option + Ziehen verschiebt beide Ansichten)"),
    "steps": ("Steps for this page", "Schritte für diese Seite"),
    "straighten": ("Straighten the tilt", "Schräglage begradigen"),
    "unwarp": ("Unwarp the photographed sheet", "Fotografiertes Blatt entzerren"),
    "background": ("Even out the background (shadows, grey paper)",
                   "Hintergrund glätten (Schatten, graues Papier)"),
    "background_tip": ("Every colour channel is evened out on its own: the paper becomes white, "
                       "ink keeps its colour.",
                       "Jeder Farbkanal wird für sich geglättet: das Papier wird weiß, die Tinte "
                       "behält ihre Farbe."),
    "grey": ("Store in grey (the page has no colour)",
             "In Graustufen ablegen (die Seite hat keine Farbe)"),
    "grey_tip": ("A page without colour is smaller in grey. optdoc suggests it where less than "
                 "0.3 % of the page is coloured; a stamp or a blue signature keeps a page in "
                 "colour.",
                 "Eine Seite ohne Farbe ist in Graustufen kleiner. optdoc schlägt es vor, wo "
                 "weniger als 0,3 % der Seite farbig sind; ein Stempel oder eine blaue "
                 "Unterschrift hält eine Seite in Farbe."),
    "further": ("Further steps", "Weitere Schritte"),
    "borders": ("Clean dark borders", "Dunkle Ränder säubern"),
    "denoise": ("Denoise (grain, dust)", "Entrauschen (Körnung, Staub)"),
    "contrast": ("Raise the contrast (faint copies)", "Kontrast anheben (blasse Kopien)"),
    "sharpen": ("Sharpen", "Schärfen"),
    "strength": ("Strength 1 (gentle) to 5 (strong)", "Stärke 1 (sanft) bis 5 (kräftig)"),
    "orientation": ("Detect the orientation", "Ausrichtung erkennen"),
    "orientation_tip": ("Portrait or landscape from the text lines; whether the text stands on its "
                        "head is decided by a short OCR comparison where ocrdoc is installed "
                        "(takes a few seconds).",
                        "Hoch- oder Querformat aus den Textzeilen; ob der Text auf dem Kopf steht, "
                        "entscheidet ein kurzer Vergleich der Texterkennung, wo ocrdoc installiert "
                        "ist (dauert einige Sekunden)."),
    "rotate": ("Rotate", "Drehen"),
    "undo_mask": ("Take back the last area (Cmd/Ctrl+Z)",
                  "Letzten Bereich zurückholen (Cmd/Strg+Z)"),
    "clear_masks": ("Take back all", "Alle zurückholen"),
    "restore": ("Restore the suggestion", "Vorschlag wiederherstellen"),
    "skip": ("Do not clean up this page", "Diese Seite nicht aufbereiten"),
    "steps_to_all": ("Copy the steps to every page", "Schritte auf alle Seiten übertragen"),
    "no_opencv_cleanup": ("Cleaning up needs OpenCV and NumPy (extra 'cleanup').",
                          "Aufbereiten braucht OpenCV und NumPy (Extra „cleanup“)."),
    "has_layer": ("This page has a text layer of its own (it is born digital); it stays as it is.",
                  "Diese Seite hat eine eigene Textebene (sie ist digital entstanden); sie bleibt, "
                  "wie sie ist."),
    "no_sheet": ("no photographed sheet found; drag the corners in “Before” onto it",
                 "kein fotografiertes Blatt erkannt; in „Vorher“ die Ecken darauf ziehen"),
    "cleanup_failed": ("Clean-up failed: {error}", "Aufbereitung fehlgeschlagen: {error}"),
    "orientation_failed": ("Orientation not found: {error}", "Ausrichtung nicht erkannt: {error}"),
    "zoom_reset": ("1:1", "1:1"),
}

_words.register(WORDS)
__all__ = ["LANGUAGES", "WORDS", "Words", "system_language"]
