"""A piece of work on one document, and its configuration.

A project holds everything that decides what optdoc makes of a file: the settings
(engine, paper, the clean-up switches), the clean-up plan of every page, what OCR read
on every page (its words with their boxes and confidences), the regions of every page
(text, tables with their grids, pictures …: :mod:`optdoc.layout`), and the text a
person corrected.  Its configuration (``<name>.optdoc.json``, format ``optdoc-config``) is
that, and nothing else: no paths, no times.  It serves three ends:

- **Interrupting and resuming.**  The window (``optdoc edit``) saves the configuration
  and opens it again where the person stopped.
- **Reproducing.**  The file and its configuration always give the same result,
  byte for byte: the clean-up is computed from the plan, and the text from the words
  stored, so that OCR, which is not always deterministic, does not run again; so are
  the regions found automatically.  A page whose words or regions are not stored yet
  is read, and its regions found, when the result is made.
- **Improving on a result.**  The configuration also travels inside the PDF optdoc
  writes (an embedded file ``optdoc.json``); ``--config`` takes that PDF as well.

The configuration names the file it belongs to by its SHA-256; another file is refused.
The command line, the window and :func:`optdoc.reading.read` all make their results
through :meth:`Project.build`, so that there is one way from a configuration to a result.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from optdoc import __version__, cleanup, layout, tables, textlayer
from optdoc import ocr as ocrlib
from optdoc.alignment import align_correction
from optdoc.errors import OptdocError
from optdoc.loading import open_document
from optdoc.pagetext import PageText, read_text_layer
from optdoc.reading import (
    MAX_PIXELS_UPSCALED,
    PageReading,
    Progress,
    Reading,
    suggestion_for,
)
from optdoc.structure import analyse_page_structure
from optdoc.tables import Table

FORMAT = "optdoc-config"
FORMAT_VERSION = 1
SUFFIX = ".optdoc.json"
EMBEDDED = "optdoc.json"  # the name of the configuration inside the PDF


@dataclass
class Options:
    """The settings that decide the result: OCR engine and its language packs,
    Tesseract's second pass for table grids, the paper an image is placed on, photo or
    scan (None: told by each page), the automatic clean-up, the structure of OCR text,
    the resolution pages are cleaned up and read at, and whether tables are found with
    their cells automatically (``cells``; a person can set them all the same)."""

    reader: str = "auto"
    languages: str | None = None
    tables: bool = True
    paper: str = "a4"
    photo: bool | None = None
    clean_up: bool = True
    structure: bool = True
    dpi: int = ocrlib.OCR_DPI
    cells: bool = True

    def as_dict(self) -> dict[str, Any]:
        """The settings for the configuration."""
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: Any) -> Options:
        """The settings from a configuration; a value of the wrong kind is a "bad-config"."""
        if not isinstance(d, dict):
            raise OptdocError("bad-config", reason="field")
        options = cls()
        kinds: dict[str, tuple[type, ...]] = {
            "reader": (str,), "languages": (str, type(None)), "tables": (bool,),
            "paper": (str,), "photo": (bool, type(None)), "clean_up": (bool,),
            "structure": (bool,), "dpi": (int,), "cells": (bool,)}
        for name, value in d.items():
            if name not in kinds:
                continue
            bad = not isinstance(value, kinds[name])
            if name == "dpi" and isinstance(value, int):
                bad = bad or isinstance(value, bool) or not 72 <= value <= 1200
            if bad:
                raise OptdocError("bad-config", reason="field")
            setattr(options, name, value)
        return options


@dataclass
class _Page:
    """The state of one page: its plan once decided (None: no clean-up), what OCR read
    on the cleaned page (None: not read yet; ``ocr`` False: the page has a text layer
    and needs none), its regions (None: not found yet) and whether a person set them,
    and the person's correction of the OCR text."""

    decided: bool = False
    plan: cleanup.CleanupPlan | None = None
    ocr: bool | None = None
    words: list[ocrlib.OCRWord] | None = None
    correction: str | None = None
    regions: list[layout.Region] | None = None
    regions_by_person: bool = False
    suggestion: cleanup.CleanupPlan | None = field(default=None, repr=False)


