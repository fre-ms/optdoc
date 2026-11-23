# optdoc's command line as an interface

**Interface 1**, since optdoc 0.2.0. This is what a program may rely on when it calls optdoc,
whatever language it is written in: a records app that ships optdoc beside it (medorello, as a
Tauri sidecar), a pseudonymiser, a script.

Every answer carries `interface`. It goes up when something a caller relies on changes in a way
that breaks it: a field or a kind of error removed or renamed, a meaning changed. Within one
interface, new fields, new options and new kinds of error may come; a caller ignores fields it
does not know and treats an unknown kind of error like any other (its message says what
happened). Releases are tagged (`v0.2.0`); pin a tag, not a branch.

## Calling

```
optdoc readers
optdoc prepare <file> --out <folder> [options]
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
| `interface` | `1` | the version of this description |
| `made_with` | `"optdoc 0.2.0"` | the program and its version, for the record of what made a file |

## `readers`: what this installation can do

```json
{"interface": 1, "made_with": "optdoc 0.2.0", "version": "0.2.0",
 "readers": ["rapidocr", "tesseract"], "clean_up": true, "heic": true}
```

`readers` lists the OCR engines found, in order of preference (`rapidocr` comes inside the
standalone program; `tesseract` is listed where the system has it). `clean_up` says whether the
clean-up steps are there (OpenCV), `heic` whether HEIC and HEIF photos can be opened. The
engines are not loaded for this, so the answer is quick (0.2 s for the standalone program as a
folder, 2.6 s as one file, which unpacks itself first).

## `prepare`: make a document legible

```
optdoc prepare <file> --out <folder> [--reader auto|rapidocr|tesseract|none]
    [--languages <packs>] [--paper a4|a5|a3|letter|legal|image] [--plan <plan.json>]
    [--photo | --scan] [--no-clean-up] [--no-tables] [--no-structure] [--progress]
```

`<file>` is a PDF or an image (JPEG, PNG, TIFF, BMP, GIF, WebP, PNM, HEIC, HEIF). optdoc never
changes it. It writes four files into `<folder>` (made when missing) and **nothing anywhere
else**: no copies, no caches, no images of pages in the temporary folder. (The standalone program
in one file unpacks its own libraries into the temporary folder at start and removes them at
exit; nothing of a document goes there.) Without `--out` the folder is `<file>.optdoc` beside the
file.

| file | what it is |
|---|---|
| `<stem>.pdf` | the document: cleaned-up pages, upright, with an invisible text layer on every page read by OCR |
| `<stem>.reading.json` | the reading (format `optdoc-reading`, below) |
| `<stem>.md` | the text as Markdown, a heading per page |
| `<stem>.plan.json` | the clean-up of each page, to make the same again with `--plan` |

The answer:

```json
{"interface": 1, "made_with": "optdoc 0.2.0",
 "pdf": "<folder>/<stem>.pdf", "reading": "<folder>/<stem>.reading.json",
 "markdown": "<folder>/<stem>.md", "plan": "<folder>/<stem>.plan.json",
 "pages": 2, "ocr_pages": [1, 2], "pages_without_text": [], "cleaned_up": [1, 2],
 "reader": "rapidocr"}
```

Pages are counted from 1. `ocr_pages` were read by OCR (the others had a text layer of their own),
`pages_without_text` hold no text at all afterwards (no layer, no engine, or nothing legible),
`cleaned_up` were changed by the clean-up, `reader` is the engine used (`null` without one).

**Photos and scans.** A page without text is cleaned up by the plan given, else by optdoc's
suggestion. The suggestion tells a photographed page from a scanned one by the page itself, in an
image file and inside a PDF alike (photos bound into one PDF): a photo shows the sheet on
something darker than paper (a desk), and that sheet is found and unwarped. A frame or a ruled
table on a scan has paper around it and is never taken for the sheet. `--photo` takes every page
without text for a photo, `--scan` for a scan.

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
`sandbox-exec -p "(version 1)(allow default)(deny network*)"`; optdoc works the same there.

## Failures

```json
{"interface": 1, "made_with": "optdoc 0.2.0", "error": "unsupported",
 "details": {"suffix": ".docx"},
 "message": {"en": "optdoc cannot open files of type .docx.",
             "de": "Dateien vom Typ .docx kann optdoc nicht öffnen."}}
