# optdoc's command line as an interface

**Interface 3**, since optdoc 0.7.0 (this description: optdoc 0.8.0). This is what a program may
rely on when it calls optdoc, whatever language it is written in: a records app, a pseudonymiser,
a script, docrepro.

Every answer carries `interface`. It goes up when something a caller relies on changes in a way
that breaks it: a field or a kind of error removed or renamed, a meaning changed. Within one
interface, new fields, new options and new kinds of error may come; a caller ignores fields it
does not know and treats an unknown kind of error like any other (its message says what
happened). Releases are tagged; pin a tag, not a branch.

optdoc does one step of docrepro: it makes a photographed or scanned page **faithful**. Reading
the page is ocrdoc's step after it.

**From interface 2:** optdoc no longer reads: `readers`, `prepare` and `bench` are gone, and so are
the reading, the Markdown, the text layer and the options of the OCR engines and the areas
(`--reader`, `--languages`, `--no-tables`, `--no-structure`, `--no-cells`, `--no-areas`), with the
kinds of error `unknown-reader`, `no-reader`, `reader-failed`, `not-ocr` and `page-text`. New:
`about`, `run` (the preparation part of `prepare`), the configuration document version 2 with a
frame per page, and pages in their colours.

**Added within interface 3 (optdoc 0.8.0):** models as an optional download: the commands
`models list` and `models fetch`, the option `--models`, `models` in the answer of `about`, the
key `models` on a page of the configuration document, and the kinds of error `unknown-model`,
`model-unreachable` and `model-checksum`.

## Calling

```
optdoc about
optdoc run  <file> --out <folder> [options]
optdoc edit <file> --out <folder> [options] [--language de|en]
optdoc models list [--models <folder>]
optdoc models fetch <name> --to <folder> [--progress]
optdoc --version
```

Every command writes **exactly one JSON object to standard output**, whether it succeeds or not,
and ends with exit status **0** on success and **2** on failure. Standard error is free for
`--progress` (below) and the usage line of an invalid command line; nothing else reaches it, not
even what the libraries inside write there. No answer and no message ever quotes the content of a
document or a path given to optdoc, since a file name may name a patient.

Every answer has these two fields:

| field | example | meaning |
|---|---|---|
| `interface` | `3` | the version of this description |
| `made_with` | `"optdoc 0.8.0"` | the program and its version, for the record of what made a file |

## `about`: what this installation can do

```json
{"interface": 3, "made_with": "optdoc 0.8.0", "version": "0.8.0",
 "clean_up": true, "heic": true, "window": true, "upside_down": false,
 "models": [{"name": "page-orientation", "…": "…", "present": null}]}
```

`clean_up` says whether the steps of the preparation are there (OpenCV and NumPy, the extra
"cleanup"), `heic` whether HEIC and HEIF photos can be opened, `window` whether `edit` can open its
window (PySide6, the extra "gui"), `upside_down` whether ocrdoc is installed to tell an upside-down
page in the window by reading it, `models` the models optdoc can use (as `models list` gives
them, below).

## `run`: prepare a document

```
optdoc run <file> --out <folder> [--config <file.optdoc.json | file.pdf>]
    [--paper a4|a5|a3|letter|legal|image] [--photo | --scan] [--no-clean-up]
    [--colour-pages jpeg|png] [--models <folder>] [--progress]
```

`<file>` is a PDF or an image (JPEG, PNG, TIFF, BMP, GIF, WebP, PNM, HEIC, HEIF). optdoc never
changes it, and always starts from it, never from an earlier result. It writes two files into
`<folder>` (made when missing) and **nothing anywhere else**. Without `--out` the folder is
`<file>.optdoc` beside the file.

| file | what it is |
|---|---|
| `<stem>.pdf` | the document: every page upright, the pages a plan changed prepared, the configuration document inside |
| `<stem>.optdoc.json` | the configuration document (format `optdoc-config`, below): from it and the file, the same two files again |

