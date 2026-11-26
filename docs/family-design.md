# The docrepro family: one tool for one step

Status: design, 26 November 2026, with the user's decisions of the same day (at the end).
optdoc 0.6.0 is the last release that does everything in one. Stage 1 (doccor 0.1.0) is
released; stage 2 (ocrdoc 0.1.0, optdoc 0.7.0 trimmed to the preparation) is built, and the
chain checked: an invented photo through optdoc and ocrdoc gives every file again from the
original and the two configuration documents, byte for byte; a change in optdoc that keeps
a page's frame keeps a person's corrections and areas in ocrdoc, one that moves the page
drops them and says so.

**docrepro** reproduces photographed and scanned documents as digital documents. (Named so
on 26 November 2026 instead of the working name reprodoc, which read in German medicine like a
doctor of reproductive medicine; `docs/name-search-docrepro-2026-11-26.md`.)

## Why

optdoc has grown into a tool that does everything: it prepares a photographed or scanned
page, reads it, divides it into areas, finds tables, barcodes and stamps, and writes a
searchable PDF. Two of its aims work against each other. To prepare a page for OCR, it
turns photographs grey and erases coloured ink (stamps, blue signatures, highlighting);
the PDF a records app files as the next version of a report then lacks its stamp and its
colour. A reproduction of the document has to keep them.

So the work is divided by the Unix principle, one tool for one step, each usable on its
own and together, each replaceable by another program:

| tool | its one step | takes | gives |
|---|---|---|---|
| **optdoc** | make the page faithful: upright, unwarped, in its true proportions, evenly lit, in its own colours | a photo, a scan, any PDF | a PDF of the prepared pages |
| **ocrdoc** | recognise: areas, text, tables, barcodes | any PDF (optdoc's, or another program's) | the same pages with a text layer, the reading, Markdown |
| **semdoc** | understand: medical terms and identifying information, with their codes (through lexterm and lexident) | a reading | the annotations |
| **tagdoc** | describe: what the document is (title, kind, date, authors, the people it names) | ocrdoc's PDF (and semdoc's annotations, once there) | its metadata as medRDS says (XMP and the information dictionary in the PDF, or a sidecar) |
| **docrepro** | the whole way, in one window and one program | a photo or a scan | a real digital document |

A small shared core, **doccor** (as lexcor is for lexterm and lexident), holds what every
tool needs, so that nothing is written twice.

## Every step can be reproduced and resumed

The requirement from the start: **an input file and the configuration document of a step
give that step's result again, byte for byte**, and the configuration document lets a
person stop at any point and go on later. Every tool keeps to the same contract, which the
core implements once.

### The configuration document

Each tool writes one per input: `<stem>.optdoc.json`, `<stem>.ocrdoc.json`,
`<stem>.semdoc.json`, `<stem>.tagdoc.json`, and docrepro `<stem>.docrepro.json` for the
whole way. It is JSON (UTF-8, the same bytes for the same content), and its name says so;
the part before `.json` names the tool.

```json
{"format": "ocrdoc-config", "version": 1, "made_with": "ocrdoc 0.1.0",
 "input": {"sha256": "…", "bytes": 245678, "suffix": ".pdf",
           "pages": [{"width": 595.28, "height": 841.89, "frame": "…"}]},
 "options": {"…": "…"},
 "pages": [{"page": 1, "…": "what was found, what a person decided"}]}
```

- **`input`** names the file the step worked on by its SHA-256 and gives every page's
  size and frame (a fingerprint of where things lie on it; below). Another file is refused
  ("config-mismatch"), unless only its looks changed (below).
- **`options`**: every setting that decides the result.
- **`pages`**: per page, everything the step decided, and the results of everything that
  is not deterministic, stored so that it never runs again for a reproduction: the words
  an OCR engine read, the areas a finder found, what a model said. A person's decisions
  are marked as theirs (`"by": "person"`), so that what a machine proposed and what a
  person checked stay apart.
