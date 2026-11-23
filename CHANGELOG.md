# Changelog

## 0.4.0 (2026-11-23)

Interface 2: the configuration takes the place of the plan (see `docs/interface.md`, "From
interface 1").

### Added

- **The window** (`optdoc edit`, `optdoc.gui`, extra `gui`, PySide6), moved here from PseudonyMed's
  pages "Aufbereiten" and "Texterkennung", in English and German (`--language`). Clean up each page
  before and after (every step switchable with its strength, rotation, areas erased, the suggestion
  restored, a page left as it came, copied to every page, orientation detected) and check the text
  beside the page, words read with little confidence marked. It starts with optdoc's suggestions, so
  that *Apply* at once gives what `prepare` gives. *Apply* writes the four files, *Save and continue
  later* the configuration alone, *Cancel* nothing (error `cancelled`). No settings of its own, nothing
  outside `--out`, no network; checked under `sandbox-exec` without network and with empty home and
  temporary folders. `--self-test` goes through it without a person (the build uses it).
- **The configuration** (`<stem>.optdoc.json`, format `optdoc-config` version 1, `optdoc.project`):
  the settings, every page's clean-up, the words OCR read and the person's corrections, the file it
  belongs to by its SHA-256; no paths, no times. It is also embedded in the PDF (`optdoc.json`).
  `prepare --config` and `edit --config` take it, or the PDF that carries it. **The same file and the
  same configuration give the same four files, byte for byte**: the words are stored, so OCR does not
  run again, and the PDF carries no time and an identifier made from the configuration.
- **Corrected text** in the text layer, the reading and the Markdown: the corrected text is laid on the
  boxes OCR found; words left as read keep their confidence; each OCR word in the reading says `by`:
  `"ocr"` or `"person"`. The answer lists the `corrected` pages.
- `optdoc.project.Project`, the work on one document for programs: open, change plans and corrections,
  read page by page, save the configuration, build the result.
- Kinds of error `bad-config` (reasons `json`, `format`, `page`, `field`), `config-mismatch`,
  `not-ocr`, `cancelled`, `no-gui`; `readers` says whether the window can open (`window`).
- `alignment.align_correction`: `text_layer_from_correction`, and which words a person wrote.
- `ocr.recognise_words`, `cleanup.cleaned_image` and `cleanup.put_page_image`: the steps of
  `recognise_page` and `replace_pages`, one at a time.

### Changed

- `reading.read` works through a project; its result carries the configuration (`Reading.config`).
- `alignment.text_layer_from_correction` keeps the engine's confidence for a word left as it was
  read; before, every word of a corrected text had confidence 1.
- `CleanupPlan.from_dict` refuses a broken plan as `bad-config` (was `bad-plan`).
- The standalone program carries PySide6 (Qt Widgets only): 161.6 MB as one file, 506.4 MB as a folder.

### Removed

- `<stem>.plan.json`, `prepare --plan`, the answer field `plan` and the kind of error `bad-plan`: the
  configuration holds the plans.
- `reading.ocr_page`; use `Project.read`.

## 0.3.0 (2026-11-23)

### Added

- **Tables with their cells** (`optdoc.tables`, extra `tables`): optdoc finds the tables of every page
  with Camelot (hybrid) in the PDF it has just written, on scanned and photographed pages in its own
  text layer, and puts them into the reading: per page `tables`, each with its box, Camelot's confidence
  and its rows of cells (text and box). A table Camelot finds twice gives every row once. On invented
  laboratory reports in three layouts: 216 of 216 rows in born-digital PDFs cut and read right; 211 of
  216 in photos cut right, 193 read exactly. Compared were Camelot, img2table, pdfplumber, RapidTable,
  Tabula and PyMuPDF; Tabula would need Java and read photos worse.
- `prepare --no-cells`; the answer of `prepare` counts the tables, `readers` says whether they can be
  found (`tables`).
- `optdoc bench` scores tables where a document has `<name>.cells.json`; `bench/lab_reports.py` writes
  one per report.

### Changed

- The text layer leaves the gap between two cells of a table open (an ordinary space, then the next
  word where it is printed) and stretches the space only within a cell. Programs that find tables by
  the gaps between text see the columns: Camelot cut 49 of 54 photographed rows right, none before.
  PDFKit still reads every row as one line.
- A gap between OCR words wider than the words are high is a cell boundary (a tab in the text). The
  former rule, far wider than the page's usual gap, found none in two of three laboratory layouts;
  their Markdown now has tables.
- The build of the standalone program switches off ONNX Runtime's telemetry for PyInstaller as well,
  which loads the library to collect it.

### Fixed

- The PDF is let go once its tables are found: Camelot's objects held it open until a garbage
  collection, and Windows cannot delete an open file.

## 0.2.1 (2026-11-23)

### Fixed

- Standard error holds optdoc's own lines only, as the interface says: on Linux, ONNX Runtime wrote a
  warning there (about PCI buses, in colour) between the progress lines. For the time of a command,
  what libraries write to standard error is discarded; the progress lines and the usage line get
  through.

## 0.2.0 (2026-11-23)

### Added

- **The command line is an interface** ([docs/interface.md](docs/interface.md), interface 1): every
  command answers with one JSON object on standard output, carrying `interface` and `made_with`; a
  failure as well, with a fixed kind (`missing`, `unsupported`, `unreadable`, `encrypted`, `no-reader`,
  `bad-plan` …), its details and its message in English and German, and exit status 2.
- `prepare --progress`: a line `{"page": n, "of": m}` on standard error before each page.
- `prepare --photo` and `--scan`; without them a photographed page is told from a scanned one by the
  page itself, inside a PDF too (photos bound into one), so that the photos of a bound PDF are found
  and unwarped. A frame or a ruled table on a scan is never taken for the sheet.
- Pages turned by `/Rotate` are opened upright without touching their pictures; the PDF optdoc writes
  has no turned pages, and the boxes of the reading are those of the page as shown.
- `optdoc.errors`: `OptdocError` (`kind`, `details`) and `describe_error(error, "de")`, the same kinds and
  wording for programs that use optdoc as a library.
- `optdoc.offline`: the command line refuses every attempt to reach the network, and switches off the
  telemetry of ONNX Runtime, which on macOS wrote a device identifier and facts about the computer into
  a queue for sending to Microsoft (in `~/Library/Application Support/Microsoft/DeveloperTools`).
- The standalone program for an application to ship beside it (a Tauri sidecar):
  `packaging/build.py` builds `optdoc-<target>` with PyInstaller (or a folder with `--onedir`), lists
  the packages inside and their licences, and tries the program out; [docs/sidecar.md](docs/sidecar.md).
- `optdoc/py.typed`: type checkers read optdoc's annotations.

### Changed

- **The text layer is written line by line** (`optdoc.textlayer`): one text object per OCR line, words
  at their printed width, real spaces stretched over the gaps, a font of its own that writes every
  character as read ("≤", "↑", where the standard font knew only Windows-1252). A row of a table comes
  out as one line in PDFKit and MuPDF, and words are no longer glued together.
- OCR words are grouped into lines from left to right, each word against the last one of its line, so
  that a slightly tilted table row stays one line.
- Tesseract gets the page on standard input; no image of a page is written to a temporary file.
- `readers` no longer loads the engines to list them.
- `SettingsLike` declares read-only properties, so that an object with properties fits it.
- `--paper image` placed an image on A4; it keeps the image's own size again.

### Removed

- `ValueError`, `NotImplementedError` and the free-text `OCRError` messages of optdoc's modules: every
  error is an `OptdocError` (an `OCRError` for the engines), worded by its kind. A caller that matched
  the old English messages uses `error.kind` and `describe_error` instead.
- Error messages on standard error; the answer on standard output says it.
- `reading.is_photo` and `reading.plan_for`: the suggestion tells photos by each page
  (`reading.suggestion_for(page, photo=None)`).
- `output.invisible_text_layer`: `optdoc.textlayer.add_font` and `write_page`.

## 0.1.0 (2026-11-22)

English identifiers throughout (`docs/renames-0.1.0.md`); the test bench (`optdoc bench`) and invented
laboratory reports to print and photograph.

## 0.0.1 (2026-11-22)

PseudonyMed's document layer as a program of its own: loading, clean-up, OCR, structure, searchable PDF.
