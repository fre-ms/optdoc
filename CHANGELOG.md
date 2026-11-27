# Changelog

## 0.10.1 (2026-11-27)

The picture as a page is written once, in doccor (0.3.0). Nothing a caller relies on changed:
interface 5, `optdoc-config` version 3.

### Changed

- **How a picture is looked at is doccor's** (`doccor.pictures`): optdoc and ocrdoc each had
  the lines that make a page of a picture; now there is one place, and the page is the same in
  every tool by construction. `optdoc.loading` keeps `open_document`, `is_picture` and
  `LONG_SIDE`; `IMAGE_SUFFIXES` and `HEIC_SUFFIXES` are `doccor.pictures.SUFFIXES` and `HEIC`.
- **A JPEG is one picture, whatever else it carries.** A phone's JPEG may hold a second image
  beside the photo (a gain map for bright screens); optdoc looked at such a file as one page
  already, and `optdoc.pictures.count` now says one as well.
- The kinds of error `unsupported`, `unreadable` and `encrypted` are worded in doccor, with the
  same words.

## 0.10.0 (2026-11-27)

A picture stays a picture. docrepro forces no file type, and optdoc is the first of its tools to
keep the one it is handed. Interface 5; `optdoc-config` version 3.

### Changed

- **Handed a picture, optdoc writes a picture of the same type**: a JPEG gives a JPEG, a HEIC a
  HEIC, and so for PNG, TIFF, WebP, BMP, GIF and PNM. Until now it made a PDF of every picture, on
  a sheet of A4. A PDF comes back as a PDF, as before. Making a PDF of a picture is typdoc's step.
- **Prepared from its own pixels**, in its own resolution (not from a rendering of a page), and
  written at quality 92 with full colour resolution (JPEG, HEIC, WebP) or without loss (the
  others). A picture no plan changes is written as it came, byte for byte. A file of several
  pictures (a TIFF of several pages) stays one file. The same picture and configuration document
  give the same bytes (measured for HEIC as well: the same picture written in separate runs).