def _plan_key(plan: cleanup.CleanupPlan | None) -> str:
    """A plan as a string that is equal for plans that do the same."""
    if plan is None or not plan.active:
        return ""
    return json.dumps(plan.full_dict(), sort_keys=True)


def _geometry_key(plan: cleanup.CleanupPlan | None) -> str:
    """What of a plan moves things on the page (turning, unwarping, straightening): the
    regions a person set stay where the rest of a plan changes."""
    if plan is None:
        return json.dumps([0, False, False])
    return json.dumps([plan.rotation, plan.unwarp and plan.corners,
                       plan.straighten and plan.angle])


def _copy(plan: cleanup.CleanupPlan | None) -> cleanup.CleanupPlan | None:
    """An independent copy of a plan (own lists of corners and masks)."""
    return None if plan is None else cleanup.CleanupPlan.from_dict(plan.full_dict())


def _rounded(w: ocrlib.OCRWord) -> ocrlib.OCRWord:
    """A word as the configuration keeps it: boxes to a thousandth of a point, the
    confidence to four places; the result is made from these, live or reproduced."""
    return ocrlib.OCRWord(w.text, round(w.x0, 3), round(w.y0, 3), round(w.x1, 3),
                          round(w.y1, 3), round(w.confidence, 4))


def _word_from(row: Any) -> ocrlib.OCRWord:
    """A stored word ``[text, x0, y0, x1, y1, confidence]``."""
    if not (isinstance(row, list) and len(row) == 6 and isinstance(row[0], str)
            and all(isinstance(v, int | float) and not isinstance(v, bool) for v in row[1:])):
        raise OptdocError("bad-config", reason="field")
    return ocrlib.OCRWord(row[0], *(float(v) for v in row[1:]))


