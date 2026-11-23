"""What a reading is, and :func:`read`, the short way to one.

A page with a text layer is read as it is.  A page without one (a scan, a photo) gets
the clean-up plan: the one given, else the automatic suggestion of
:func:`optdoc.cleanup.suggest`, which tells a photographed page from a scanned one by
the page itself, inside a PDF too (a photo bound into one).  The cleaned-up image
replaces the page, so that OCR, the output and anything a caller does afterwards
(redaction, for instance) see the same page.  Upscaling is not baked into the page;
such pages are read by OCR at the higher resolution instead.  The work itself is
:class:`optdoc.project.Project`'s; :func:`read` opens one and builds its result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from optdoc import cleanup
from optdoc import ocr as ocrlib
from optdoc.errors import OptdocError
from optdoc.pagetext import PageText
from optdoc.structure import Structure
from optdoc.tables import Table

SUGGESTION_DPI = 150  # resolution the clean-up suggestion looks at a page with
MAX_PIXELS_UPSCALED = 9000  # cap for the OCR image of an upscaled page


Progress = Callable[[int, int], None]  # page (from 1) about to be done, and how many


def suggestion_for(page: pymupdf.Page, photo: bool | None = None) -> cleanup.CleanupPlan:
    """The automatic clean-up suggestion for one image-only page; ``photo`` as in
    :func:`optdoc.cleanup.suggest` (None: told by the page)."""
    image, scale = cleanup.render(page, SUGGESTION_DPI)
    return cleanup.suggest(image, photo, scale, cleanup.native_dpi(page))


@dataclass
class PageReading:
    """One page as read: its text (with a box for every character), whether that text
    came from OCR, the structure of an OCR text, and on an OCR page for every word
    whether a person wrote it (corrected the OCR) rather than the engine."""

    number: int
    text: PageText
    ocr: bool
    structure: Structure | None = None
    person: list[bool] | None = None

    @property
    def markdown(self) -> str:
        """The page text as Markdown where it has a structure, else as it is."""
        return self.structure.render(self.text.text) if self.structure else self.text.text


@dataclass
class Reading:
    """A read document: the cleaned-up document, the plan that was applied, the pages,
    the OCR engine used (None without one), and the tables of its pages by page number
    once :func:`optdoc.output.write` has looked for them (None until then, or when it
    did not), and the configuration that makes it again (:mod:`optdoc.project`).  Call
    :meth:`close` when done."""

    source: Path
    doc: pymupdf.Document
    plan: dict[int, cleanup.CleanupPlan]
    pages: list[PageReading] = field(default_factory=list)
    reader: str | None = None
    tables: dict[int, list[Table]] | None = None
    config: dict[str, Any] | None = None

    @property
    def without_text(self) -> list[int]:
        """Pages that hold no text at all after reading (no text layer and no OCR)."""
        return [s.number for s in self.pages if not s.text.text.strip()]

    def close(self) -> None:
        """Close the document."""
        self.doc.close()


def read(
    path: str | Path,
    reader: str = "auto",
    languages: str | None = None,
    tables: bool = True,
    paper: str = "a4",
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
    is the clean-up per page number (from 0), every other page left as it is; without it
    the automatic suggestion is used, unless ``clean_up`` is False.  ``photo`` True takes
    every image-only page for a photo, False for a scan; None (the default) tells by each
    page.  ``with_structure`` gives OCR pages their structure.  ``progress`` is called
    with the number of the page about to be done (from 1) and the number of pages.

    Raises :class:`~optdoc.errors.OptdocError` (an :class:`~optdoc.errors.OCRError` for
    the engines); a plan that names a page the document does not have is a "bad-config"."""
    from optdoc.project import Options, Project

    options = Options(reader=reader, languages=languages, tables=tables, paper=paper,
                      photo=photo, clean_up=clean_up, structure=with_structure, dpi=dpi)
    project = Project.open(path, options)
    try:
        if plan is not None:
            if any(not 0 <= n < len(project.pages) for n in plan):
                raise OptdocError("bad-config", reason="page")
            for n in range(len(project.pages)):
                project.set_plan(n, plan.get(n))
        reading = project.build(progress)
    finally:
        project.close()
    return reading