- **What the picture says of itself stays** (the user's decision): the camera, the moment, the
  place, the colour profile, the resolution. The orientation is set upright, since the prepared
  picture is; the small preview a camera embeds is left out, since it would still show the
  picture as it came; the sizes named are those of the prepared picture. A TIFF with directories
  of its own for such details (EXIF, GPS) is written without compression, which alone can carry
  them; any other TIFF with LZW.
- **A picture is looked at as a page whose long side is that of A4**, upright as its EXIF
  orientation says: the page typdoc binds it into (medRDS 9.5). A plan's coordinates mean the
  same whether optdoc is handed the picture or typdoc's PDF of it.
- **The configuration document is version 3**: no `paper`. It lies beside a picture, which has no
  place for it. Version 2 is no longer read.

### Removed

- `--paper`, the option `paper`, the kind of error `paper`, and `optdoc.loading.paper_size`: the
  sheet of paper a picture was placed on went with the PDF optdoc made of it.

### Fixed

- **WebP pictures open.** They were listed among the types optdoc takes and failed as
  "unreadable": the PDF library does not read them. Every picture that is no JPEG is now decoded
  by the library that also prepares it.

## 0.9.0 (2026-11-27)

Interface 4: one field renamed, in every tool of docrepro at once.

### Changed

- **The answer names the prepared document `document`**, no longer `pdf` (`run`, and `edit` on
  Apply); `optdoc.output.write` returns it under that key. No step of docrepro is to force a
  file type, so a document need not be a PDF, and a field called `pdf` would then point at a
  picture. optdoc itself still writes a PDF; that it writes back the type it was handed is to
  come. Callers read `document` where they read `pdf`.

## 0.8.0 (2026-11-26)

Models as an optional download, and the first one: a page that stands on its head or lies on
its side is set upright in the suggestion. optdoc needs no model and fetches none unasked.
Interface 3 and `optdoc-config` version 2 stay: everything here is added.

### Added

- **`optdoc models list [--models <folder>]`** shows the models optdoc can use, each with the
  address it comes from (https, a fixed revision), its SHA-256, size, licence and the page
  that states the licence, and whether it lies in the folder given. `about` lists them too.
- **`optdoc models fetch <name> --to <folder> [--progress]`**, the only command that goes on
  the network, and only when asked: it fetches that one file and keeps it only when its size
  and SHA-256 are the ones listed. Kinds of error `unknown-model`, `model-unreachable`,
  `model-checksum`. The mechanism is doccor's (0.2.0), the same for every tool of docrepro.
- **`--models <folder>`** for `run` and `edit`: what lies there is used, what does not is done
  without. Work stays off the network.
- **The model `page-orientation`** (PaddleOCR's PP-LCNet_x1_0_doc_ori, Apache-2.0, 6.8 MB;
  OpenCV runs it, optdoc gains no dependency): the suggestion turns a page upright that
  stands on its head or on its side, and "Detect the orientation" in the window asks it
  first. It decides only where it is sure (a probability of 0.8), by the middle of the page
  as it was trained, and where that shows it little, by the middle of what is written; a
  blank page is left as it is. Measured on invented pages, each turned four ways
  (`bench/orientation_bench.py`), the turn that puts the page upright was named:

  | pages | of | lines only | lines and OCR | the model |
  |---|---|---|---|---|
  | as made | 56 | 28 | 56 | 56 |
  | worn scans (askew, grainy) | 56 | 28 | 56 | 55 |
  | photographed at a slant | 48 | 24 | not measured | 44 |
  | scanned at 60 dpi | 48 | 24 | not measured | 48 |
  | one to three lines of text | 20 | 10 | not measured | 20 |
  | seconds per page | | 0.002 | 2.1 | 0.009 |

  Where the model was not right it was not sure and left the page (five pages); it turned no
  page of the bench wrongly.
- **The configuration document** names the model that took part in a suggested plan
  (`"models": ["page-orientation"]` on the page's entry); a plan a person decided names none.
  The turn is in the plan, so the same file and document give the same result without the
  model.

### Changed

- optdoc needs doccor 0.2.

## 0.7.0 (2026-11-26)

optdoc does one thing now: it makes a photographed or scanned page **faithful**. Reading it
(OCR, areas, tables, barcodes, the text layer, the reading, the bench) moved to **ocrdoc**,
with its history; what the tools of docrepro share is **doccor**'s (`docs/family-design.md`).
optdoc's output keeps the page's colours; the configuration document records every page's
frame, so that a person's decisions in ocrdoc survive a change in optdoc that does not move
the page. Interface 3; `optdoc-config` version 2. optdoc 0.6.0 stays available for whoever
needs both steps in one program until docrepro has it.

### Changed

- **Colours stay.** Evening out the background works per colour channel: the paper turns
  white, a red stamp stays red, a blue signature blue. Nothing takes coloured ink away any
  more. A page with less than 0.3 % of colour is stored in grey (PNG); one with colour by
  default as JPEG at quality 92 with full colour resolution, since a lossless page in colour
  is some ten times the size, or losslessly as PNG (`--colour-pages png`, the option
  `colour_pages`, a choice in the window). TIFF is no choice: a PDF holds no TIFF, and one
  given to it is stored exactly as a PNG. The plan has `grey`, suggested by the page.
- **The configuration document** is `optdoc-config` version 2: `input` (SHA-256, size,
  suffix and every page's size) instead of `source`; per page its `plan`, who decided it
  (`by`: "auto" or "person") and its `frame`, a fingerprint of where things lie on the
  prepared page (its size, and the turning, unwarping and straightening that made it).
  Light, contrast, colour and masks leave the frame as it is. Version 1 is refused.
- **The PDF** has the prepared pages and no text layer; it carries its configuration
  document (`optdoc.json`) for the steps after it. No reading and no Markdown: those are
  ocrdoc's.
- **The command line** has the verbs of every tool of docrepro: `about` (fields `clean_up`,
  `heic`, `window`, `upside_down`), `run` (what `prepare` did for the page) and `edit`.
  Options: `--out`, `--config`, `--paper`, `--photo`/`--scan`, `--no-clean-up`,
  `--colour-pages`, `--progress`. The answer of `run`: `pdf`, `config`, `pages`, `cleaned_up`, `unwarped`,
  `decided`. Interface 3 (`docs/interface.md`).
- **The window** has the preparation only, with "Store in grey" among the steps; "Detect
  the orientation" tells an upside-down page where ocrdoc is installed (a provider, not a
  dependency), else portrait or landscape from the lines.
- optdoc depends on **doccor**: the configuration document's mechanics, the common kinds of
  error and their wording, the command line's manners, the network lock, and the window's
  page view, worker and words.
- Extras: `cleanup` (OpenCV, NumPy, Pillow, pillow-heif) and `gui`.

### Removed

- Upscaling, letter mode, removing coloured ink and ruled lines, black and white (ocrdoc's
  filters now, on its own copy of a page); the OCR engines, page text, text layer,
  corrections, structure, areas, tables, the reading and the bench (ocrdoc); the settings of
  the OCR layer (`OPTDOC_OCR` …); `readers`, `prepare`, `bench`; the kinds of error
  `unknown-reader`, `no-reader`, `reader-failed`, `not-ocr`, `page-text`.
- The standalone program and its build (`packaging/`, `docs/sidecar.md`): one program with
  every tool inside is to come with docrepro.
- `optdoc.offline`, `optdoc.gui.view` and `optdoc.gui.worker` (now in `doccor`).

## 0.6.0 (2026-11-26)

Areas, as in FineReader: a page is divided into regions, found automatically and corrected by
hand, and a table's grid can be set. Tables, barcodes (read as well), pictures, stamps and
handwriting are found automatically; the reading order of text areas and layout models as an
optional download are to come. Interface 2 and the formats of the configuration and the reading
(version 1) gain fields; nothing is taken away.

### Added

- **Areas** (`optdoc.layout`): text, table, image, barcode, handwriting, stamp, ignore, each with
  its box in points of the cleaned page and who set it ("auto" or "person"); a table with its grid
  (inner column and row lines, merged cells) and operations on it (add, move and remove a line,
  merge and split cells, move and resize with the grid). What lies in no area is text. Words in
  pictures, barcodes and "ignore" areas stay out of the text, the text layer and the reading;
  handwriting and stamps are read and marked.
- **The window's tab "Areas"** between clean-up and text: the areas in their colours, numbered in
  reading order; a drawing tool per kind; select, move, resize, change the kind, delete; for a
  table add a column or row line, drag one, take one away, merge cells by dragging over them and
  split them by a click; find the areas again.
- The configuration keeps every page's areas (`layout`, with `by`) and the setting `cells`; the
  reading lists every page's `regions` and says of each table who set it (`by`).
- **Barcodes, pictures, stamps and handwriting found** (`optdoc.areas`), on the page where it lies
  once cleaned up but in its own colours: barcodes with zxing-cpp (the extra `barcodes`), read as
  well (format and content in the reading; a line barcode's box grown over its bars); stamps by one
  strong colour with lines of letters; pictures by filled or many-toned ink with hardly a word
  read in it (a picture keeps its words out of the text, so it needs a clear case); handwriting
  by ink of the height of writing in which OCR read hardly a word. Measured on six invented
  letters (`bench/area_letters.py`), born digital / scanned in colour / in grey / photographed:
  pictures 12 / 12 / 10 / 12 of 12, barcodes 17 / 17 / 17 / 15 of 17 with their content, stamps
  6 / 5 / 0 / 5 of 6, handwriting 11 / 11 / 9 / 10 of 12, wrong ones at most 2 pictures and 1
  handwriting (on the photos); on laboratory reports nothing besides their tables, the numbers
  read unchanged. `--no-areas` (`Options.areas`) finds none of them; `readers` says whether
  barcodes can be read (`barcodes`).
- `Project.regions`, `set_regions`, `find_regions`, `find_tables`, `forget_regions`;
  `read(..., cells=..., scratch=...)`; `cleanup.geometry_only`.

### Changed

- The tables of a page come from its table areas: every word goes into the cell of the grid its
  middle lies in. Camelot finds the tables of a page once, on that page in memory, and they are
  stored with the configuration, so that a reproduction does not run Camelot again. Measured on
  12 photographed and 12 born-digital invented reports: the same cells as before, row for row
  (211 of 216 photographed rows cut right, 196 read exactly; every born-digital row).
- The Markdown writes a table with a grid from its cells.
- `--no-cells` is a setting of the configuration; beside `--config` it leaves out the tables
  found before, but not those a person set.
- A table a person changed counts as certain (`confidence` 1).
- **The suggestion straightens a tilt from 0.3 degrees** (was 1.2). Invented laboratory reports
  scanned half a degree to a degree askew lost the grid of their tables (0 to 36 of 108 rows cut
  right); straightened, 101 to 108, while the numbers read stayed within a few of 306 either way.

### Fixed

- Tables on scans: Camelot's table of texts can have fewer rows or columns than its grid of
  cells, and optdoc stopped at that (since 0.3.0), so that many a scanned page had no tables.
- Camelot is given a page only as a file in a folder of optdoc's own inside the results folder,
  removed at once: given a PDF in memory, it writes it to the temporary folder.

### Removed

- `output.write(..., cells=...)`: the tables are made with the reading (`Options.cells`).

## 0.5.0 (2026-11-23)

Photos taken at a slant. Interface 2 and the configuration's format are unchanged, but a
configuration made by 0.4.0 gives a different PDF for a photographed page: the sheet now has its
true proportions.

Measured on 30 invented laboratory reports photographed by a simulated phone camera (26 mm),
six each on a dark desk at a slight and at a strong slant, on a light grey table, on a wooden
desk, and with the foot or head of the sheet cut off by the photo: the sheet is found in 29
(0.4.0: 21); OCR then reads 1525 of 1530 numbers right (0.4.0: 1450; unwarped with the true
corners: 1522) and 91 % of the table rows exactly (0.4.0: 61 %). Compared were Apple Vision's
document and rectangle detection (1499 numbers, 66 % of rows), DocAligner, UVDoc (PaddleOCR's,
which bent the tables) and page-dewarp (which needs a page full of text); none did better.

### Changed

- **True proportions.** An unwarped sheet takes its width and height from the perspective of its
  corners (Zhang and He, 2007), with the focal length from the corners where they tell it and a
  phone's (26 mm) where they do not, snapped to A4, A5, Letter or Legal within 3 %. Before, it took
  the longer of each pair of sides: 8 to 43 % off at a slant; now within 1 %, and within about 5 %
  for a phone between 24 and 28 mm with corners a few pixels off (before snapping).
- **The sheet is found more often.** Besides the edge search, a second search fits straight lines
  to the visible edges of the paper, so that a corner may lie outside the photo; where a whole edge
  of the sheet is outside, it is reconstructed from the other three and the camera, and what the
  photo did not show stays white. The white bars of a photo placed on paper are no part of the
  picture.
- **Desk or paper** is told by a narrow ring just outside the outline. Before, everything outside
  counted, so that a desk around the sheet made a table on it look like the sheet. The difference
  asked for is now 15 grey levels (was 30): a light grey table lay 34 to 37 below the paper, and
  paper around a frame is brighter than inside it, by 16 to 31. The corner search itself rejects an
  outline with paper around it, so `--photo` no longer cuts a page to a table.

### Added

- The window shows the sheet's four corners on the page before, to be dragged; where optdoc found
  none, dashed at the page's corners, as a start.
- `cleanup.sheet_aspect` (proportions from four corners) and `cleanup.turn_points`.

### Fixed

- A quarter turn in the window left the sheet's corners where they were on the unturned page, so
  that unwarping then cut out the wrong area; they turn with the page now.
- What lies outside the photo after unwarping is white; it repeated the pixels at the edge.

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