- **Nothing else**: no paths, no times, no user, no machine. Numbers are stored rounded,
  and the result is always made from the stored, rounded values, live or reproduced.
- A page not done yet has `null` where its results would be: the document can be saved at
  any moment, and the step goes on from there (`<tool> edit <input> --config <doc>`).

### The output carries the way it was made

Every PDF a tool writes carries the configuration documents of all the steps that made
it, as embedded files (`optdoc.json`, `ocrdoc.json`, …): ocrdoc copies optdoc's from its
input and adds its own. A finished document therefore says how it was made, and with the
original it is made again. The PDF has no time in it and a file identifier made from its
configuration documents, so that the same documents give the same bytes. A records app
may add its own metadata as an incremental update; the embedded documents stay readable.

### The chain

A step's input is the output of the step before (or any file a person brings). Since that
output is reproducible to the byte, the chain is: the original and the configuration
documents give the final document again. `<stem>.docrepro.json` holds the way as a whole: the
original's SHA-256 and every step's document, so that `docrepro run <original> --config
<stem>.docrepro.json` makes everything again and `docrepro edit` goes on where the person
stopped.

**When a person changes an earlier step** (more contrast in optdoc), the later steps'
inputs change and their documents no longer fit by hash. They are not thrown away: a
step's document also records every page's **frame**, a fingerprint of the page's geometry
(its size, and the turning, unwarping and straightening that made it). Where the frame of
a page is unchanged, what a person decided on it stays (areas they drew, a table grid they
set, text they corrected), and what a machine found is found again (OCR reads the page
anew). Where the frame changed, the page's decisions no longer fit and go, and the answer
says which (`dropped`). This rule is the same in every tool and in the window.

### What "the same" means

The guarantee holds for the same version of a tool (`made_with`). A new version may make a
different result from the same document (a better unwarping, a better table finder); the
document still opens and goes on, and the step's result changes once, deliberately.

## What goes where

From today's optdoc (modules in parentheses):

**optdoc** keeps the preparation of the page: opening PDFs and images, EXIF and `/Rotate`
upright, paper sizes (`loading`); the sheet's corners, true proportions, quarter turns,
straightening, dark borders, even lighting, noise, contrast, sharpening, areas erased
(`cleanup`), its suggestion, the clean-up tab of the window. Two changes:

- **Its output keeps the page's colours**: evening out the light works per colour channel,
  and nothing erases coloured ink. A stamp stays in the document.
- **Upside down** is told without an OCR engine: by the lines as today for a quarter turn,
  and for half a turn either by a small orientation model (an optional download, below) or
  by asking ocrdoc where it is installed (a provider, not a dependency).

**ocrdoc** takes the recognition: the engines (`ocr`), page text with a box for every
character (`pagetext`), the text layer (`textlayer`), corrections (`alignment`), structure
and Markdown (`structure`), areas and table grids (`layout`), barcodes, pictures, stamps and
handwriting (`areas`), tables (`tables`), the reading, the bench of laboratory reports
(`bench`), the areas and text tabs of the window. The steps that only help OCR move here
and work on ocrdoc's own copy of each page, never on the document: upscaling, letter mode,
taking coloured ink away, ruled lines away, black and white, Tesseract's second pass over
ruled tables. ocrdoc lays its text layer over the input's pages and leaves their pictures
as they are.

**semdoc** finds medical terms (lexterm) and identifying information (lexident) in a
reading, with their spans and boxes and codes, for a person to confirm (`<stem>.semdoc`
holds the proposals and the decisions). It waits for lexterm and lexident to be libraries.

**tagdoc** suggests what a document is (title, kind, clinical date, language; from its text,
later from semdoc's annotations), a person confirms or completes it (authors, institution,
the people it names, with copies of their cards from an address book), and tagdoc writes it
as medRDS chapter 7 says: XMP with the information dictionary in step, or a sidecar for a PDF
signed by someone else. The standard keeps its vocabulary and its reference library (in
JavaScript, which medorello and medonomina use to file); tagdoc writes the same packet in
Python, character by character, and its tests let the reference library read it back. What
belongs to filing (the record, the versions, who filed it, where it came from) stays the
records app's.

