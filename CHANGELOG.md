# Changelog

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
