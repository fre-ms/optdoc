"""The reading pipeline: open a file, clean up its image-only pages, read every page
(its text layer, or OCR where there is none) and give the OCR text its structure.

A page with a text layer is read as it is.  A page without one (a scan, a photo) gets
the clean-up plan: the one given, else the automatic suggestion of
:func:`optdoc.cleanup.suggest`.  The cleaned-up image replaces the page, so that
OCR, the output and anything a caller does afterwards (redaction, for instance) see
the same page.  Upscaling is not baked into the page; such pages are read by OCR at
the higher resolution instead.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from optdoc import cleanup
from optdoc import ocr as ocrlib
from optdoc.loading import HEIC_SUFFIXES, IMAGE_SUFFIXES, open_document
from optdoc.pagetext import PageText, read_text_layer
from optdoc.structure import Structure, analyse_page_structure

SUGGESTION_DPI = 150  # resolution the clean-up suggestion looks at a page with
MAX_PIXELS_UPSCALED = 9000  # cap for the OCR image of an upscaled page


def is_photo(path: str | Path) -> bool:
    """True for an image file (photo, scan as JPEG, PNG, HEIC) rather than a PDF."""
    return Path(path).suffix.lower() in IMAGE_SUFFIXES | HEIC_SUFFIXES


def suggestion_for(page: pymupdf.Page, photo: bool) -> cleanup.CleanupPlan:
    """The automatic clean-up suggestion for one image-only page."""
    image, scale = cleanup.render(page, SUGGESTION_DPI)
    return cleanup.suggest(image, photo, scale, cleanup.native_dpi(page))


def plan_for(doc: pymupdf.Document, photo: bool) -> dict[int, cleanup.CleanupPlan]:
    """The suggestions for the image-only pages of ``doc``, active ones only; empty
    without OpenCV."""
    if not cleanup.available():
        return {}
    plan: dict[int, cleanup.CleanupPlan] = {}
    for i, page in enumerate(doc):
        if read_text_layer(page, i).has_text_layer:
            continue
        a = suggestion_for(page, photo)
        if a.active:
            plan[i] = a
    return plan


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
    and the OCR engine used (None without one).  Call :meth:`close` when done."""

    source: Path
    doc: pymupdf.Document
    plan: dict[int, cleanup.CleanupPlan]
    pages: list[PageReading] = field(default_factory=list)
    reader: str | None = None

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
) -> Reading:
    """Read a PDF or an image.

    ``reader`` is the OCR engine ("auto", "rapidocr", "tesseract", "none"), ``languages``
    its language packs, ``tables`` Tesseract's second pass for table grids, ``paper``
    the paper size an image is placed on (``None`` keeps the image's own size).  ``plan``
    is the clean-up per page number; without it the automatic suggestion is used, unless
    ``clean_up`` is False.  ``with_structure`` gives OCR pages their structure."""
    source = Path(path)
    engine = ocrlib.backend(reader, languages, tables=tables)
    doc = open_document(source, paper)
    try:
        if plan is None:
            plan = plan_for(doc, is_photo(source)) if clean_up else {}
        plan = {n: a for n, a in plan.items() if a.active and 0 <= n < len(doc)}
        for number in sorted(plan):
            cleanup.replace_page(doc, number, plan[number], dpi)
        pages = [_read_one(doc, i, engine, plan.get(i), dpi, with_structure)
                 for i in range(len(doc))]
    except Exception:
        doc.close()
        raise
    return Reading(source, doc, plan, pages, engine.name if engine else None)