```

A caller decides by `error` and shows `message` in the language of its interface. `details` hold
what the message is made from, never a path or content.

| `error` | when | `details` |
|---|---|---|
| `missing` | the file (or the plan, or the bench folder) does not exist | |
| `unsupported` | not a PDF or an image optdoc knows | `suffix` |
| `no-heic` | a HEIC or HEIF photo, and pillow-heif is not installed | |
| `unreadable` | the file cannot be read: damaged, empty, or not what its name says | |
| `encrypted` | the PDF needs a password | |
| `paper` | `--paper` names no paper size | `name` |
| `unknown-reader` | an engine optdoc does not know | `name` |
| `no-reader` | the engine asked for is not installed | `reader` |
| `reader-failed` | the engine failed on a page | `reader` |
| `bad-plan` | the plan is no JSON object keyed by page, names a page the document lacks, or has a value of the wrong kind | `reason`: `json`, `page`, `field` |
| `same-as-source` | the PDF would overwrite the document itself | |
| `unwritable` | the folder cannot take the results | |
| `clean-up-failed` | a page could not be cleaned up | |
| `network` | something tried to reach the network; it was stopped | |
| `usage` | the command line is not valid (the usage line goes to standard error) | |
| `internal` | a fault of optdoc | `error`: the name of the exception class |

The same kinds and wording are there for programs that use optdoc as a Python library:
`optdoc.errors.OptdocError` (`kind`, `details`) and `optdoc.errors.describe_error(error, "de")`.

## The reading: `optdoc-reading`, version 1

```json
{"format": "optdoc-reading", "version": 1, "made_with": "optdoc 0.2.0",
 "reader": "rapidocr", "source": "<file name>", "plan": {"1": {"…": "…"}},
 "pages": [{"page": 1, "width": 595.28, "height": 841.89, "source": "ocr",
            "text": "Kalium 5,8 mmol/l 3,5 - 5,1 H\n…", "markdown": "…",
            "words": [{"text": "Kalium", "start": 0, "end": 6,
                       "box": [56.2, 210.4, 89.9, 221.0], "confidence": 0.998}]}]}
```

Per page: its size in points, where its text came from (`text` layer or `ocr`), the text, its
Markdown, and every word with its offsets in the text and its `box` as **[left, top, right,
bottom] in points from the top left of the page as shown**, the same page as in the PDF. OCR words
carry the engine's `confidence` (0 to 1). In the text, a line of the page is a line; a gap far
wider than a space (a table cell) is a tab. `plan` is the content of `<stem>.plan.json`.

## The text layer

On every page read by OCR, the PDF carries the words invisibly where they are printed, one OCR
line as one line of text: the words of a row of a table stand in one line, with real spaces
between them, in the order of the row. So a program that takes the text out finds name, value,
unit, range and flag of a laboratory result in one line: measured with PDFKit's
`PDFPage.string` (as medorello reads) and MuPDF on photographed invented laboratory reports in
three layouts, every row of every table; Poppler's `pdftotext` keeps rows with `-layout`
(without it, it orders a table by columns, a born-digital one as well). Each word is scaled to
its printed width, so a search or a selection covers it. Every character is written as it was
read, "≤", "↑" and "µ" included. The tests check rows with PDFKit (on macOS) and MuPDF.

## Licence

optdoc is free software under the GNU Affero General Public License 3.0 or later; its source is at
https://github.com/fre-ms/optdoc. A program that ships it names it and where its source is.
