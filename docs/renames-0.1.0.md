# Renames in optdoc 0.1.0

optdoc 0.0.1 kept the German identifiers it brought from PseudonyMed. 0.1.0 renames them to English; nothing
else changed in behaviour. This table is for code that used 0.0.1 (in practice: PseudonyMed's switch-over).

## Modules

| 0.0.1 | 0.1.0 |
|---|---|
| `optdoc.laden` | `optdoc.loading` |
| `optdoc.aufbereitung` | `optdoc.cleanup` |
| `optdoc.textebene` | `optdoc.pagetext` |
| `optdoc.gliederung` | `optdoc.structure` |
| `optdoc.textabgleich` | `optdoc.alignment` |
| `optdoc.einstellungen` | `optdoc.settings` |
| `optdoc.lesen` | `optdoc.reading` |
| `optdoc.ausgabe` | `optdoc.output` |

## `optdoc.loading` (was `optdoc.laden`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `BILDENDUNGEN` | `IMAGE_SUFFIXES` | constant |
| `HEIC_ENDUNGEN` | `HEIC_SUFFIXES` | constant |
| `PAPIERFORMATE` | `PAPER_SIZES` | constant |
| `papierformat` | `paper_size` | function |
| `oeffne` | `open_document` | function |
| `oeffne(pfad=)` | `open_document(path=)` | parameter |
| `oeffne(papier=)` | `open_document(paper=)` | parameter |

## `optdoc.cleanup` (was `optdoc.aufbereitung`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `Ecke` | `Corner` | constant |
| `Rechteck` | `Rectangle` | constant |
| `verfuegbar` | `available` | function |
| `Aufbereitung` | `CleanupPlan` | class |
| `Aufbereitung.drehung` | `CleanupPlan.rotation` | field |
| `Aufbereitung.begradigen` | `CleanupPlan.straighten` | field |
| `Aufbereitung.winkel` | `CleanupPlan.angle` | field |
| `Aufbereitung.entzerren` | `CleanupPlan.unwarp` | field |
| `Aufbereitung.ecken` | `CleanupPlan.corners` | field |
| `Aufbereitung.hochskalieren` | `CleanupPlan.upscale` | field |
| `Aufbereitung.textmodus` | `CleanupPlan.letter_mode` | field |
| `Aufbereitung.raender` | `CleanupPlan.borders` | field |
| `Aufbereitung.farbe_entfernen` | `CleanupPlan.remove_colour` | field |
| `Aufbereitung.entrauschen` | `CleanupPlan.denoise` | field |
| `Aufbereitung.entrauschen_staerke` | `CleanupPlan.denoise_strength` | field |
| `Aufbereitung.kontrast` | `CleanupPlan.contrast` | field |
| `Aufbereitung.kontrast_staerke` | `CleanupPlan.contrast_strength` | field |
| `Aufbereitung.schaerfen` | `CleanupPlan.sharpen` | field |
| `Aufbereitung.schaerfen_staerke` | `CleanupPlan.sharpen_strength` | field |
| `Aufbereitung.hintergrund` | `CleanupPlan.background` | field |
| `Aufbereitung.linien_entfernen` | `CleanupPlan.remove_lines` | field |
| `Aufbereitung.schwarzweiss` | `CleanupPlan.black_white` | field |
| `Aufbereitung.masken` | `CleanupPlan.masks` | field |
| `Aufbereitung.maskenfarbe` | `CleanupPlan.mask_colour` | field |
| `Aufbereitung.aktiv()` | `CleanupPlan.active()` | method |
| `Aufbereitung.als_dict()` | `CleanupPlan.as_dict()` | method |
| `Aufbereitung.vollstaendig()` | `CleanupPlan.full_dict()` | method |
| `Aufbereitung.aus_dict()` | `CleanupPlan.from_dict()` | method |
| `rendere` | `render` | function |
| `schaetze_winkel` | `estimate_tilt` | function |
| `schaetze_winkel(bild=)` | `estimate_tilt(image=)` | parameter |
| `schaetze_winkel(maximal=)` | `estimate_tilt(maximum=)` | parameter |
| `finde_ecken` | `find_corners` | function |
| `finde_ecken(bild=)` | `find_corners(image=)` | parameter |
| `finde_ecken(skala=)` | `find_corners(scale=)` | parameter |
| `raender_dunkel` | `dark_borders` | function |
| `raender_dunkel(bild=)` | `dark_borders(image=)` | parameter |
| `raender_dunkel(breite=)` | `dark_borders(width=)` | parameter |
| `raender_dunkel(grenze=)` | `dark_borders(limit=)` | parameter |
| `farbanteil` | `colour_share` | function |
| `farbanteil(bild=)` | `colour_share(image=)` | parameter |
| `rauschanteil` | `noise_share` | function |
| `rauschanteil(bild=)` | `noise_share(image=)` | parameter |
| `hintergrund_ungleich` | `uneven_background` | function |
| `hintergrund_ungleich(bild=)` | `uneven_background(image=)` | parameter |
| `vorschlag` | `suggest` | function |
| `vorschlag(bild=)` | `suggest(image=)` | parameter |
| `vorschlag(foto=)` | `suggest(photo=)` | parameter |
| `vorschlag(skala=)` | `suggest(scale=)` | parameter |
| `vorschlag(aufloesung=)` | `suggest(resolution=)` | parameter |
| `beschreibung` | `describe` | function |
| `textverfeinerung` | `letter_finish` | function |
| `textverfeinerung(grau=)` | `letter_finish(grey=)` | parameter |
| `textverfeinerung(faktor=)` | `letter_finish(factor=)` | parameter |
| `gitterbereiche` | `grid_areas` | function |
| `gitterbereiche(bild=)` | `grid_areas(image=)` | parameter |
| `ohne_linien` | `without_lines` | function |
| `ohne_linien(bild=)` | `without_lines(image=)` | parameter |
| `Schritt` | `Step` | constant |
| `wende_an` | `apply_plan` | function |
| `wende_an(bild=)` | `apply_plan(image=)` | parameter |
| `wende_an(skala=)` | `apply_plan(scale=)` | parameter |
| `als_png` | `as_png` | function |
| `als_png(bild=)` | `as_png(image=)` | parameter |
| `seiten_ersetzen` | `replace_pages` | function |
| `seiten_ersetzen(nummer=)` | `replace_pages(number=)` | parameter |
| `seite_ersetzen` | `replace_page` | function |
| `seite_ersetzen(nummer=)` | `replace_page(number=)` | parameter |
| `vorschau_png` | `preview_png` | function |
| `np_contig(bild=)` | `np_contig(image=)` | parameter |
| `schaetze_ausrichtung` | `estimate_orientation` | function |
| `schaetze_ausrichtung(bild=)` | `estimate_orientation(image=)` | parameter |

## `optdoc.pagetext` (was `optdoc.textebene`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `Seitentext` | `PageText` | class |
| `Seitentext.nummer` | `PageText.number` | field |
| `Seitentext.breite` | `PageText.width` | field |
| `Seitentext.hoehe` | `PageText.height` | field |
| `Seitentext.text` | `PageText.text` | field |
| `Seitentext.boxen` | `PageText.boxes` | field |
| `Seitentext.zeilen` | `PageText.lines` | field |
| `Seitentext.groessen` | `PageText.sizes` | field |
| `Seitentext.basislinien` | `PageText.baselines` | field |
| `Seitentext.zeilenboxen` | `PageText.line_boxes` | field |
| `Seitentext.quelle` | `PageText.source` | field |
| `Seitentext.konfidenzen` | `PageText.confidences` | field |
| `Seitentext.wortspannen` | `PageText.word_spans` | field |
| `Seitentext.hat_textebene()` | `PageText.has_text_layer()` | method |
| `Seitentext.unsichere_woerter()` | `PageText.uncertain_words()` | method |
| `Seitentext.rects()` | `PageText.rects()` | method |
| `Seitentext.rects(ende=)` | `PageText.rects(end=)` | parameter |
| `Seitentext.woerter()` | `PageText.words()` | method |
| `Seitentext.zeile_von()` | `PageText.line_of()` | method |
| `Seitentext.schriftgroesse()` | `PageText.font_size()` | method |
| `Seitentext.schriftgroesse(ende=)` | `PageText.font_size(end=)` | parameter |
| `Seitentext.basislinie()` | `PageText.baseline()` | method |
| `Seitentext.basislinie(ende=)` | `PageText.baseline(end=)` | parameter |
| `Seitentext.freier_raum_rechts()` | `PageText.free_space_right()` | method |
| `Seitentext.freier_raum_rechts(ende=)` | `PageText.free_space_right(end=)` | parameter |
| `Seitentext.als_dict()` | `PageText.as_dict()` | method |
| `Seitentext.aus_dict()` | `PageText.from_dict()` | method |
| `lese_seite` | `read_text_layer` | function |
| `lese_seite(nummer=)` | `read_text_layer(number=)` | parameter |
| `lese_dokument` | `read_text_layers` | function |

## `optdoc.structure` (was `optdoc.gliederung`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `UEBERSCHRIFT_GROSS` | `HEADING_LARGE` | constant |
| `UEBERSCHRIFT_KLEIN` | `HEADING_SMALL` | constant |
| `Zeile` | `Line` | class |
| `Zeile.start` | `Line.start` | field |
| `Zeile.ende` | `Line.end` | field |
| `Zeile.text` | `Line.text` | field |
| `Zeile.x0` | `Line.x0` | field |
| `Zeile.y0` | `Line.y0` | field |
| `Zeile.x1` | `Line.x1` | field |
| `Zeile.y1` | `Line.y1` | field |
| `Zeile.hoehe` | `Line.height` | field |
| `Zeile.leer()` | `Line.empty()` | method |
| `Zeile.breite()` | `Line.width()` | method |
| `Rolle` | `Role` | class |
| `Rolle.art` | `Role.kind` | field |
| `Rolle.ebene` | `Role.level` | field |
| `Rolle.fett` | `Role.bold` | field |
| `Rolle.trenner` | `Role.separator` | field |
| `Rolle.tabelle` | `Role.table` | field |
| `Gliederung` | `Structure` | class |
| `Gliederung.rollen` | `Structure.roles` | field |
| `Gliederung.tabellen()` | `Structure.tables()` | method |
| `Gliederung.ueberschriften()` | `Structure.headings()` | method |
| `Gliederung.rendere()` | `Structure.render()` | method |
| `zeilen_aus` | `lines_of` | function |
| `zeilen_aus(seite=)` | `lines_of(page_text=)` | parameter |
| `fette_zeilen` | `bold_lines` | function |
| `fette_zeilen(zeilen=)` | `bold_lines(lines=)` | parameter |
| `fette_zeilen(grau=)` | `bold_lines(grey=)` | parameter |
| `fette_zeilen(skala=)` | `bold_lines(scale=)` | parameter |
| `gliedere` | `analyse_structure` | function |
| `gliedere(seite=)` | `analyse_structure(page_text=)` | parameter |
| `gliedere(fett=)` | `analyse_structure(bold=)` | parameter |
| `gliedere_seite` | `analyse_page_structure` | function |

## `optdoc.alignment` (was `optdoc.textabgleich`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `textebene_aus_korrektur` | `text_layer_from_correction` | function |

## `optdoc.settings` (was `optdoc.einstellungen`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `EinstellungenArt` | `SettingsLike` | class |
| `EinstellungenArt.ocr_backend` | `SettingsLike.ocr_backend` | field |
| `EinstellungenArt.tesseract_pfad` | `SettingsLike.tesseract_path` | field |
| `EinstellungenArt.tesseract_sprachen` | `SettingsLike.tesseract_languages` | field |
| `Einstellungen` | `Settings` | class |
| `Einstellungen.ocr_backend` | `Settings.ocr_backend` | field |
| `Einstellungen.tesseract_pfad` | `Settings.tesseract_path` | field |
| `Einstellungen.tesseract_sprachen` | `Settings.tesseract_languages` | field |
| `setze_einstellungen` | `set_settings` | function |
| `setze_einstellungen(einstellungen=)` | `set_settings(settings=)` | parameter |
| `lade_einstellungen` | `load_settings` | function |

## `optdoc.reading` (was `optdoc.lesen`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `VORSCHLAG_DPI` | `SUGGESTION_DPI` | constant |
| `MAX_PIXEL_HOCHSKALIERT` | `MAX_PIXELS_UPSCALED` | constant |
| `ist_foto` | `is_photo` | function |
| `ist_foto(pfad=)` | `is_photo(path=)` | parameter |
| `vorschlag_fuer` | `suggestion_for` | function |
| `vorschlag_fuer(foto=)` | `suggestion_for(photo=)` | parameter |
| `plan_fuer` | `plan_for` | function |
| `plan_fuer(foto=)` | `plan_for(photo=)` | parameter |
| `Seite` | `PageReading` | class |
| `Seite.nummer` | `PageReading.number` | field |
| `Seite.text` | `PageReading.text` | field |
| `Seite.ocr` | `PageReading.ocr` | field |
| `Seite.gliederung` | `PageReading.structure` | field |
| `Seite.markdown()` | `PageReading.markdown()` | method |
| `Lesung` | `Reading` | class |
| `Lesung.quelle` | `Reading.source` | field |
| `Lesung.doc` | `Reading.doc` | field |
| `Lesung.plan` | `Reading.plan` | field |
| `Lesung.seiten` | `Reading.pages` | field |
| `Lesung.leser` | `Reading.reader` | field |
| `Lesung.ohne_text()` | `Reading.without_text()` | method |
| `Lesung.schliessen()` | `Reading.close()` | method |
| `lies_seite` | `ocr_page` | function |
| `lies_seite(leser=)` | `ocr_page(reader=)` | parameter |
| `lies_seite(nummer=)` | `ocr_page(number=)` | parameter |
| `lies` | `read` | function |
| `lies(pfad=)` | `read(path=)` | parameter |
| `lies(leser=)` | `read(reader=)` | parameter |
| `lies(sprachen=)` | `read(languages=)` | parameter |
| `lies(tabellen=)` | `read(tables=)` | parameter |
| `lies(papier=)` | `read(paper=)` | parameter |
| `lies(aufbereiten=)` | `read(clean_up=)` | parameter |
| `lies(gliedern=)` | `read(with_structure=)` | parameter |

## `optdoc.output` (was `optdoc.ausgabe`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `SCHRIFT` | `FONT` | constant |
| `unsichtbare_textebene` | `invisible_text_layer` | function |
| `unsichtbare_textebene(seite=)` | `invisible_text_layer(page_text=)` | parameter |
| `plan_als_dict` | `plan_as_dict` | function |
| `plan_als_dict(lesung=)` | `plan_as_dict(reading=)` | parameter |
| `lesung_als_dict` | `reading_as_dict` | function |
| `lesung_als_dict(lesung=)` | `reading_as_dict(reading=)` | parameter |
| `markdown(lesung=)` | `markdown(reading=)` | parameter |
| `durchsuchbares_pdf` | `searchable_pdf` | function |
| `durchsuchbares_pdf(lesung=)` | `searchable_pdf(reading=)` | parameter |
| `schreibe` | `write` | function |
| `schreibe(lesung=)` | `write(reading=)` | parameter |
| `schreibe(ordner=)` | `write(folder=)` | parameter |
| `schreibe(stamm=)` | `write(stem=)` | parameter |

## `optdoc.ocr` (was `optdoc.ocr`)

| 0.0.1 | 0.1.0 | kind |
|---|---|---|
| `MAX_PIXEL` | `MAX_PIXELS` | constant |
| `UNSICHER_KONFIDENZ` | `UNCERTAIN_CONFIDENCE` | constant |
| `UNLESBAR` | `UNREADABLE` | constant |
| `Kasten` | `Bounds` | constant |
| `OCRWort` | `OCRWord` | class |
| `OCRWort.text` | `OCRWord.text` | field |
| `OCRWort.x0` | `OCRWord.x0` | field |
| `OCRWort.y0` | `OCRWord.y0` | field |
| `OCRWort.x1` | `OCRWord.x1` | field |
| `OCRWort.y1` | `OCRWord.y1` | field |
| `OCRWort.konfidenz` | `OCRWord.confidence` | field |
| `OCRBackend.erkenne()` | `OCRBackend.recognise()` | method |
| `OCRBackend.erkenne(skala=)` | `OCRBackend.recognise(scale=)` | parameter |
| `OCRFehler` | `OCRError` | class |
| `vorverarbeite` | `preprocess` | function |
| `tesseract_programm` | `tesseract_program` | function |
| `tesseract_programm(pfad=)` | `tesseract_program(path=)` | parameter |
| `tesseract_sprachen` | `tesseract_languages` | function |
| `tesseract_sprachen(programm=)` | `tesseract_languages(program=)` | parameter |
| `TesseractBackend.verfuegbar()` | `TesseractBackend.available()` | method |
| `TesseractBackend.erkenne()` | `TesseractBackend.recognise()` | method |
| `TesseractBackend.erkenne(skala=)` | `TesseractBackend.recognise(scale=)` | parameter |
| `RapidOCRBackend.verfuegbar()` | `RapidOCRBackend.available()` | method |
| `RapidOCRBackend.erkenne()` | `RapidOCRBackend.recognise()` | method |
| `RapidOCRBackend.erkenne(skala=)` | `RapidOCRBackend.recognise(scale=)` | parameter |
| `backend(sprachen=)` | `backend(languages=)` | parameter |
| `backend(tabellen=)` | `backend(tables=)` | parameter |
| `verfuegbare_backends` | `available_backends` | function |
| `seitentext_aus_woerter` | `page_text_from_words` | function |
| `seitentext_aus_woerter(woerter=)` | `page_text_from_words(words=)` | parameter |
| `seitentext_aus_woerter(nummer=)` | `page_text_from_words(number=)` | parameter |
| `seitentext_aus_woerter(breite=)` | `page_text_from_words(width=)` | parameter |
| `seitentext_aus_woerter(hoehe=)` | `page_text_from_words(height=)` | parameter |
| `UnlesbareZeile` | `UnreadableLine` | class |
| `UnlesbareZeile.seite` | `UnreadableLine.page_text` | field |
| `UnlesbareZeile.start` | `UnreadableLine.start` | field |
| `UnlesbareZeile.ende` | `UnreadableLine.end` | field |
| `UnlesbareZeile.text` | `UnreadableLine.text` | field |
| `UnlesbareZeile.rects` | `UnreadableLine.rects` | field |
| `UnlesbareZeile.schriftgroesse` | `UnreadableLine.font_size` | field |
| `unlesbare_regionen` | `unreadable_lines` | function |
| `unlesbare_regionen(seite=)` | `unreadable_lines(page_text=)` | parameter |
| `unlesbare_regionen(mindestanteil=)` | `unreadable_lines(min_share=)` | parameter |
| `erkenne_seite` | `recognise_page` | function |
| `erkenne_seite(nummer=)` | `recognise_page(number=)` | parameter |
| `erkenne_seite(vorverarbeitung=)` | `recognise_page(preprocessing=)` | parameter |
| `braucht_ocr` | `needs_ocr` | function |
| `braucht_ocr(textebene=)` | `needs_ocr(text_layer=)` | parameter |
| `braucht_ocr(mindestanteil=)` | `needs_ocr(min_share=)` | parameter |

## Values and keys

| Where | 0.0.1 | 0.1.0 |
|---|---|---|
| OCR engine name (`backend()`, `OPTDOC_OCR`, `Settings.ocr_backend`) | `"aus"` | `"none"` |
| paper size for an image as large as itself (`open_document`, `--paper`) | `"bild"` | `"image"` |
| `CleanupPlan.mask_colour` | `"weiss"` | `"white"` (any other value: black) |
| `Role.kind` (structure) | `"absatz"`, `"ueberschrift"`, `"liste"`, `"tabelle"` | `"paragraph"`, `"heading"`, `"list"`, `"table"` |
| `Role.separator` (structure) | `"absatz"`, `"zeile"`, `"wort"`, `"silbe"` | `"paragraph"`, `"line"`, `"word"`, `"syllable"` |
| `PageText.as_dict()` keys | German field names | the English field names above |
| `CleanupPlan.full_dict()` / `as_dict()` keys | German field names | the English field names above |
| `describe(plan)` | German wording | English; `describe(plan, "de")` gives the German wording of 0.0.1 |
| `UNLESBAR` (`"[unlesbar]"`) | constant in `optdoc.ocr` | removed: the placeholder for a covered line is the caller's own |
| messages of `OCRError` and `ValueError` | German | English |

Saved plans and page texts from 0.0.1 (German keys) are not read by 0.1.0: `from_dict` ignores unknown keys,
so a plan comes back empty and a page text fails its check. Map the keys with this table, or make them anew.