With `--config`, optdoc starts from a configuration document instead of its suggestions: a
`<stem>.optdoc.json`, or a PDF optdoc wrote, which carries it. The document then decides every
setting; `--paper`, `--photo`, `--scan`, `--no-clean-up` and `--colour-pages` beside it are a
`usage` error. `--models` may stand beside it: it changes nothing of what the document decides.

The answer:

```json
{"interface": 3, "made_with": "optdoc 0.8.0",
 "pdf": "<folder>/<stem>.pdf", "config": "<folder>/<stem>.optdoc.json",
 "pages": 2, "cleaned_up": [1, 2], "unwarped": [1], "decided": []}
```

Pages are counted from 1. `cleaned_up` were changed by their plan (the others are as they came:
a born-digital page with its text, or a page whose plan does nothing), `unwarped` were found as a
photographed sheet and unwarped, `decided` are pages whose plan a person decided (in the window;
carried by the configuration document).

**The preparation.** A page without text of its own is prepared by the configuration document
given, else by optdoc's suggestion:

- **Photo or scan** is told by the page itself, in an image file and inside a PDF alike (photos
  bound into one PDF): a photo shows the sheet on something darker than paper (a desk, also a
  light grey table), and that sheet is found and unwarped to how it looks from straight above, in
  its true proportions (from the perspective of its corners; snapped to A4, A5, Letter or Legal
  when within 3 %). A corner may lie outside the photo; where a whole edge of the sheet does, it
  is reconstructed from the others, and what the photo did not show stays white. A frame or a
  ruled table has paper around it and is never taken for the sheet. `--photo` takes every page
  without text for a photo, `--scan` for a scan.
- **A tilt** from 0.3 degrees on is straightened (tables lose their grid in ocrdoc from a third of
  a degree on); dark scanner borders are cleaned, uneven light evened out, grain removed.
- **Colours stay.** The light is evened out per colour channel: the paper turns white, a red stamp
  stays red, a blue signature blue. A page with less than 0.3 % of colour is stored in grey (PNG,
  lossless); a page with colour as JPEG at quality 92 with full colour resolution, or losslessly
  as PNG with `--colour-pages png` (some ten times the size). TIFF is no choice: a PDF holds no
  TIFF, and one given to it is stored exactly as a PNG.
- **Orientation.** An image is turned as its EXIF orientation says; a PDF page turned by `/Rotate`
  is set upright without touching its picture (a JPEG stays byte for byte). The PDF has no turned
  pages, and its coordinates are those of the page as shown. A page that was scanned or
  photographed on its head or on its side says so nowhere: with the model `page-orientation` in
  the folder of `--models` (below), the suggestion sets such a page upright; without it the page
  stays as it came, and a person turns it in the window.

`--no-clean-up` leaves every page as it came, unless a person prepares it in the window.

**Progress.** With `--progress`, a line goes to standard error before each page:

```
{"page": 1, "of": 2}
{"page": 2, "of": 2}
```

**Network.** `about`, `run`, `edit` and `models list` never go on the network. The command line
refuses every attempt to resolve a name or open a connection before it does anything else (the
answer would be the error `network`). A caller on macOS may also run them under
`sandbox-exec -p "(version 1)(allow default)(deny network*)"`. The one command that goes out is
`models fetch`, on request, for one file from the address listed (below).

## `edit`: the window

```
optdoc edit <file> --out <folder> [--config <file.optdoc.json | file.pdf>] [--language de|en]
    [the settings of run] [--progress]
```

