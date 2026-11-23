# optdoc's command line as an interface

**Interface 2**, since optdoc 0.4.0. This is what a program may rely on when it calls optdoc,
whatever language it is written in: a records app that ships optdoc beside it (medorello, as a
Tauri sidecar), a pseudonymiser, a script.

Every answer carries `interface`. It goes up when something a caller relies on changes in a way
that breaks it: a field or a kind of error removed or renamed, a meaning changed. Within one
interface, new fields, new options and new kinds of error may come; a caller ignores fields it
does not know and treats an unknown kind of error like any other (its message says what
happened). Releases are tagged (`v0.4.0`); pin a tag, not a branch.

**From interface 1:** the configuration (`<stem>.optdoc.json`, `--config`, answer field `config`)
takes the place of the plan (`<stem>.plan.json`, `--plan`, answer field `plan`), and the kind of
error `bad-plan` is now `bad-config`. New: the window (`edit`), the answer field `corrected`,
`readers` field `window`, the word field `by` in the reading, the kinds of error
`config-mismatch`, `cancelled` and `no-gui`.

## Calling

```
optdoc readers
optdoc prepare <file> --out <folder> [options]
optdoc edit <file> --out <folder> [options] [--language de|en]
optdoc bench <folder> [--reader rapidocr|tesseract] [--no-clean-up]
optdoc --version
```

Every command writes **exactly one JSON object to standard output**, whether it succeeds or not,
and ends with exit status **0** on success and **2** on failure. Standard error is free for
`--progress` (below) and the usage line of an invalid command line; nothing else reaches it, not
even what the libraries inside write there (since 0.2.1). No answer and no message ever
quotes the content of a document or a path given to optdoc, since a file name may name a patient.

Every answer has these two fields:

| field | example | meaning |
|---|---|---|
| `interface` | `2` | the version of this description |
| `made_with` | `"optdoc 0.4.0"` | the program and its version, for the record of what made a file |

## `readers`: what this installation can do

```json
{"interface": 2, "made_with": "optdoc 0.4.0", "version": "0.4.0",
 "readers": ["rapidocr", "tesseract"], "clean_up": true, "heic": true, "tables": true,
 "window": true}
```

`readers` lists the OCR engines found, in order of preference (`rapidocr` comes inside the
standalone program; `tesseract` is listed where the system has it). `clean_up` says whether the
clean-up steps are there (OpenCV), `heic` whether HEIC and HEIF photos can be opened, `tables`
whether tables are found with their cells (Camelot, the extra "tables"), `window` whether
`edit` can open its window (PySide6, the extra "gui"). The engines are not loaded for this, so the
answer is quick (0.25 s for the standalone program as a folder, 3.7 s as one file, which unpacks
itself first).

## `prepare`: make a document legible

```
optdoc prepare <file> --out <folder> [--config <file.optdoc.json | file.pdf>]
    [--reader auto|rapidocr|tesseract|none] [--languages <packs>]
    [--paper a4|a5|a3|letter|legal|image] [--photo | --scan]
    [--no-clean-up] [--no-tables] [--no-structure] [--no-cells] [--progress]
```

`<file>` is a PDF or an image (JPEG, PNG, TIFF, BMP, GIF, WebP, PNM, HEIC, HEIF). optdoc never
changes it. It writes four files into `<folder>` (made when missing) and **nothing anywhere
else**: no copies, no caches, no images of pages in the temporary folder. (The standalone program
in one file unpacks its own libraries into the temporary folder at start and removes them at
exit; nothing of a document goes there.) Without `--out` the folder is `<file>.optdoc` beside the
file.

| file | what it is |
|---|---|
| `<stem>.pdf` | the document: cleaned-up pages, upright, with an invisible text layer on every page read by OCR, and the configuration inside |
| `<stem>.reading.json` | the reading (format `optdoc-reading`, below) |
| `<stem>.md` | the text as Markdown, a heading per page |
| `<stem>.optdoc.json` | the configuration (format `optdoc-config`, below): from it and the file, the same four files again |