**The core, doccor,** holds what all tools share: the configuration document (head, SHA-256, frame,
rounding, embedding in a PDF, the deterministic file identifier), the command line's
manners (exactly one JSON answer, kinds of error with messages in English and German,
progress lines), the network lock and ONNX Runtime's telemetry switched off, settings, and
the window's building blocks (page view, background work, words in two languages, the
frame with Apply, Save and continue later, Cancel).

**docrepro** joins them: the chain and its document, `docrepro run` and `docrepro edit`,
one window whose tabs come from the tools installed (a tool that is missing leaves its tab
out), and the standalone program: one Python with every tool inside, called as
`docrepro optdoc …`, `docrepro ocrdoc …` or as a whole, so that a records app ships one
program, not four of 160 MB each.

**semdoc and tagdoc** have their places in docrepro from the start (orders 30 and 40, what
they take and give, their formats). A step joins the chain by being installed: docrepro
brings the adapters of optdoc and ocrdoc, and any other step brings its own through the
entry-point group `docrepro.steps` (tagdoc does) (an adapter opens the step's project on its input, gives
its configuration document, writes its result and names the pages whose decisions went).
A chain document that names a step which is not installed is refused (`step-missing`).

## The command lines

Every tool alike:

```
<tool> run  <input> --out <folder> [--config <doc>] [settings] [--progress]
<tool> edit <input> --out <folder> [--config <doc>] [settings] [--language de|en]
<tool> about
```