Opens a window on the file, in German or English (`--language`, else the system's language), and
asks to bring it to the front. It starts as `run` would (optdoc's suggestions, or the
configuration document given), so that **Apply** at once gives the same files as `run`. The page
before and after, every step switchable with its strength, rotation, the sheet's four corners
dragged on the page before (also where optdoc found none), areas erased by dragging on the page
after (Cmd/Ctrl+Z takes them back), "store in grey", the suggestion restored, a page left as it
came, the steps copied to every page, the orientation detected (upside down with the model
`page-orientation` in the folder of `--models`, or where ocrdoc is installed), and for the whole
document how pages in colour are stored (JPEG or PNG).

| the person chooses | written into `<folder>` | answer |
|---|---|---|
| **Apply** | both files, as `run` writes them | as `run`, and `"finished": true` |
| **Save and continue later** | the configuration document alone | `{"config": "<folder>/<stem>.optdoc.json", "finished": false}` |
| **Cancel**, or closing the window | nothing | the error `cancelled` (status 2) |

`edit <file> --config <folder>/<stem>.optdoc.json` goes on where the person stopped; so does
`--config <the PDF optdoc wrote>`. The window has no time limit and keeps no settings of its own.

## `models`: optional downloads

optdoc needs no model: every step works by its rules. A model is listed here only after it was
measured against the rules it adds to (`bench/orientation_bench.py`, on invented pages), and it
is never fetched unasked.

```
optdoc models list [--models <folder>]
optdoc models fetch <name> --to <folder> [--progress]
```

`models list` answers with the models optdoc can use:

```json
{"interface": 3, "made_with": "optdoc 0.8.0",
 "models": [{"name": "page-orientation", "file": "pp-lcnet-x1-0-doc-ori.onnx",
             "url": "https://huggingface.co/PaddlePaddle/PP-LCNet_x1_0_doc_ori_onnx/resolve/7330ab7039123e46af2dc03154b9969aa412c61d/inference.onnx",
             "sha256": "af9a0a4f317ff0709ce752067807f819cb15d883f8ecad89f28df1c6ee2d9c92",
             "bytes": 6788069, "licence": "Apache-2.0",
             "source": "https://huggingface.co/PaddlePaddle/PP-LCNet_x1_0_doc_ori_onnx",
             "does": {"en": "tells which way up a page stands, …", "de": "erkennt, wie herum …"},
             "present": true}]}
```

`url` is where the file comes from (https, a fixed revision), `sha256` and `bytes` what it must
be, `licence` the licence of the weights and `source` the page that states it. `present` says
whether the file lies in the folder of `--models` under the name `file` with that SHA-256 (`null`
without `--models`, as in `about`).

`models fetch <name> --to <folder>` is **the only command that goes on the network**: it fetches
that one file from `url`, never more bytes than listed, and keeps it only when size and SHA-256
are the ones listed (`model-checksum` otherwise, and nothing is kept). The request carries the
address and a client name ("doccor" and its version), nothing of a document or a person. The
answer: `{"model": "page-orientation", "file": "<folder>/pp-lcnet-x1-0-doc-ori.onnx", "bytes":
6788069, "sha256": "…", "licence": "Apache-2.0"}`. With `--progress`, lines `{"bytes": n, "of":
m}` go to standard error. A file that is already there and right is not fetched again. An
application may as well fetch the file itself from the listed address and put it into the folder
under the name `file`; a caller that runs optdoc without network runs this one command outside
that fence, or does the download itself.

`run` and `edit` take `--models <folder>` and use what lies there; a model that is missing, or a
file that is not the one listed, is done without, and is no error.

| model | size | what optdoc does with it |
|---|---|---|
| `page-orientation` | 6.8 MB | Sets a page upright that stands on its head or lies on its side, in the suggestion and in the window's "detect orientation". It answers only where it is sure and leaves a blank page as it is. On the bench (57 images of invented pages, each shown the four ways up: as made, worn scans, photos at a slant, coarse scans, pages with one to three lines) it named the turn of 223 of the 228, was unsure of the other five and left them, and turned none wrongly; the lines of the text alone tell portrait from landscape and are right for half the turns. PaddleOCR's PP-LCNet_x1_0_doc_ori, run by OpenCV. |

**What a model found is kept.** The turn becomes the page's plan, and the page's entry in the
configuration document names the model that took part (`"models": ["page-orientation"]`). Making
the result again from the document needs no model and no `--models`.

## The configuration document: `optdoc-config`, version 2

```json
{"format": "optdoc-config", "version": 2, "made_with": "optdoc 0.8.0",
 "input": {"sha256": "…", "bytes": 245678, "suffix": ".jpg",
           "pages": [{"width": 595.276, "height": 841.89}]},
 "options": {"paper": "a4", "photo": null, "clean_up": true, "colour_pages": "jpeg"},
 "pages": [{"page": 1,
            "plan": {"rotation": 0, "straighten": true, "angle": 2.1, "unwarp": true,
                     "corners": [[31.2, 40.5], "…"], "borders": false, "denoise": false,
                     "denoise_strength": 2, "contrast": false, "contrast_strength": 2,
                     "sharpen": false, "sharpen_strength": 2, "background": true,
                     "masks": [], "mask_colour": "white", "grey": true},
            "by": "auto", "frame": "b1419d68b65af0a8"}]}
```

Everything that decides the result, and nothing else: no paths, no times. `input` names the file
it belongs to by its SHA-256, and every page's size as it came; for another file the document is
refused (`config-mismatch`). `options` are the settings. Per page: its `plan` (`null` for a page
left as it came; a plan may do nothing and still keep the sheet's corners it found), who decided
it (`by`: "auto" as optdoc suggested it, "person" once a person changed it), and its `frame`.
Where a model took part in a suggested plan, the entry also has `models`, the names of those
models (`"models": ["page-orientation"]`); a plan a person decided names none.

**The frame** is a fingerprint of where things lie on the prepared page: its size, and what of the
plan moves the page (a quarter turn, the sheet's corners, the tilt straightened). Light, contrast,
colour and masks leave it as it is. ocrdoc reads optdoc's PDF and records the frames it found
there; when a person changes a page in optdoc later, ocrdoc keeps what the person decided there
(areas, a table's grid, corrected text) as long as the page's frame stays the same.

**The same file and the same document give the same two files, byte for byte**, on the same
version of optdoc: every page is prepared from its plan, and the PDF carries no time and a file
identifier made from the document. The tests check the bytes for `run`, `run --config` with the
document and with the PDF, and `edit`.

## Failures

```json
{"interface": 3, "made_with": "optdoc 0.8.0", "error": "unsupported",
 "details": {"suffix": ".docx"},
 "message": {"en": "optdoc cannot open files of type .docx.",
             "de": "Dateien vom Typ .docx kann optdoc nicht öffnen."}}
```

A caller decides by `error` and shows `message` in the language of its interface. `details` hold
what the message is made from, never a path or content.

| `error` | when | `details` |
|---|---|---|
| `missing` | the file (or the configuration document) does not exist | |
| `unsupported` | not a PDF or an image optdoc knows | `suffix` |
| `no-heic` | a HEIC or HEIF photo, and pillow-heif is not installed | |
| `unreadable` | the file cannot be read: damaged, empty, or not what its name says | |
| `encrypted` | the PDF needs a password | |
| `paper` | `--paper` names no paper size | `name` |
| `bad-config` | the document is no readable JSON, not of this version, has no entry for each page, or a value of the wrong kind | `reason`: `json`, `format`, `page`, `field` |
| `config-mismatch` | the document belongs to another file | |
| `same-as-source` | the PDF would overwrite the document itself | |
| `unwritable` | the folder cannot take the results | |
| `clean-up-failed` | a page could not be prepared | |
| `cancelled` | the person cancelled the window; nothing was written | |
| `no-gui` | `edit`, and PySide6 is not installed | |
| `network` | something tried to reach the network; it was stopped | |
| `unknown-model` | `models fetch` names a model optdoc does not list | `name` |
| `model-unreachable` | the model's address did not answer, or the download broke off | `name` |
| `model-checksum` | what came is not the file listed (size or SHA-256); nothing was kept | `name` |
| `usage` | the command line is not valid (the usage line goes to standard error) | |
| `internal` | a fault of optdoc | `error`: the name of the exception class |

The same kinds and wording are there for programs that use optdoc as a Python library:
`optdoc.errors.OptdocError` (`kind`, `details`) and `optdoc.errors.describe_error(error, "de")`.

## Licence

optdoc is free software under the GNU Affero General Public License 3.0 or later; its source is at
https://github.com/fre-ms/optdoc. A program that ships it names it and where its source is.