With `--config`, optdoc starts from a configuration instead of its suggestions: a
`<stem>.optdoc.json`, or a PDF optdoc wrote, which carries its configuration. The configuration
then decides every setting; `--reader`, `--languages`, `--paper`, `--photo`, `--scan`,
`--no-clean-up`, `--no-tables` and `--no-structure` beside it are a `usage` error.

The answer:

```json
{"interface": 2, "made_with": "optdoc 0.4.0",
 "pdf": "<folder>/<stem>.pdf", "reading": "<folder>/<stem>.reading.json",
 "markdown": "<folder>/<stem>.md", "config": "<folder>/<stem>.optdoc.json",
 "pages": 2, "ocr_pages": [1, 2], "pages_without_text": [], "cleaned_up": [1, 2],
 "corrected": [], "reader": "rapidocr", "tables": 1}
```

Pages are counted from 1. `ocr_pages` were read by OCR (the others had a text layer of their own),
`pages_without_text` hold no text at all afterwards (no layer, no engine, or nothing legible),
`cleaned_up` were changed by the clean-up, `corrected` are pages whose text a person corrected
(in the window; carried by the configuration), `reader` is the engine used (`null` without one),
`tables` the number of tables found with their cells (`null` when they were not looked for:
`--no-cells`, or the extra "tables" is not installed, or Camelot failed).

**Tables.** The tables of every page, with their cells, go into the reading (below); a laboratory
result then is a row of cells (name, value, unit, range, flag) rather than a line to take apart.
optdoc finds them with Camelot in the PDF it has just written, on scanned and photographed pages
in its own text layer. Measured on invented laboratory reports in three layouts: of 216 results
in born-digital PDFs every row came out cut into the right cells and read exactly; of 216 in
photos, 211 cut right and 193 read exactly (the rest are misreadings such as "U/I" for "U/l").
`--no-cells` leaves them out (about 4 s less for the standalone program as one file, 0.7 s as a
folder).

**Photos and scans.** A page without text is cleaned up by the configuration given, else by
optdoc's suggestion. The suggestion tells a photographed page from a scanned one by the page
itself, in an image file and inside a PDF alike (photos bound into one PDF): a photo shows the
sheet on something darker than paper (a desk), and that sheet is found and unwarped. A frame or a
ruled table on a scan has paper around it and is never taken for the sheet. `--photo` takes every
page without text for a photo, `--scan` for a scan.

**Orientation.** An image is turned as its EXIF orientation says; a PDF page turned by `/Rotate`
is set upright without touching its picture (a JPEG stays byte for byte). The PDF that optdoc
writes has no turned pages, and its coordinates are those of the page as shown.

**Progress.** With `--progress`, a line goes to standard error before each page:

```
{"page": 1, "of": 2}
{"page": 2, "of": 2}
```

**Network.** optdoc never goes on the network; everything it needs travels with it. The command
line refuses every attempt to resolve a name or open a connection before it does anything else
(the answer would be the error `network`), and switches off the telemetry of ONNX Runtime, which
would otherwise queue facts about the computer for sending to Microsoft. A caller on macOS that
wants the system to make sure may run optdoc under
`sandbox-exec -p "(version 1)(allow default)(deny network*)"`; optdoc, its window included, works
the same there.

## `edit`: the window

```
optdoc edit <file> --out <folder> [--config <file.optdoc.json | file.pdf>] [--language de|en]
    [the settings of prepare] [--no-cells] [--progress]
```

