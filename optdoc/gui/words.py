"""Every word optdoc's window shows, in English and German, registered with the words of
doccor (:mod:`doccor.gui.words`), which give them in the language of the application that
opens the window (``--language``), else that of the system.  Text that comes from optdoc's
core (the description of a clean-up, an error) has its own two languages
(:func:`optdoc.cleanup.describe`, :func:`optdoc.errors.describe_error`).
"""

from __future__ import annotations

from doccor.gui import words as _words
from doccor.gui.words import LANGUAGES, Words, system_language

WORDS: dict[str, tuple[str, str]] = {  # key: (English, German)
    "title": ("optdoc: {name}", "optdoc: {name}"),
    "page": ("Page {number}", "Seite {number}"),
    "page_corrected": ("Page {number} ✎", "Seite {number} ✎"),
    "tab_cleanup": ("1 Clean up", "1 Aufbereiten"),
    "tab_regions": ("2 Areas", "2 Bereiche"),
    "tab_text": ("3 Check the text", "3 Text prüfen"),
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
    "before": ("Before (drag the blue corners onto the sheet's corners to unwarp it)",
               "Vorher (die blauen Ecken auf die Ecken des Blatts ziehen, um es zu entzerren)"),
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
    "no_sheet": ("no photographed sheet found; drag the corners in “Before” onto it",
                 "kein fotografiertes Blatt erkannt; in „Vorher“ die Ecken darauf ziehen"),
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
    # areas
    "kind_text": ("Text", "Text"),
    "kind_table": ("Table", "Tabelle"),
    "kind_image": ("Picture", "Bild"),
    "kind_barcode": ("Barcode", "Barcode"),
    "kind_handwriting": ("Handwriting", "Handschrift"),
    "kind_stamp": ("Stamp", "Stempel"),
    "kind_ignore": ("Do not read", "Nicht lesen"),
    "kind": ("Kind of the area selected", "Art des ausgewählten Bereichs"),
    "kind_tip": ("Gives the area selected another kind",
                 "Gibt dem ausgewählten Bereich eine andere Art"),
    "tools": ("Tools", "Werkzeuge"),
    "tool_select": ("Select, move, resize; drag a table's lines",
                    "Auswählen, verschieben, Größe ändern; Tabellenlinien ziehen"),
    "tool_draw": ("Draw an area", "Bereich zeichnen"),
    "tool_column": ("Add a column line (click in the table)",
                    "Spaltenlinie einfügen (in die Tabelle klicken)"),
    "tool_row": ("Add a row line (click in the table)",
                 "Zeilenlinie einfügen (in die Tabelle klicken)"),
    "tool_remove": ("Remove a line (click on it)", "Linie entfernen (darauf klicken)"),
    "tool_merge": ("Merge cells (drag over them) or split them (click)",
                   "Zellen verbinden (darüber ziehen) oder trennen (klicken)"),
    "delete_region": ("Delete the area", "Bereich löschen"),
    "find_again": ("Find the areas again", "Bereiche neu erkennen"),
    "regions_help": ("What is in no area is read as text. Pictures, barcodes and areas not to "
                     "be read stay out of the text; handwriting and stamps are read and marked. "
                     "The numbers are the order of reading. Delete or Backspace deletes the area "
                     "selected, Escape goes back to selecting.",
                     "Was in keinem Bereich liegt, wird als Text gelesen. Bilder, Barcodes und "
                     "Bereiche, die nicht gelesen werden sollen, bleiben aus dem Text; "
                     "Handschrift und Stempel werden gelesen und markiert. Die Nummern sind die "
                     "Lesereihenfolge. Entf oder Rückschritt löscht den ausgewählten Bereich, "
                     "Escape kehrt zum Auswählen zurück."),
    "regions_auto": ("Areas found by optdoc: {count}", "Von optdoc erkannte Bereiche: {count}"),
    "regions_person": ("Areas set by hand: {count}", "Von Hand gesetzte Bereiche: {count}"),
    "regions_table": ("Table selected: {rows} rows, {columns} columns",
                      "Ausgewählte Tabelle: {rows} Zeilen, {columns} Spalten"),
    "regions_barcode": ("Barcode selected ({format}): {content}",
                        "Ausgewählter Barcode ({format}): {content}"),
    "regions_no_tables": ("Tables are not found automatically here (extra 'tables' or "
                          "--no-cells); they can be drawn.",
                          "Tabellen werden hier nicht automatisch erkannt (Extra „tables“ oder "
                          "--no-cells); sie lassen sich zeichnen."),
    "finding_regions": ("Finding the areas of page {number} …",
                        "Erkenne die Bereiche auf Seite {number} …"),
}

_words.register(WORDS)
__all__ = ["LANGUAGES", "WORDS", "Words", "system_language"]