`run` makes the result (today's `prepare`), `edit` opens the tool's window (Apply writes
the result, Save and continue later the configuration document alone, Cancel nothing),
`about` says what the installation can do (today's `readers`). Everything else as optdoc
does it today: one JSON answer, status 0 or 2, nothing outside `--out`, never the network,
no path or content in any message. `--config` takes the configuration document or a PDF
the tool wrote. docrepro adds `docrepro run|edit <original>` for the whole way.

## Models as an optional download

Some steps become better with a model (finding areas: PP-DocLayout; handwriting; turning a
page upright). Models are planned in from the start and never fetched while a document is
being worked on:

- A tool lists the models it can use, each with its address, SHA-256, size and licence,
  in its own code (`<tool> about`).
- **One command goes on the network**, and only on a person's request:
  `<tool> models fetch <name> --to <folder>`; it checks the SHA-256 before it keeps a file.
  A records app may fetch the file itself from the same list.
- `run` and `edit` take `--models <folder>` and stay without network; a model that is
  missing is no error, the step works as without it.
- What a model found is stored in the configuration document like OCR's words, so that a
  reproduction needs the model no more.

**Built (stage 4, 26 November 2026):** the mechanism is doccor's (0.2.0: the catalogue,
`fetch`, the door in the network lock that opens for that download alone, the commands), the
same in optdoc, ocrdoc and docrepro, which lists the models of every step and hands every
step the folder. **A model is listed only after it did better than the rules it adds to**,
on a bench that is in the repository and runs on invented pages:

- **Orientation: listed** (optdoc 0.8.0, `page-orientation`: PaddleOCR's
  PP-LCNet_x1_0_doc_ori, Apache-2.0, 6.8 MB, run by OpenCV). It named the turn in 223 of 228
  cases (57 images of invented pages, each shown the four ways up: worn scans, photos at a
  slant, coarse scans, pages with one to three lines), was unsure in the other five and left
  the page, and turned none wrongly, in 0.009 s a page; the lines of the text alone are
  right for half the turns, and reading the page both ways takes 2 s
  (`bench/orientation_bench.py`).
- **Areas: not listed.** PP-DocLayout_plus-L (Apache-2.0, 130 MB) found 6 to 9 of 12 pictures
  on ocrdoc's invented letters, with many areas where none was drawn, and none of the 6
  stamps; the rules found 11 to 12 (ocrdoc's `bench/areas_bench.py`). Invented letters are
  not what it was trained on: the fair test is on real documents, which only their owner
  can run, on their own computer, with figures alone leaving it.
- **Handwriting: not tried.** The one detector found (hwdet) is a single person's
  repository some days old, with weights under the AGPL and, by its own account, 71 % of
  handwritten pages found; not a download to offer.

## Formats

| format | from | replaces |
|---|---|---|
| `optdoc-config` version 2 | optdoc | version 1, without the steps that move to ocrdoc |
| `ocrdoc-config` version 1 | ocrdoc | the OCR part of `optdoc-config` 1 |
| `ocrdoc-reading` version 1 | ocrdoc | `optdoc-reading` 1, without the clean-up plan and the input's file name (named by its SHA-256 instead) |
| `semdoc-annotations` version 1 | semdoc | — |
| `tagdoc-config` version 1 | tagdoc | — |
| `docrepro-chain` version 1 | docrepro | — |

The old formats go when the new ones come (no compatibility layer); optdoc 0.6.0 stays
available for whoever has not moved yet.

## Repositories

- **optdoc** keeps its repository and history, trimmed to the preparation.
- **ocrdoc** comes out of optdoc with the history of its modules (`git filter-repo`), as
  optdoc came out of PseudonyMed.
- **doccor** and **docrepro** are new repositories; doccor's code moves out of optdoc.
- **tagdoc** is a new repository (26 November 2026); **semdoc** follows later.

All AGPL-3.0, the core too: code that two applications share is application code (the
user's rule; MIT is for what a program takes from a standard).

## Order of work

Each stage is released and tested before the next; each keeps the chain reproducible.

1. **doccor**, out of optdoc; optdoc depends on it; nothing else changes.
2. **ocrdoc**, out of optdoc: the recognition moves, optdoc's output keeps its colours,
   the configuration documents `.optdoc.json` and `.ocrdoc.json`, the frame rule, `run`,
   `edit`, `about`. The tests check that original + `.optdoc.json` + `.ocrdoc.json` give the same files.
3. **docrepro**: the chain document, the joined window, the one program; a handoff to
   medorello (from `optdoc edit` to `docrepro edit`) and to PseudonyMed (imports from
   ocrdoc and optdoc, the window's panels).
4. **Models** as an optional download (areas, handwriting, orientation), each measured
   against the rules it would replace (built 26 November 2026; one model listed, above).
5. **tagdoc** (built 26 November 2026, before the standalone program, at the user's request);
   **semdoc**, once lexterm and lexident are libraries. As of 26 November 2026 they are not:
   both hold design, reports and benches; the code is lexcor's (0.1: the tagger, the
   packages, the store), which gets its annotation document and its window for a person's
   review with 0.2. semdoc waits for that (the user, 26 November 2026); its place in
   docrepro (step 30, the entry point, the test with a stand-in) is kept.

## Decided (the user, 26 November 2026)

- The names of the tools stay as they are: optdoc, ocrdoc, semdoc, tagdoc; the core is
  **doccor** (its .org domain is free). A first check found no live mark against any of
  them (DPMAregister: DE, EU and international marks with German effect; TMview and the US
  register not yet); semdoc shares its name with projects in other fields.
- The whole application is **docrepro** (the user, later the same day, after reprodoc,
  facsimdoc and facsim): every domain free, no mark in the DPMAregister, TMview or the US
  register (`docs/name-search-docrepro-2026-11-26.md`).
- The configuration documents are named `<stem>.<tool>.json` ("clearer, more honest").
- Every tool's verbs are `run`, `edit` and `about`.
- tagdoc uses the standard (the user, the same night): writing a document's metadata, vCards
  in XMP among them, stays in medRDS's reference library for the apps that file; tagdoc writes
  the descriptive part of chapter 7 in Python, as the library does.