Opens a window on the file, in German or English (`--language`, else the system's language),
and asks to bring it to the front. It starts as `prepare` would (optdoc's suggestions, or the configuration
given), so that **Apply** at once gives the same files as `prepare`. Two tabs:

- **Clean up:** the page before and after, every step switchable with its strength, rotation,
  areas erased by dragging (Cmd/Ctrl+Z takes them back), the suggestion restored, a page left as
  it came, the steps copied to every page, the orientation detected.
- **Check the text:** the page as OCR read it, words read with little confidence marked yellow, a
  click on a word selects it in the text; the text beside it, to be corrected by hand. A
  correction goes into the PDF's text layer, the reading (as words `"by": "person"`) and the
  Markdown; the words keep the boxes of the page.

The window closes in one of three ways:

| the person chooses | written into `<folder>` | answer |
|---|---|---|
| **Apply** | the four files, as `prepare` writes them | as `prepare`, and `"finished": true` |
| **Save and continue later** | the configuration alone: `<stem>.optdoc.json` | `{"config": "<folder>/<stem>.optdoc.json", "finished": false}` |
| **Cancel**, or closing the window | nothing | the error `cancelled` (status 2) |

`edit <file> --config <folder>/<stem>.optdoc.json` goes on where the person stopped; so does
`--config <the PDF optdoc wrote>`, to improve a result later. The window has no time limit; the
caller waits until it is closed. It keeps no settings of its own and writes nothing outside
`<folder>` (checked with empty home and temporary folders).

## The configuration: `optdoc-config`, version 1

```json
{"format": "optdoc-config", "version": 1, "made_with": "optdoc 0.4.0",
 "source": {"sha256": "…", "bytes": 245678, "suffix": ".jpg"},
 "options": {"reader": "auto", "languages": null, "tables": true, "paper": "a4", "photo": null,
             "clean_up": true, "structure": true, "dpi": 300},
 "reader": "rapidocr",
 "pages": [{"page": 1, "plan": {"rotation": 0, "straighten": true, "angle": 2.1, "…": "…"},
            "ocr": true, "words": [["Kalium", 56.2, 210.4, 89.9, 221.0, 0.998], "…"],
            "correction": null}]}
```

Everything that decides the result, and nothing else: no paths, no times. `source` names the file
it belongs to by its SHA-256; for another file it is refused (`config-mismatch`). `options` are
the settings. Per page: its clean-up `plan` (`null` for a page with a text layer; a plan may do
nothing and still keep the sheet's corners it found), whether it was read by `ocr` (`null`: not
read yet), the `words` OCR read (text, box in points, confidence), and the person's `correction`
of the page text (`null`: as read).

**The same file and the same configuration give the same four files, byte for byte**, on the
same version of optdoc: the pages are cleaned up from the plans, the text is made from the words
stored (OCR, which is not always deterministic, does not run again), and the PDF carries no time
and a file identifier made from the configuration. A page whose words are not stored yet (a
configuration saved before that page was read) is read when the result is made. The tests check
the bytes for `prepare`, `prepare --config` with the file and with the PDF, and `edit`.

## Failures

```json
{"interface": 2, "made_with": "optdoc 0.4.0", "error": "unsupported",
 "details": {"suffix": ".docx"},
 "message": {"en": "optdoc cannot open files of type .docx.",
             "de": "Dateien vom Typ .docx kann optdoc nicht öffnen."}}
```

A caller decides by `error` and shows `message` in the language of its interface. `details` hold
what the message is made from, never a path or content.

| `error` | when | `details` |
|---|---|---|
| `missing` | the file (or the configuration, or the bench folder) does not exist | |
| `unsupported` | not a PDF or an image optdoc knows | `suffix` |
| `no-heic` | a HEIC or HEIF photo, and pillow-heif is not installed | |
| `unreadable` | the file cannot be read: damaged, empty, or not what its name says | |
| `encrypted` | the PDF needs a password | |
| `paper` | `--paper` names no paper size | `name` |
| `unknown-reader` | an engine optdoc does not know | `name` |
| `no-reader` | the engine asked for is not installed | `reader` |
| `reader-failed` | the engine failed on a page | `reader` |
| `bad-config` | the configuration is no readable JSON, not of this version, has no entry for each page, or a value of the wrong kind | `reason`: `json`, `format`, `page`, `field` |
| `config-mismatch` | the configuration belongs to another file | |
| `same-as-source` | the PDF would overwrite the document itself | |
| `unwritable` | the folder cannot take the results | |
| `clean-up-failed` | a page could not be cleaned up | |
| `cancelled` | the person cancelled the window; nothing was written | |
| `no-gui` | `edit`, and PySide6 is not installed | |
| `network` | something tried to reach the network; it was stopped | |
| `usage` | the command line is not valid (the usage line goes to standard error) | |
| `internal` | a fault of optdoc | `error`: the name of the exception class |

The same kinds and wording are there for programs that use optdoc as a Python library:
`optdoc.errors.OptdocError` (`kind`, `details`) and `optdoc.errors.describe_error(error, "de")`.

## The reading: `optdoc-reading`, version 1

```json
{"format": "optdoc-reading", "version": 1, "made_with": "optdoc 0.4.0",
 "reader": "rapidocr", "source": "<file name>", "plan": {"1": {"…": "…"}},
 "pages": [{"page": 1, "width": 595.28, "height": 841.89, "source": "ocr",
            "text": "Kalium\t5,8\tmmol/l\t3,5 - 5,1\tH\n…", "markdown": "…",
            "words": [{"text": "Kalium", "start": 0, "end": 6,
                       "box": [56.2, 210.4, 89.9, 221.0], "confidence": 0.998, "by": "ocr"}],
            "tables": [{"box": [56.2, 150.1, 536.0, 451.3], "confidence": 0.863,
                        "rows": [[{"text": "Kalium", "box": [56.2, 208.4, 226.2, 224.4]},
                                  {"text": "5,8", "box": [226.2, 208.4, 296.2, 224.4]},
                                  "…"]]}]}]}
```

Per page: its size in points, where its text came from (`text` layer or `ocr`), the text, its
Markdown, and every word with its offsets in the text and its `box` as **[left, top, right,
bottom] in points from the top left of the page as shown**, the same page as in the PDF. OCR words
carry the engine's `confidence` (0 to 1) and `by`: `"ocr"`, or `"person"` for a word a person
wrote in the window (confidence 1). In the text, a line of the page is a line; on a page read by
OCR, a gap wider than the words are high (between the cells of a table, or columns) is a tab.
`plan` holds the plans of the pages that were cleaned up, as in the configuration.

`tables` lists the tables of the page, top to bottom, each with its `box`, Camelot's `confidence`
in it (0 to 1) and its `rows`, top to bottom, each a list of cells from left to right: `text`
(spaces collapsed; empty for an empty cell or one another cell spans) and `box`, in the same
points as the words. Every row is given once, even where Camelot found a table twice. `tables` is
`[]` when the page has none and `null` when tables were not looked for.

## The text layer

On every page read by OCR, the PDF carries the words invisibly where they are printed, one OCR
line as one line of text, with real spaces between the words. Within a cell of a table the space
is stretched over the gap; between two cells (a tab in the reading) the gap stays open, so that a
program finding tables by the gaps between text (Camelot, Tabula) sees the columns. PDFKit's
`PDFPage.string` (as medorello reads) gives every row of a table as one line, name, value, unit,
range and flag in order: measured on photographed invented laboratory reports in three layouts,
every row of every table. MuPDF gives running text as a line and a table row cell by cell, as it
does for a born-digital table; Poppler's `pdftotext` keeps rows with `-layout`. Each word is
scaled to its printed width, so a search or a selection covers it. Every character is written as
it was read, "≤", "↑" and "µ" included; a corrected text is laid on the same boxes. The tests
check this with PDFKit (on macOS) and MuPDF.

## Licence

optdoc is free software under the GNU Affero General Public License 3.0 or later; its source is at
https://github.com/fre-ms/optdoc. A program that ships it names it and where its source is.