def digest(path: Path) -> str:
    """The SHA-256 of a file, as the configuration names it."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(path: str | Path) -> dict[str, Any]:
    """A configuration from its file, or from the PDF optdoc wrote, which carries it.
    Raises "missing", or "bad-config" (reason "json" or "format") for a file that holds
    none optdoc can read."""
    path = Path(path)
    if not path.is_file():
        raise OptdocError("missing")
    try:
        if path.suffix.lower() == ".pdf":
            with pymupdf.open(path) as doc:
                if EMBEDDED not in doc.embfile_names():
                    raise OptdocError("bad-config", reason="format")
                raw = doc.embfile_get(EMBEDDED)
        else:
            raw = path.read_bytes()
        config = json.loads(raw.decode("utf-8"))
    except OptdocError:
        raise
    except Exception as e:
        raise OptdocError("bad-config", reason="json") from e
    if not isinstance(config, dict) or config.get("format") != FORMAT:
        raise OptdocError("bad-config", reason="format")
    if config.get("version") != FORMAT_VERSION:
        raise OptdocError("bad-config", reason="format")
    return config


class Project:
    """The work on one document; see the module.  Open with :meth:`open`, close with
    :meth:`close`.  Page numbers count from 0."""

    def __init__(self, source: Path, doc: pymupdf.Document, sha256: str, size: int,
                 options: Options) -> None:
        self.source = source
        self.original = doc  # every page upright, as it came
        self.sha256 = sha256
        self.size = size
        self.options = options
        self.pages = [_Page() for _ in range(len(doc))]
        self._work = pymupdf.open("pdf", doc.tobytes())  # the pages as cleaned up
        self._applied: list[str] = [""] * len(doc)  # the plan each work page shows
        self._images: dict[int, tuple[str, tuple[bytes, float, float]]] = {}
        self._layer: dict[int, bool] = {}
        self._engine: ocrlib.OCRBackend | None = None
        self._engine_made = False
        self._stored_reader: str | None = None

    # -- opening and saving --------------------------------------------------------------------
    @classmethod
    def open(cls, source: str | Path, options: Options | None = None,
             config: dict[str, Any] | None = None) -> Project:
        """A project on ``source``: fresh with ``options``, or as ``config`` left it
        (whose settings then count).  Raises "config-mismatch" when the configuration
        belongs to another file, and what :func:`optdoc.loading.open_document` raises."""
        source = Path(source)
        if not source.is_file():
            raise OptdocError("missing")
        sha256 = digest(source)
        if config is not None:
            named = config.get("source")
            if not isinstance(named, dict) or named.get("sha256") != sha256:
                raise OptdocError("config-mismatch")
            options = Options.from_dict(config.get("options", {}))
        options = options or Options()
        doc = open_document(source, options.paper)
        project = cls(source, doc, sha256, source.stat().st_size, options)
        if config is not None:
            reader = config.get("reader")
            project._stored_reader = reader if isinstance(reader, str) else None
            try:
                project._take_pages(config.get("pages"))
            except Exception:
                project.close()
                raise
        return project

    def _take_pages(self, pages: Any) -> None:
        """The pages of a configuration: one entry per page of the document."""
        if not isinstance(pages, list) or len(pages) != len(self.pages):
            raise OptdocError("bad-config", reason="page")
        for page, entry in zip(self.pages, pages, strict=True):
            if not isinstance(entry, dict):
                raise OptdocError("bad-config", reason="field")
            plan = entry.get("plan")
            page.decided = True
            page.plan = None if plan is None else cleanup.CleanupPlan.from_dict(plan)
            ocr = entry.get("ocr")
            if ocr is not None and not isinstance(ocr, bool):
                raise OptdocError("bad-config", reason="field")
            page.ocr = ocr
            words = entry.get("words")
            page.words = None if words is None or not isinstance(words, list) else [
                _word_from(row) for row in words]
            if ocr and page.words is None:
                page.ocr = None  # to be read again
            correction = entry.get("correction")
            if correction is not None and not isinstance(correction, str):
                raise OptdocError("bad-config", reason="field")
            page.correction = correction
            found = entry.get("layout")
            if found is not None:
                if not isinstance(found, dict) or found.get("by") not in layout.BY:
                    raise OptdocError("bad-config", reason="field")
                page.regions = layout.regions_from_dicts(found.get("regions"))
                page.regions_by_person = found["by"] == "person"

    def config(self) -> dict[str, Any]:
        """The configuration: settings, and per page the plan (resolved: the suggestion
        where none was decided; kept also where it does nothing, for the corners it
        found), what OCR read, the regions (found or set; None while not found), and the
        correction."""
        pages = []
        for n, page in enumerate(self.pages):
            plan = self.plan(n)
            pages.append({
                "page": n + 1,
                "plan": plan.full_dict() if plan is not None else None,
                "ocr": page.ocr,
                "words": None if page.words is None else [
                    [w.text, w.x0, w.y0, w.x1, w.y1, w.confidence] for w in page.words],
                "layout": None if page.regions is None else {
                    "by": "person" if page.regions_by_person else "auto",
                    "regions": [r.as_dict() for r in page.regions]},
                "correction": page.correction,
            })
        return {
            "format": FORMAT, "version": FORMAT_VERSION, "made_with": f"optdoc {__version__}",
            "source": {"sha256": self.sha256, "bytes": self.size,
                       "suffix": self.source.suffix.lower()},
            "options": self.options.as_dict(),
            "reader": self.reader_name(),
            "pages": pages,
        }

    def save(self, path: str | Path) -> Path:
        """Write the configuration to ``path``; raises "unwritable"."""
        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(config_bytes(self.config()))
        except OSError as e:
            raise OptdocError("unwritable") from e
        return path

    def close(self) -> None:
        """Release both documents."""
        self._work.close()
        self.original.close()

    # -- the clean-up --------------------------------------------------------------------------
    def has_text_layer(self, n: int) -> bool:
        """True when the page as it came carries text of its own (it is not cleaned up)."""
        if n not in self._layer:
            self._layer[n] = read_text_layer(self.original[n], n).has_text_layer
        return self._layer[n]

    def cleanable(self, n: int) -> bool:
        """True for a page without a text layer (a scan, a photo), when OpenCV is there."""
        return cleanup.available() and not self.has_text_layer(n)

    def suggestion(self, n: int) -> cleanup.CleanupPlan:
        """optdoc's suggestion for a page without text layer (computed once); an empty
        plan for any other page."""
        page = self.pages[n]
        if page.suggestion is None:
            page.suggestion = (suggestion_for(self.original[n], self.options.photo)
                               if self.cleanable(n) else cleanup.CleanupPlan())
        return _copy(page.suggestion) or cleanup.CleanupPlan()

    def plan(self, n: int) -> cleanup.CleanupPlan | None:
        """The clean-up plan of a page, a copy: as decided, else the suggestion (unless
        the automatic clean-up is off).  It may do nothing (every step off), and keeps
        what it found all the same (the corners of a sheet, the tilt)."""
        page = self.pages[n]
        if page.decided:
            return _copy(page.plan)
        if not self.options.clean_up or not self.cleanable(n):
            return None
        return self.suggestion(n)

    def active_plan(self, n: int) -> cleanup.CleanupPlan | None:
        """The plan of a page where it changes the page, else None."""
        plan = self.plan(n)
        return plan if plan is not None and plan.active else None

    def set_plan(self, n: int, plan: cleanup.CleanupPlan | None) -> None:
        """Decide the clean-up plan of a page.  When it changes what the page looks like,
        what OCR read is dropped (the page is read again); a correction stays and is laid
        on the new words."""
        page = self.pages[n]
        changed = _plan_key(plan) != _plan_key(self.plan(n))
        moved = _geometry_key(plan) != _geometry_key(self.plan(n))
        page.decided = True
        page.plan = _copy(plan)
        if changed:
            page.words, page.ocr = None, None
            # found regions are found again on the new words; a person's stay where
            # nothing moved on the page
            if not page.regions_by_person or moved:
                page.regions, page.regions_by_person = None, False

    def _image(self, n: int) -> tuple[bytes, float, float] | None:
        """The cleaned-up image of a page and the size of its page (computed once per
        plan); None for a page that is not cleaned up."""
        plan = self.active_plan(n)
        if plan is None:
            return None
        key = _plan_key(plan)
        if n not in self._images or self._images[n][0] != key:
            self._images[n] = (key, cleanup.cleaned_image(self.original[n], plan,
                                                          self.options.dpi))
        return self._images[n][1]

    def _cleaned(self, n: int) -> pymupdf.Page:
        """The page as cleaned up by its plan, made from the original each time the plan
        changed."""
        key = _plan_key(self.plan(n))
        if self._applied[n] != key:
            self._work.delete_page(n)
            self._work.insert_pdf(self.original, from_page=n, to_page=n, start_at=n)
            image = self._image(n)
            if image is not None:
                cleanup.put_page_image(self._work, n, *image)
            self._applied[n] = key
        return self._work[n]

    def page_png(self, n: int, dpi: int = 100) -> bytes:
        """The page as OCR sees it (cleaned up, not upscaled), as PNG."""
        return self._cleaned(n).get_pixmap(dpi=dpi, alpha=False).tobytes("png")

    def original_png(self, n: int, dpi: int = 100) -> bytes:
        """The page as it came, as PNG."""
        return self.original[n].get_pixmap(dpi=dpi, alpha=False).tobytes("png")

    def preview(self, n: int, plan: cleanup.CleanupPlan, dpi: int = 100) -> tuple[bytes, float]:
        """The page as ``plan`` would clean it up (upscaling shown), as PNG, and its pixels
        per point (:func:`optdoc.cleanup.preview_png`)."""
        return cleanup.preview_png(self.original[n], plan, dpi)

    def cleaned_width(self, n: int, plan: cleanup.CleanupPlan) -> float:
        """The width in points of the page ``plan`` makes (a quarter turn swaps sides)."""
        r = self.original[n].rect
        return r.width if plan.rotation in (0, 180) else r.height

    # -- reading -------------------------------------------------------------------------------
    def engine(self) -> ocrlib.OCRBackend | None:
        """The OCR engine of the settings, started once; None for "none" (or no engine
        installed for "auto")."""
        if not self._engine_made:
            self._engine = ocrlib.backend(self.options.reader, self.options.languages,
                                          tables=self.options.tables)
            self._engine_made = True
        return self._engine

    def reader_name(self) -> str | None:
        """The engine that read the pages: as stored, else the engine of the settings
        once it has started."""
        if self._engine_made:
            return self._engine.name if self._engine is not None else None
        if self._stored_reader is not None:
            return self._stored_reader
        return self.options.reader if self.options.reader in ("rapidocr", "tesseract") \
            else None

    def needs_reading(self, n: int) -> bool:
        """True while the page has not been read since its clean-up last changed."""
        return self.pages[n].ocr is None

    def read(self, n: int) -> None:
        """Read a page: its text layer where that suffices, else OCR on the cleaned page
        (the words are kept).  Nothing happens to a page read already."""
        page = self.pages[n]
        if page.ocr is not None:
            return
        cleaned = self._cleaned(n)
        engine = self.engine()
        if engine is None or not ocrlib.needs_ocr(cleaned, read_text_layer(cleaned, n)):
            page.ocr, page.words = False, None
            return
        plan = self.active_plan(n)
        factor = max(1, plan.upscale) if plan is not None else 1
        finish = (functools.partial(cleanup.letter_finish, factor=factor)
                  if plan is not None and plan.letter_mode else None)
        words = ocrlib.recognise_words(
            cleaned, engine, dpi=self.options.dpi * factor,
            max_pixel=min(ocrlib.MAX_PIXELS * factor, MAX_PIXELS_UPSCALED), filter_=finish)
        page.words = [_rounded(w) for w in words]
        page.ocr = True

    def read_all(self, progress: Progress | None = None) -> None:
        """Read every page not read yet."""
        for n in range(len(self.pages)):
            if progress is not None:
                progress(n + 1, len(self.pages))
            self.read(n)

    def ocr_text(self, n: int, every_word: bool = False) -> PageText | None:
        """What OCR read on the page, as a page text, without the words in regions that
        are not read (pictures, barcodes, "ignore"), unless ``every_word``; None for a
        page not read by OCR."""
        page = self.pages[n]
        if not page.ocr or page.words is None:
            return None
        words = page.words
        if not every_word and page.regions:
            words = [w for w in words
                     if layout.is_read(page.regions, (w.x0, w.y0, w.x1, w.y1))]
        cleaned = self._cleaned(n)
        return ocrlib.page_text_from_words(words, n, cleaned.rect.width, cleaned.rect.height)

    def text(self, n: int) -> str:
        """The text of a page as it will be: the correction, else what OCR read, else the
        text layer.  Reads the page first."""
        self.read(n)
        page = self.pages[n]
        if page.correction is not None:
            return page.correction
        ocr = self.ocr_text(n)
        return ocr.text if ocr is not None else read_text_layer(self._cleaned(n), n).text

    def set_correction(self, n: int, text: str) -> None:
        """Keep a person's correction of the OCR text of a page; the text as read (spacing
        at its end aside) takes it back.  Only for pages read by OCR."""
        self.read(n)
        ocr = self.ocr_text(n)
        if ocr is None:
            raise OptdocError("not-ocr", page=n + 1)
        self.pages[n].correction = None if text.rstrip() == ocr.text.rstrip() else text

    # -- the regions ---------------------------------------------------------------------------
    def finds_tables(self) -> bool:
        """True when tables are found automatically (the setting, and Camelot there)."""
        return self.options.cells and tables.available()

    def regions(self, n: int) -> list[layout.Region]:
        """The regions of a page (copies): as a person set them, else as found (once; the
        page is read first)."""
        page = self.pages[n]
        if page.regions is None:
            page.regions = self.find_regions(n)
            page.regions_by_person = False
        return [layout.copy(r) for r in page.regions]

    def has_regions(self, n: int) -> bool:
        """True when the regions of the page are known (found or set): no work to wait for."""
        return self.pages[n].regions is not None

    def forget_regions(self, n: int) -> None:
        """Forget the regions of a page, a person's too: they are found again."""
        self.pages[n].regions, self.pages[n].regions_by_person = None, False

    def regions_by_person(self, n: int) -> bool:
        """True when a person set the regions of the page."""
        return self.pages[n].regions_by_person

    def set_regions(self, n: int, regions: list[layout.Region]) -> None:
        """A person's regions for a page; raises "bad-config" (reason "field") for a
        region that makes no sense."""
        if not all(r.valid() for r in regions):
            raise OptdocError("bad-config", reason="field")
        page = self.pages[n]
        page.regions = [layout.rounded(r) for r in regions]
        page.regions_by_person = True

    def leave_out_found_tables(self) -> None:
        """Find no tables from now on, and forget those found (a person's stay)."""
        self.options.cells = False
        for page in self.pages:
            if not page.regions_by_person:
                page.regions = None

    def find_regions(self, n: int) -> list[layout.Region]:
        """The regions optdoc finds on a page (read first): its tables with their grids
        (Camelot on the page with its text, as the PDF will carry it); none where tables
        are not found automatically or finding them failed."""
        self.read(n)
        if not self.finds_tables():
            return []
        self._cleaned(n)  # the work page shows the current plan (or the page as it came)
        single = pymupdf.open()
        try:
            single.insert_pdf(self._work, from_page=n, to_page=n)
            text = self.ocr_text(n, every_word=True)
            if text is not None:
                textlayer.write_page(single, single[0], text, textlayer.add_font(single))
            found = tables.find_tables(single.tobytes())
        except Exception:  # Camelot's own failure on an unusual page: no regions
            return []
        finally:
            single.close()
        return [layout.rounded(layout.from_table(t)) for t in found.get(0, [])]

    # -- the result ----------------------------------------------------------------------------
    def build(self, progress: Progress | None = None) -> Reading:
        """The result: every page read (where not yet), cleaned up by its plan, its text
        corrected where a person did; the reading carries the configuration.  The
        caller closes it."""
        self.read_all(progress)
        # made afresh from the original, so that the result does not depend on how often
        # a plan changed on the way
        doc = pymupdf.open("pdf", self.original.tobytes())
        for n in range(len(self.pages)):
            image = self._image(n)
            if image is not None:
                cleanup.put_page_image(doc, n, *image)
        for n in range(len(self.pages)):
            self.regions(n)  # found where not yet, so that the configuration holds them
        pages = [self._page_reading(doc, n) for n in range(len(self.pages))]
        plans = {n: p for n in range(len(self.pages)) if (p := self.active_plan(n)) is not None}
        found: dict[int, list[Table]] | None = {s.number: s.tables for s in pages}
        if not self.finds_tables() and not any(s.tables for s in pages):
            found = None  # not looked for
        return Reading(self.source, doc, plans, pages, self.reader_name(),
                       tables=found, config=self.config())

    def _page_reading(self, doc: pymupdf.Document, n: int) -> PageReading:
        """One page of the result: its text, and the tables of its table regions made
        from the words of that text (corrected where a person did)."""
        regions = self.regions(n)
        ocr = self.ocr_text(n)
        if ocr is None:
            text = read_text_layer(doc[n], n)
            return PageReading(n, text, False, regions=regions,
                               tables=_tables(regions, text))
        correction = self.pages[n].correction
        text, person = (ocr, [False] * len(ocr.words())) if correction is None \
            else align_correction(correction, ocr)
        found = _tables(regions, text)
        structure = None
        if self.options.structure:
            structure = analyse_page_structure(doc[n], ocr)
            structure.use_tables(ocr, [(r.box, [[c.text for c in row] for row in t.rows])
                                       for r, t in zip([r for r in regions if r.kind == "table"],
                                                       found, strict=True)])
        return PageReading(n, text, True, structure, person, regions=regions, tables=found)

    @property
    def corrected(self) -> list[int]:
        """The pages a person corrected (from 0)."""
        return [n for n, p in enumerate(self.pages) if p.correction is not None]


def _words_of(text: PageText) -> list[layout.Word]:
    """The words of a page text with their boxes (the union of their characters')."""
    words: list[layout.Word] = []
    for a, b in text.words():
        boxes = text.rects(a, b)
        if boxes:
            box = boxes[0]
            for r in boxes[1:]:
                box |= r
            words.append((text.text[a:b], (box.x0, box.y0, box.x1, box.y1)))
    return words


def _tables(regions: list[layout.Region], text: PageText) -> list[Table]:
    """The tables the table regions of a page make of its text, in their order."""
    words = _words_of(text)
    return [layout.table_of(r, words) for r in regions if r.kind == "table"]


def config_bytes(config: dict[str, Any]) -> bytes:
    """A configuration as optdoc writes it: JSON, the same bytes for the same content."""
    return (json.dumps(config, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
