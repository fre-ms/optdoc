# optdoc

optdoc makes photographed and scanned documents legible. It finds and straightens the page, evens out
light and noise, reads the text with word boxes, gives it structure (paragraphs, lists, tables) and lays it
back onto the page as an invisible text layer. The result is a searchable PDF and a machine-readable
reading that other programs can build on. Everything runs on your own computer; nothing is sent anywhere.

It is the document layer of two applications by the same author: [PseudonyMed](https://github.com/fre-ms/PseudonyMed),
which pseudonymises patient documents, and medorello, a records app that files documents and reads
values from them, such as the results printed on a photographed laboratory report. optdoc itself knows
nothing about either and works on any kind of document.

**Status: pre-alpha (0.0.1).** The code comes from PseudonyMed, where it has been tested for weeks, with its
history. Its identifiers are still German; they will become English before 0.1.0, together with the items
under *Planned*. Expect the interface to change until then.

## What it does today

- **Opens** PDFs and images (JPEG, PNG, TIFF, HEIC and more); an image is placed on a paper size (A4 by
  default, or its own size), honouring its EXIF orientation.
- **Cleans up** image-only pages, with an automatic suggestion per page: perspective correction of a
  photographed sheet (finds its corners), straightening, rotation by quarter turns, dark scanner borders,
  coloured ink (stamps, highlighter), noise, contrast, sharpening, uneven background, ruled and table lines,
  upscaling for low-resolution images, masks. Every step can be switched and tuned; the plan is written
  out so that the same result can be made again.
- **Reads** with [RapidOCR](https://github.com/RapidAI/RapidOCR) (ONNX models in the wheel, no download) or
  [Tesseract](https://github.com/tesseract-ocr/tesseract), with real word boxes and confidences. Tables with
  ruled grids, which Tesseract's page segmentation tends to drop, are read a second time without their lines.
- **Structures** the OCR text as Markdown: paragraphs re-joined, headings by size and weight, lists,
  tables from wide gaps.
- **Writes** a searchable PDF (the cleaned-up pages with the recognised words laid invisibly over the printed
  ones, so that selecting a word in a reader covers it), the reading as JSON, the text as Markdown, and the
  clean-up plan.

Decisions in the clean-up are measured, not guessed: binarising a page (Sauvola) looked good and made
RapidOCR nearly blind, so optdoc does not do it; straightening a noisy scan by less than about one degree
costs more than it gains, so the suggestion leaves it alone. The tests guard both.

## Install

Python 3.12 or later, with [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/fre-ms/optdoc
cd optdoc
uv sync --extra ocr
```

The `ocr` extra brings RapidOCR, ONNX Runtime, OpenCV and NumPy (for the clean-up steps) and HEIC support.
Tesseract is optional and installed separately (`brew install tesseract tesseract-lang`,
`apt install tesseract-ocr tesseract-ocr-deu`).

## Command line

```
optdoc readers
optdoc prepare photo.heic --out results/
optdoc prepare scan.pdf --reader tesseract --languages deu+eng --plan results/scan.plan.json
```

`prepare` writes `<name>.pdf`, `<name>.reading.json`, `<name>.md` and `<name>.plan.json` and answers in
JSON on standard output, so that programs in any language can use optdoc as a helper. Errors go to standard
error, end with exit status 2 and never quote the document. Options: `--reader auto|rapidocr|tesseract|none`,
`--languages`, `--paper a4|a5|a3|letter|legal|image`, `--plan`, `--no-clean-up`, `--no-tables`,
`--no-structure`.

Settings without a configuration file: `OPTDOC_OCR` (the engine `auto` stands for), `OPTDOC_TESSERACT`
(the program's path), `OPTDOC_TESSERACT_LANGUAGES`. An application that embeds optdoc hands over its own
with `optdoc.einstellungen.setze_einstellungen`.

## The reading

`<name>.reading.json` (format `optdoc-reading`, version 1) holds, per page, its size in points, where the text
came from (`text` layer or `ocr`), the text, its Markdown, and every word with its offsets in the text, its box
in page points and, for OCR, the engine's confidence. It also names the engine, the optdoc version and the plan.

## In Python

```python
from optdoc.lesen import lies
from optdoc import ausgabe

lesung = lies("photo.heic")
try:
    ausgabe.schreibe(lesung, "results")
    print(lesung.seiten[0].markdown)
finally:
    lesung.schliessen()
```

## Planned

- English identifiers throughout (0.1.0).
- Apple Vision as a reader on macOS, including its document recognition with table cells (macOS 26 and later).
- Flattening curved pages (a book, a folded letter) and finding the page in a photo more robustly.
- Two independent readings of every number, so that a value is only trusted where both agree.
- A window to correct the clean-up and the reading by hand.
- A test bench of photographed documents with known content, to measure each step.

## Licence

GNU Affero General Public License 3.0 or later (see `LICENSE`); PyMuPDF, on which optdoc rests, is AGPL as well.
