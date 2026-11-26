"""What a reading leaves behind: a searchable PDF, the reading as JSON, the text as
Markdown, and the configuration that makes it again (:mod:`optdoc.project`).

The PDF is the cleaned-up document; the OCR text is laid invisibly over the place where
it is printed, line by line (:mod:`optdoc.textlayer`), so that a reader can search and
select the text of a scan like that of a born-digital document, and a program that
takes the text out gets a printed row as one line.  The JSON names every word with its
box in page points and the engine's confidence; it is meant for programs in other
languages (a records app, a laboratory reader) and says which version of optdoc and
which engine made it.

The same reading and configuration always give the same bytes: the PDF carries no time
and a file identifier made from its configuration, which it also carries as an
embedded file (``optdoc.json``) without dates.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pymupdf

from optdoc import __version__, textlayer
from optdoc.errors import OptdocError
from optdoc.pagetext import PageText
from optdoc.project import EMBEDDED, SUFFIX, config_bytes
from optdoc.reading import PageReading, Reading
from optdoc.tables import Table

FORMAT = "optdoc-reading"
FORMAT_VERSION = 1


def _word_box(page_text: PageText, a: int, b: int) -> pymupdf.Rect | None:
    """The union of the boxes of ``page_text.text[a:b]``, or None without boxes."""
    boxes_found = page_text.rects(a, b)
    if not boxes_found:
        return None
    word = pymupdf.Rect(boxes_found[0])
    for r in boxes_found[1:]:
        word |= r
    return word


def _words(page_text: PageText, person: list[bool] | None = None) -> list[dict[str, Any]]:
    """The words of a page with their boxes and, for OCR, the engine's confidence and
    who wrote the word: "ocr", or "person" where someone corrected it (``person``)."""
    words_of_page = page_text.words()
    confidences = (page_text.confidences
                   if len(page_text.confidences) == len(words_of_page) else [])
    words = []
    for i, (a, b) in enumerate(words_of_page):
        bounds = _word_box(page_text, a, b)
        word: dict[str, Any] = {"text": page_text.text[a:b], "start": a, "end": b,
                                "box": ([round(v, 2) for v in (bounds.x0, bounds.y0, bounds.x1,
                                                               bounds.y1)]
                                        if bounds else None)}
        if confidences:
            word["confidence"] = round(confidences[i], 3)
        if person is not None and len(person) == len(words_of_page):
            word["by"] = "person" if person[i] else "ocr"
        words.append(word)
    return words


def _regions(s: PageReading) -> list[dict[str, Any]]:
    """The regions of a page for the reading, in reading order: kind, box, who set it,
    and for a table the number of its table in the page's ``tables``."""
    regions, table = [], 0
    for r in s.regions:
        d: dict[str, Any] = {"kind": r.kind, "box": [round(v, 2) for v in r.box], "by": r.by}
        if r.kind == "table":
            d["table"] = table
            table += 1
        regions.append(d)
    return regions


def _page_as_dict(s: PageReading, tables: list[Table] | None) -> dict[str, Any]:
    """One page of the reading; ``tables`` None when they were not looked for."""
    return {
        "page": s.number + 1,
        "width": round(s.text.width, 2),
        "height": round(s.text.height, 2),
        "source": "ocr" if s.ocr else "text",
        "text": s.text.text,
        "markdown": s.markdown,
        "words": _words(s.text, s.person),
        "regions": _regions(s),
        "tables": [t.as_dict() for t in tables] if tables is not None else None,
    }


def plan_as_dict(reading: Reading) -> dict[str, Any]:
    """The clean-up plan by page number (counted from 1), every switch and corner."""
    return {str(n + 1): a.full_dict() for n, a in sorted(reading.plan.items())}


