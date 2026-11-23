"""The reading pipeline: open a file, clean up its image-only pages, read every page
(its text layer, or OCR where there is none) and give the OCR text its structure.

A page with a text layer is read as it is.  A page without one (a scan, a photo) gets
the clean-up plan: the one given, else the automatic suggestion of
:func:`optdoc.cleanup.suggest`, which tells a photographed page from a scanned one by
the page itself, inside a PDF too (a photo bound into one).  The cleaned-up image
replaces the page, so that OCR, the output and anything a caller does afterwards
(redaction, for instance) see the same page.  Upscaling is not baked into the page;
such pages are read by OCR at the higher resolution instead.  The pages are done one
after the other, each cleaned up and read before the next, so that a caller can be
told how far the work has come.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from optdoc import cleanup
from optdoc import ocr as ocrlib
from optdoc.errors import OptdocError
from optdoc.loading import open_document
from optdoc.pagetext import PageText, read_text_layer
from optdoc.structure import Structure, analyse_page_structure
from optdoc.tables import Table

SUGGESTION_DPI = 150  # resolution the clean-up suggestion looks at a page with
MAX_PIXELS_UPSCALED = 9000  # cap for the OCR image of an upscaled page


Progress = Callable[[int, int], None]  # page (from 1) about to be done, and how many


def suggestion_for(page: pymupdf.Page, photo: bool | None = None) -> cleanup.CleanupPlan:
    """The automatic clean-up suggestion for one image-only page; ``photo`` as in
    :func:`optdoc.cleanup.suggest` (None: told by the page)."""
    image, scale = cleanup.render(page, SUGGESTION_DPI)
    return cleanup.suggest(image, photo, scale, cleanup.native_dpi(page))


def _plan_of_page(page: pymupdf.Page, number: int,
                  plan: dict[int, cleanup.CleanupPlan] | None, clean_up: bool,
                  photo: bool | None) -> cleanup.CleanupPlan | None:
    """The clean-up of one page: its entry in the plan given, else the suggestion for an
    image-only page (with OpenCV, unless ``clean_up`` is off); None when nothing would
    change."""
    if plan is not None:
        a = plan.get(number)
    elif clean_up and cleanup.available() and not read_text_layer(page, number).has_text_layer:
        a = suggestion_for(page, photo)
    else:
        a = None
    return a if a is not None and a.active else None


@dataclass
class PageReading:
    """One page as read: its text (with a box for every character), whether that text
    came from OCR, and the structure of an OCR text."""

    number: int
    text: PageText
    ocr: bool
    structure: Structure | None = None

    @property
    def markdown(self) -> str:
        """The page text as Markdown where it has a structure, else as it is."""
        return self.structure.render(self.text.text) if self.structure else self.text.text


@dataclass
class Reading:
    """A read document: the cleaned-up document, the plan that was applied, the pages,
    the OCR engine used (None without one), and the tables of its pages by page number
    once :func:`optdoc.output.write` has looked for them (None until then, or when it
    did not).  Call :meth:`close` when done."""

    source: Path
    doc: pymupdf.Document
    plan: dict[int, cleanup.CleanupPlan]
    pages: list[PageReading] = field(default_factory=list)
    reader: str | None = None
    tables: dict[int, list[Table]] | None = None

    @property
    def without_text(self) -> list[int]:
        """Pages that hold no text at all after reading (no text layer and no OCR)."""
        return [s.number for s in self.pages if not s.text.text.strip()]

    def close(self) -> None:
        """Close the document."""
        self.doc.close()


def ocr_page(page: pymupdf.Page, reader: ocrlib.OCRBackend,
               plan: cleanup.CleanupPlan | None = None, number: int | None = None,
               dpi: int = ocrlib.OCR_DPI) -> PageText:
    """OCR of one page at the resolution and with the finish its plan asks for: an
    upscaled page is read at that multiple of ``dpi`` (capped), a page in letter mode
    gets the letter-aware finish before the engine."""
    factor = max(1, plan.upscale) if plan is not None else 1
    filter_ = (functools.partial(cleanup.letter_finish, factor=factor)
               if plan is not None and plan.letter_mode else None)
    return ocrlib.recognise_page(
        page, reader, number, dpi=dpi * factor,
        max_pixel=min(ocrlib.MAX_PIXELS * factor, MAX_PIXELS_UPSCALED), filter_=filter_)


def _read_one(doc: pymupdf.Document, number: int, reader: ocrlib.OCRBackend | None,
          plan: cleanup.CleanupPlan | None, dpi: int, with_structure: bool) -> PageReading:
    """One page: its text layer where that suffices, else its OCR with structure."""
    page = doc[number]
    layer = read_text_layer(page, number)
    if reader is None or not ocrlib.needs_ocr(page, layer):
        return PageReading(number, layer, False)
    text = ocr_page(page, reader, plan, number, dpi)
    structure = analyse_page_structure(page, text) if with_structure else None
    return PageReading(number, text, True, structure)


def read(
    path: str | Path,
    reader: str = "auto",
    languages: str | None = None,
    tables: bool = True,
    paper: str | None = "a4",
    plan: dict[int, cleanup.CleanupPlan] | None = None,
    clean_up: bool = True,
    dpi: int = ocrlib.OCR_DPI,
    with_structure: bool = True,
    photo: bool | None = None,
    progress: Progress | None = None,
) -> Reading:
    """Read a PDF or an image.

    ``reader`` is the OCR engine ("auto", "rapidocr", "tesseract", "none"), ``languages``
    its language packs, ``tables`` Tesseract's second pass for table grids, ``paper``
    the paper size an image is placed on ("image" keeps the image's own size).  ``plan``
    is the clean-up per page number (from 0); without it the automatic suggestion is
    used, unless ``clean_up`` is False.  ``photo`` True takes every image-only page for a
    photo, False for a scan; None (the default) tells by each page.  ``with_structure``
    gives OCR pages their structure.  ``progress`` is called with the number of the page
    about to be done (from 1) and the number of pages.

    Raises :class:`~optdoc.errors.OptdocError` (an :class:`~optdoc.errors.OCRError` for
    the engines); a plan that names a page the document does not have is a "bad-plan"."""
    source = Path(path)
    doc = open_document(source, paper)  # first: a missing file is told before an engine starts
    try:
        engine = ocrlib.backend(reader, languages, tables=tables)
        if plan is not None and any(not 0 <= n < len(doc) for n in plan):
            raise OptdocError("bad-plan", reason="page")
        applied: dict[int, cleanup.CleanupPlan] = {}
        pages = []
        for number in range(len(doc)):
            if progress is not None:
                progress(number + 1, len(doc))
            a = _plan_of_page(doc[number], number, plan, clean_up, photo)
            if a is not None:
                cleanup.replace_page(doc, number, a, dpi)
                applied[number] = a
            pages.append(_read_one(doc, number, engine, a, dpi, with_structure))
    except Exception:
        doc.close()
        raise
    return Reading(source, doc, applied, pages, engine.name if engine else None)
