# optdoc

optdoc makes photographed and scanned pages faithful. It finds the sheet in a photo and unwarps it to
how it looks from straight above, in its true proportions; it turns and straightens the page, cleans
dark scanner borders, evens out uneven light and grain, and keeps the page's own colours: a stamp stays
red, a signature blue. The result is a PDF of the prepared pages. Everything runs on your own computer;
nothing is sent anywhere (the command line refuses any attempt to reach the network).

It is one step of **docrepro**, a family of tools that reproduce photographed and scanned documents as
real digital documents, one tool for one step:

| tool | its step |
|---|---|
| **optdoc** | makes the page faithful: upright, unwarped, in its true proportions, evenly lit, in its own colours |
| [ocrdoc](https://github.com/fre-ms/ocrdoc) | recognises: areas, text, tables, barcodes; lays the text over the page |
| semdoc, tagdoc (planned) | understand the text (medical terms, identifying information) and describe the document |

What they share (configuration documents, the command line's manners, no network, the window's
building blocks) is [doccor](https://github.com/fre-ms/doccor)'s. [docs/family-design.md](docs/family-design.md)
describes the family and why it is divided so.

**Status: pre-alpha (0.7.0).** The code comes from PseudonyMed, with its history. Up to 0.6.0 optdoc
also read the pages (OCR, areas, tables, a searchable PDF); that is ocrdoc now, which came out of optdoc
with its history. optdoc 0.6.0 remains the one program that does both, until docrepro joins the tools.
`CHANGELOG.md` lists the changes.

## Every step can be reproduced and resumed

The configuration document (`<name>.optdoc.json`, also inside the PDF optdoc writes) holds every
setting and the plan of every page, marked as optdoc's suggestion or a person's decision, and nothing
else (no paths, no times). **The same file with the same document gives the same PDF, byte for byte.**
The window saves the document and opens it again where the person stopped.

Every page also has a **frame**: a fingerprint of where things lie on the prepared page (its size, and
the turning, unwarping and straightening that made it). ocrdoc, which reads optdoc's PDF, keeps what a
person decided there (areas drawn, a table's grid, corrected text) as long as the frame stays the same,
so a later change in optdoc that does not move the page (more contrast) costs no work in ocrdoc. An
original with both configuration documents gives every file of both steps again.

## What it does

- **Opens** PDFs and images (JPEG, PNG, TIFF, HEIC and more); an image is placed on a paper size (A4 by
  default, or its own size), honouring its EXIF orientation; a PDF page turned by `/Rotate` is set upright
  without touching its picture.
- **Prepares** pages without text of their own, with an automatic suggestion per page: perspective
  correction of a photographed sheet (finds its corners, also one outside the photo or on a light table,
  and gives the sheet its true proportions; tells a photographed page from a scanned one by the page
  itself, also inside a PDF of bound photos, and never cuts a page to the frame of a table), straightening,
  rotation by quarter turns, dark scanner borders, noise, contrast, sharpening, uneven light (per colour
  channel), areas erased. Every step can be switched and tuned.
- **Keeps colours** where the page has any (more than 0.3 % of it), stored as JPEG at quality 92 with full
  colour resolution, or losslessly as PNG when chosen (`--colour-pages png`, some ten times the size); a
  page without colour is stored in grey, losslessly. A born-digital page stays as it is, its text
  included.
- **Lets a person prepare it** in a window (extra `gui`, Qt): every page before and after, each step
  switchable, the sheet's corners to drag, areas to erase. The work can be saved and taken up again later.

Decisions in the preparation are measured, not guessed: binarising a page (Sauvola) looked good and made
RapidOCR nearly blind, so it is left to ocrdoc's filters, on its own copy; a scan tilted by as little as
half a degree lost the grid of its tables (0 to 36 of 108 rows cut right), so the suggestion straightens
from 0.3 degrees on (101 to 108 rows); neural unwarping (UVDoc) bent the tables of photographed laboratory
reports, while a sheet unwarped by its corners in its true proportions read as well as with the true
corners (1525 and 1522 of 1530 numbers on 30 invented photos). The tests guard the unwarping at a slant
and that a red stamp stays red.

## Install

Python 3.12 or later, with [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/fre-ms/optdoc
cd optdoc
uv sync --extra cleanup --extra gui
```

The `cleanup` extra brings OpenCV, NumPy, Pillow and HEIC support; the `gui` extra PySide6 (Qt, LGPL 3.0)
for the window. With [ocrdoc](https://github.com/fre-ms/ocrdoc) installed beside it, the window also tells
a page that stands on its head.

## Command line

```
optdoc about
optdoc run photo.heic --out results/
optdoc run scan.pdf --scan --out results/
optdoc edit photo.heic --out results/ --language en
optdoc edit photo.heic --out results/ --config results/photo.optdoc.json
```

`run` writes `<name>.pdf` and `<name>.optdoc.json` into the folder given and nowhere else. `edit` opens
the window; *Apply* writes the same two files, *Save and continue later* the configuration document
alone, *Cancel* nothing. `--config` (a `<name>.optdoc.json` or a PDF optdoc wrote) starts from a
configuration document instead of optdoc's suggestions. Every command answers with one JSON object on
standard output, so that programs in any language can use optdoc as a helper; a failure too, with a
fixed kind and its message in English and German, and exit status 2. No answer quotes a document or its
path. Options: `--paper a4|a5|a3|letter|legal|image`, `--photo` or `--scan` (instead of telling by each
page), `--no-clean-up`, `--colour-pages jpeg|png`, `--progress` (a line of JSON per page on standard
error).
[docs/interface.md](docs/interface.md) describes the answers, the kinds of error and the configuration
document.

## In Python

```python
from optdoc import output
from optdoc.project import Project, load_config

project = Project.open("photo.heic")            # or config=load_config("results/photo.optdoc.json")
try:
    plan = project.plan(0)
    plan.contrast = True
    project.set_plan(0, plan)
    prepared = project.build()
    try:
        output.write(prepared, "results")       # the configuration document is written with it
    finally:
        prepared.close()
finally:
    project.close()
```

Errors are `optdoc.errors.OptdocError` with a `kind` and `details`; `optdoc.errors.describe_error(error, "de")`
words one in German, `"en"` in English. `optdoc.cleanup.describe(plan, "de")` words a plan.

## Planned

- Flattening curved pages (a book, a folded letter), finding the page in a photo more robustly.
- Telling an upside-down page in the suggestion, by a small orientation model as an optional download
  (`optdoc models fetch`, the only command that goes on the network, on a person's request).

## Licence

GNU Affero General Public License 3.0 or later (see `LICENSE`); PyMuPDF, on which optdoc rests, is AGPL as well.
