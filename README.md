# optdoc

optdoc makes photographed and scanned documents legible. It finds and straightens the page, evens out
light and noise, reads the text with word boxes, gives it structure (paragraphs, lists, tables) and lays it
back onto the page as an invisible text layer. The result is a searchable PDF and a machine-readable
reading that other programs can build on. Everything runs on your own computer; nothing is sent anywhere
(the command line refuses any attempt to reach the network, and switches off the telemetry ONNX Runtime
would otherwise queue for Microsoft).

It is the document layer of two applications by the same author: [PseudonyMed](https://github.com/fre-ms/PseudonyMed),
which pseudonymises patient documents, and medorello, a records app that files documents and reads
values from them, such as the results printed on a photographed laboratory report. optdoc itself knows
nothing about either and works on any kind of document.

**Status: pre-alpha (0.6.0).** The code comes from PseudonyMed, where it has been tested for weeks, with its
history. Since 0.1.0 its identifiers are English (`docs/renames-0.1.0.md` lists the old German names); since
0.2.0 its command line is a described interface ([docs/interface.md](docs/interface.md)) and it can be built
as a standalone program ([docs/sidecar.md](docs/sidecar.md)); since 0.4.0 it has a window to correct the
clean-up and the text by hand, and a configuration from which a result can be made again, byte for byte;
since 0.6.0 a page is divided into areas (text, tables with their grid, pictures, barcodes, handwriting,
stamps, areas not to be read), found automatically and corrected by hand, as in FineReader.
`CHANGELOG.md` lists the changes.

## What it does today

- **Opens** PDFs and images (JPEG, PNG, TIFF, HEIC and more); an image is placed on a paper size (A4 by
  default, or its own size), honouring its EXIF orientation; a PDF page turned by `/Rotate` is set upright
  without touching its picture.
- **Cleans up** image-only pages, with an automatic suggestion per page: perspective correction of a
  photographed sheet (finds its corners, also one outside the photo or on a light table, and gives the
  sheet its true proportions; tells a photographed page from a scanned one by the page itself, also inside
  a PDF of bound photos, and never cuts a page to the frame of a table), straightening, rotation by quarter
  turns, dark scanner borders,
  coloured ink (stamps, highlighter), noise, contrast, sharpening, uneven background, ruled and table lines,
  upscaling for low-resolution images, masks. Every step can be switched and tuned.
- **Reads** with [RapidOCR](https://github.com/RapidAI/RapidOCR) (ONNX models in the wheel, no download) or
  [Tesseract](https://github.com/tesseract-ocr/tesseract), with real word boxes and confidences. Tables with
  ruled grids, which Tesseract's page segmentation tends to drop, are read a second time without their lines.
- **Structures** the OCR text as Markdown: paragraphs re-joined, headings by size and weight, lists,
  tables from wide gaps.
- **Divides a page into areas**: text, tables, pictures, barcodes, handwriting, stamps, and areas not to
  be read; what lies in no area is text. Words in pictures, barcodes and areas not to be read stay out of
  the text; handwriting and stamps are read and marked, so that a program such as a pseudonymiser can
  cover them. Barcodes are found and read (QR, DataMatrix, Code 128, EAN …; extra `barcodes`), pictures,
  stamps (by their colour) and handwriting found by measured rules.
- **Finds tables with their grid** (extra `tables`, Camelot), in born-digital PDFs and, through its own
  text layer, in scans and photos, and puts every word into the cell of the grid it lies in: a laboratory
  result comes out as a row of cells, name, value, unit, range, flag. On invented laboratory reports in
  three layouts every one of 216 rows in born-digital PDFs was cut and read right, and 211 of 216 in photos
  were cut right (196 read exactly).
- **Writes** a searchable PDF (the cleaned-up pages with the recognised words laid invisibly over the printed
  ones, line by line, so that selecting a word in a reader covers it and a program that takes the text out
  gets a row of a table as one line; every character as read, "≤" and "↑" too), the reading as JSON, the
  text as Markdown, and the configuration.
- **Lets a person correct it** in a window (extra `gui`, Qt): the clean-up of every page before and after,
  each step switchable, the sheet's corners to drag; the areas of the page, to be drawn, moved, resized,
  given another kind or deleted, and a table's grid, whose lines can be added, dragged and taken away and
  whose cells can be merged and split; and the text read by OCR beside the page, uncertain words marked, to
  be corrected by hand. A correction reaches the PDF's text layer, the reading and the Markdown. The work can be saved
  and taken up again later.
- **Makes the same result again.** The configuration (`<name>.optdoc.json`, also inside the PDF) holds
  every setting, the clean-up of every page, the words OCR read and the person's corrections, and nothing
  else (no paths, no times). The same file with the same configuration gives the same four files, byte for
  byte.

Decisions in the clean-up are measured, not guessed: binarising a page (Sauvola) looked good and made
RapidOCR nearly blind, so optdoc does not do it; a scan tilted by as little as half a degree lost the
grid of its tables (0 to 36 of 108 rows cut right), so the suggestion straightens from 0.3 degrees on
(101 to 108 rows, the numbers read as well as before within a few); neural unwarping (UVDoc) bent the tables of
photographed laboratory reports, while a sheet unwarped by its corners in its true proportions read as well
as with the true corners (1525 and 1522 of 1530 numbers on 30 invented photos). The tests guard the
first two and the unwarping at a slant.

## Install

Python 3.12 or later, with [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/fre-ms/optdoc
cd optdoc
uv sync --extra ocr --extra tables --extra gui --extra barcodes
```

The `ocr` extra brings RapidOCR, ONNX Runtime, OpenCV and NumPy (for the clean-up steps) and HEIC support;
the `tables` extra brings [Camelot](https://github.com/camelot-dev/camelot), which finds tables with their
cells; the `gui` extra brings PySide6 (Qt, LGPL 3.0) for the window.
Tesseract is optional and installed separately (`brew install tesseract tesseract-lang`,
`apt install tesseract-ocr tesseract-ocr-deu`).

## Command line

```
optdoc readers
optdoc prepare photo.heic --out results/
optdoc prepare scan.pdf --reader tesseract --languages deu+eng
optdoc edit scan.pdf --out results/ --language en
optdoc edit scan.pdf --out results/ --config results/scan.optdoc.json
```

`prepare` writes `<name>.pdf`, `<name>.reading.json`, `<name>.md` and `<name>.optdoc.json` into the folder
given and nowhere else. `edit` opens the window; *Apply* writes the same four files, *Save and continue
later* the configuration alone, *Cancel* nothing. `--config` (a `<name>.optdoc.json` or a PDF optdoc wrote)
starts from a configuration instead of optdoc's suggestions, for `prepare` and `edit` alike. Every command answers with one JSON object on standard output, so that programs in
any language can use optdoc as a helper; a failure too, with a fixed kind and its message in English and
German, and exit status 2. No answer quotes a document or its path. Options: `--reader
auto|rapidocr|tesseract|none`, `--languages`, `--paper a4|a5|a3|letter|legal|image`, `--config`, `--photo` or
`--scan` (instead of telling by each page), `--no-clean-up`, `--no-tables`, `--no-structure`, `--no-cells`
(no tables with their cells), `--progress` (a line of JSON per page on standard error). [docs/interface.md](docs/interface.md) describes the answers,
the kinds of error and the reading.

Settings without a configuration file: `OPTDOC_OCR` (the engine `auto` stands for), `OPTDOC_TESSERACT`
(the program's path), `OPTDOC_TESSERACT_LANGUAGES`. An application that embeds optdoc hands over its own
with `optdoc.settings.set_settings`.

## Standalone program

`uv run python packaging/build.py` builds optdoc as one program with everything in it (Python, the OCR
models, Camelot and all), named the way Tauri wants a sidecar (`optdoc-aarch64-apple-darwin`), and tries it
out: 162 MB as one file (the window included), or a faster-starting folder with `--onedir`. See [docs/sidecar.md](docs/sidecar.md).

## Test bench

`optdoc bench <folder>` scores the readings of documents whose content is known. Next to every document lies a
truth file `<name>.truth.txt`, one line per item as it is printed (`Kalium 5,8 mmol/l 3,5 - 5,1 H`). The answer
is numbers only (rows found word for word, numbers read right in their own row, rows with every number right,
similarity, engine confidence), per document and per engine. Documents are named by their position, never by file
name, and no word of a document or a truth file is printed, not even in an error. So the bench can run on real
documents on your own computer while only the figures are shared.

Invented laboratory reports to print and photograph:

```
uv run python bench/lab_reports.py reports/ 6     # reports/lab-01.pdf … and lab-01.truth.txt …
# print them, photograph each, save the photo as reports/lab-01.jpg (or .heic, .png)
optdoc bench reports/
```

On those reports as clean 200-dpi scans RapidOCR reads 99.0 % of the numbers right (Tesseract 95.1 %); tilted by
2°, noisy and at 150 dpi 96.1 % (Tesseract 63.8 %). That is why every number is to be read twice (see *Planned*).

Where a document also has `<name>.cells.json` (the cells of each row as printed; `bench/lab_reports.py`
writes it), the bench scores its tables as well: rows cut into the right cells, rows read exactly.

## The reading

`<name>.reading.json` (format `optdoc-reading`, version 1) holds, per page, its size in points, where the text
came from (`text` layer or `ocr`), the text, its Markdown, and every word with its offsets in the text, its box
in points from the top left of the page as shown and, for OCR, the engine's confidence, and the page's
tables with their cells. It also names the engine, the optdoc version and the clean-up plans; a word a
person wrote in the window is marked as theirs.

## In Python

```python
from optdoc import output
from optdoc.reading import read

reading = read("photo.heic")
try:
    output.write(reading, "results")
    print(reading.pages[0].markdown)
finally:
    reading.close()
```

To keep the work, or to change it before the result is made, open a project:

```python
from optdoc import output
from optdoc.project import Project, load_config

project = Project.open("photo.heic")            # or config=load_config("results/photo.optdoc.json")
try:
    project.set_correction(0, project.text(0).replace("U/I", "U/l"))
    reading = project.build()
    try:
        output.write(reading, "results")        # the configuration is written with it
    finally:
        reading.close()
finally:
    project.close()
```

Errors are `optdoc.errors.OptdocError` with a `kind` and `details`; `optdoc.errors.describe_error(error, "de")`
words one in German, `"en"` in English.

## Planned

- The reading order of text areas, and layout models (PP-DocLayout, a handwriting detector) as an
  optional download, measured against the heuristics before they are offered.
- Apple Vision as a reader on macOS, including its document recognition with table cells (macOS 26 and later).
- Flattening curved pages (a book, a folded letter), finding the page in a photo more robustly, and
  turning an upside-down page in the automatic suggestion.
- Two independent readings of every number, so that a value is only trusted where both agree.
- A test bench of photographed documents with known content, to measure each step.

## Licence

GNU Affero General Public License 3.0 or later (see `LICENSE`); PyMuPDF, on which optdoc rests, is AGPL as well.
