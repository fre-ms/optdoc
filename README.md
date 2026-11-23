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

**Status: pre-alpha (0.2.1).** The code comes from PseudonyMed, where it has been tested for weeks, with its
history. Since 0.1.0 its identifiers are English (`docs/renames-0.1.0.md` lists the old German names); since
0.2.0 its command line is a described interface ([docs/interface.md](docs/interface.md)) and it can be built
as a standalone program ([docs/sidecar.md](docs/sidecar.md)). `CHANGELOG.md` lists the changes.

## What it does today

- **Opens** PDFs and images (JPEG, PNG, TIFF, HEIC and more); an image is placed on a paper size (A4 by
  default, or its own size), honouring its EXIF orientation; a PDF page turned by `/Rotate` is set upright
  without touching its picture.
- **Cleans up** image-only pages, with an automatic suggestion per page: perspective correction of a
  photographed sheet (finds its corners; tells a photographed page from a scanned one by the page itself,
  also inside a PDF of bound photos, and never cuts a scan to the frame of a table), straightening, rotation by quarter turns, dark scanner borders,
  coloured ink (stamps, highlighter), noise, contrast, sharpening, uneven background, ruled and table lines,
  upscaling for low-resolution images, masks. Every step can be switched and tuned; the plan is written
  out so that the same result can be made again.
- **Reads** with [RapidOCR](https://github.com/RapidAI/RapidOCR) (ONNX models in the wheel, no download) or
  [Tesseract](https://github.com/tesseract-ocr/tesseract), with real word boxes and confidences. Tables with
  ruled grids, which Tesseract's page segmentation tends to drop, are read a second time without their lines.
- **Structures** the OCR text as Markdown: paragraphs re-joined, headings by size and weight, lists,
  tables from wide gaps.
- **Finds tables with their cells** (extra `tables`, Camelot), in born-digital PDFs and, through its own
  text layer, in scans and photos: a laboratory result comes out as a row of cells, name, value, unit,
  range, flag. On invented laboratory reports in three layouts every one of 216 rows in born-digital PDFs
  was cut and read right, and 211 of 216 in photos were cut right (193 read exactly).
- **Writes** a searchable PDF (the cleaned-up pages with the recognised words laid invisibly over the printed
  ones, line by line, so that selecting a word in a reader covers it and a program that takes the text out
  gets a row of a table as one line; every character as read, "≤" and "↑" too), the reading as JSON, the
  text as Markdown, and the clean-up plan.

Decisions in the clean-up are measured, not guessed: binarising a page (Sauvola) looked good and made
RapidOCR nearly blind, so optdoc does not do it; straightening a noisy scan by less than about one degree
costs more than it gains, so the suggestion leaves it alone. The tests guard both.

## Install

Python 3.12 or later, with [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/fre-ms/optdoc
cd optdoc
uv sync --extra ocr --extra tables
```

The `ocr` extra brings RapidOCR, ONNX Runtime, OpenCV and NumPy (for the clean-up steps) and HEIC support;
the `tables` extra brings [Camelot](https://github.com/camelot-dev/camelot), which finds tables with their
cells.
Tesseract is optional and installed separately (`brew install tesseract tesseract-lang`,
`apt install tesseract-ocr tesseract-ocr-deu`).

## Command line

```
optdoc readers
optdoc prepare photo.heic --out results/
optdoc prepare scan.pdf --reader tesseract --languages deu+eng --plan results/scan.plan.json
```

`prepare` writes `<name>.pdf`, `<name>.reading.json`, `<name>.md` and `<name>.plan.json` into the folder
given and nowhere else. Every command answers with one JSON object on standard output, so that programs in
any language can use optdoc as a helper; a failure too, with a fixed kind and its message in English and
German, and exit status 2. No answer quotes a document or its path. Options: `--reader
auto|rapidocr|tesseract|none`, `--languages`, `--paper a4|a5|a3|letter|legal|image`, `--plan`, `--photo` or
`--scan` (instead of telling by each page), `--no-clean-up`, `--no-tables`, `--no-structure`, `--no-cells`
(no tables with their cells), `--progress` (a line of JSON per page on standard error). [docs/interface.md](docs/interface.md) describes the answers,
the kinds of error and the reading.

Settings without a configuration file: `OPTDOC_OCR` (the engine `auto` stands for), `OPTDOC_TESSERACT`
(the program's path), `OPTDOC_TESSERACT_LANGUAGES`. An application that embeds optdoc hands over its own
with `optdoc.settings.set_settings`.

## Standalone program

`uv run python packaging/build.py` builds optdoc as one program with everything in it (Python, the OCR
models, Camelot and all), named the way Tauri wants a sidecar (`optdoc-aarch64-apple-darwin`), and tries it
out: 142 MB as one file, or a faster-starting folder with `--onedir`. See [docs/sidecar.md](docs/sidecar.md).

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
tables with their cells. It also names the engine, the optdoc version and the plan.

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

Errors are `optdoc.errors.OptdocError` with a `kind` and `details`; `optdoc.errors.describe_error(error, "de")`
words one in German, `"en"` in English.

## Planned

- Apple Vision as a reader on macOS, including its document recognition with table cells (macOS 26 and later).
- Flattening curved pages (a book, a folded letter), finding the page in a photo more robustly, and
  turning an upside-down page in the automatic suggestion.
- Two independent readings of every number, so that a value is only trusted where both agree.
- A window to correct the clean-up and the reading by hand.
- A test bench of photographed documents with known content, to measure each step.

## Licence

GNU Affero General Public License 3.0 or later (see `LICENSE`); PyMuPDF, on which optdoc rests, is AGPL as well.