def reading_as_dict(reading: Reading) -> dict[str, Any]:
    """The reading as a JSON-ready dictionary."""
    return {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "made_with": f"optdoc {__version__}",
        "reader": reading.reader,
        "source": reading.source.name,
        "plan": plan_as_dict(reading),
        "pages": [_page_as_dict(s, None if reading.tables is None
                                else reading.tables.get(s.number, []))
                  for s in reading.pages],
    }


def markdown(reading: Reading) -> str:
    """The text of all pages as Markdown, a heading per page."""
    parts = [f"## Page {s.number + 1}\n\n{s.markdown.strip()}\n" for s in reading.pages]
    return "\n".join(parts)


def _embed(doc: pymupdf.Document, config: bytes) -> None:
    """Put the configuration into the PDF as an embedded file, without the dates MuPDF
    would give it (they would make every run different)."""
    # PyMuPDF returns the xref of the file specification; its type hints say nothing.
    xref: int = doc.embfile_add(  # type: ignore[func-returns-value, assignment]
        EMBEDDED, config, filename=EMBEDDED,
        desc="optdoc configuration: makes this PDF again from the original")
    kind, value = doc.xref_get_key(xref, "EF/F")
    stream = int(value.split()[0]) if kind == "xref" else xref
    for key in ("Params/CreationDate", "Params/ModDate"):
        doc.xref_set_key(stream, key, "null")


def searchable_pdf(reading: Reading) -> bytes:
    """The cleaned-up document with an invisible text layer on every OCR page, carrying
    the configuration; its file identifier is made from the configuration, so that the
    same reading gives the same bytes."""
    duplicate = pymupdf.open("pdf", reading.doc.tobytes())
    try:
        font = None
        for s in reading.pages:
            if s.ocr:
                font = font or textlayer.add_font(duplicate)
                textlayer.write_page(duplicate, duplicate[s.number], s.text, font)
        made_by = f"optdoc {__version__}"
        duplicate.set_metadata({"producer": made_by, "creator": made_by})
        config = config_bytes(reading.config) if reading.config is not None else b""
        if config:
            _embed(duplicate, config)
        ident = hashlib.sha256(config + made_by.encode()).hexdigest()[:32].upper()
        duplicate.xref_set_key(-1, "ID", f"[<{ident}><{ident}>]")
        return duplicate.tobytes(garbage=3, deflate=True, no_new_id=True)
    finally:
        duplicate.close()


def write(reading: Reading, folder: str | Path, stem: str | None = None) -> dict[str, Path]:
    """Write ``<stem>.pdf``, ``<stem>.reading.json``, ``<stem>.md`` and the
    configuration ``<stem>.optdoc.json`` (where the reading has one) into ``folder``
    (created when missing); returns the paths.  Nothing is written anywhere else.  Raises
    :class:`~optdoc.errors.OptdocError`: "same-as-source" when the PDF would replace the
    document that was read, "unwritable" when the folder cannot take the files."""
    target = Path(folder)
    stem = stem or reading.source.stem
    paths = {
        "pdf": target / f"{stem}.pdf",
        "reading": target / f"{stem}.reading.json",
        "markdown": target / f"{stem}.md",
        "config": target / f"{stem}{SUFFIX}",
    }
    if paths["pdf"].resolve() == reading.source.resolve():
        raise OptdocError("same-as-source")
    pdf = searchable_pdf(reading)
    try:
        target.mkdir(parents=True, exist_ok=True)
        paths["pdf"].write_bytes(pdf)
    except OSError as e:
        raise OptdocError("unwritable") from e
    contents = {
        "reading": json.dumps(reading_as_dict(reading), ensure_ascii=False,
                              indent=1).encode("utf-8"),
        "markdown": markdown(reading).encode("utf-8"),
    }
    if reading.config is not None:
        contents["config"] = config_bytes(reading.config)
    else:
        del paths["config"]
    try:
        for key, data in contents.items():
            paths[key].write_bytes(data)
    except OSError as e:
        raise OptdocError("unwritable") from e
    return paths
