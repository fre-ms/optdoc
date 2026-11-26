"""The preparation of one document, and its configuration document.

optdoc makes a photographed or scanned document faithful: every page upright, the sheet
in a photo found and unwarped in its true proportions, a tilt straightened, dark borders
and uneven light evened out, in the page's own colours.  Its configuration document
(``<stem>.optdoc.json``, format ``optdoc-config``) holds everything that decides the
result and nothing else (no paths, no times): the settings and the plan of every page,
marked as optdoc's suggestion or a person's decision.  It serves three ends:

- **Reproducing.**  The input and the document always give the same PDF, byte for byte:
  every page is prepared from its plan.
- **Resuming.**  The window (``optdoc edit``) saves the document and opens it again where
  the person stopped; the PDF optdoc writes carries it too (``optdoc.json``).
- **The steps after.**  Every page's **frame** is recorded with it: a fingerprint of where
  things lie on the prepared page (its size, and the turning, unwarping and straightening
  that made it).  ocrdoc, which reads optdoc's PDF, keeps what a person decided on a page
  as long as its frame stays the same, even when the page itself changed (more contrast).

The document names its input by its SHA-256; another file is refused ("config-mismatch").
optdoc always starts from the original, never from an earlier result.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf
from doccor import documents
from doccor.errors import DocError

from optdoc import __version__, cleanup
from optdoc import models as catalogue
from optdoc import orientation as upright
from optdoc.errors import OptdocError
from optdoc.loading import open_document

FORMAT = "optdoc-config"
FORMAT_VERSION = 2
SUFFIX = ".optdoc.json"
EMBEDDED = "optdoc.json"  # the name of the configuration document inside the PDF
DPI = 300  # the resolution pages are prepared at
SUGGESTION_DPI = 150  # the resolution the suggestion looks at a page with

Progress = Any  # a callable (page from 1, number of pages) -> None


@dataclass
class Options:
    """The settings that decide the result: the paper an image is placed on, photo or
    scan (None: told by each page), whether pages are prepared by optdoc's suggestion
    (``clean_up``) or left as they came unless a person prepares them, and how a page in
    colour is stored (``colour_pages``: "jpeg", the default, or "png", lossless)."""

    paper: str = "a4"
    photo: bool | None = None
    clean_up: bool = True
    colour_pages: str = "jpeg"

    def as_dict(self) -> dict[str, Any]:
        """The settings for the configuration document."""
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: Any) -> Options:
        """The settings from a configuration document; a value of the wrong kind is a
        "bad-config"."""
        if not isinstance(d, dict):
            raise OptdocError("bad-config", reason="field")
        options = cls()
        kinds: dict[str, tuple[type, ...]] = {
            "paper": (str,), "photo": (bool, type(None)), "clean_up": (bool,),
            "colour_pages": (str,)}
        for name, value in d.items():
            if name not in kinds:
                continue
            if not isinstance(value, kinds[name]) or (
                    name == "colour_pages" and value not in cleanup.COLOUR_PAGES):
                raise OptdocError("bad-config", reason="field")
            setattr(options, name, value)
        return options


@dataclass
class _Page:
    """The state of one page: its plan once decided (None: left as it came), whether a
    person decided it, and the models that took part in it where optdoc suggested it
    (``found_with``; the configuration document says so, and the result is made again
    without them); optdoc's suggestion (computed once) and the models that took part in
    that (``suggested_with``)."""

    decided: bool = False
    plan: cleanup.CleanupPlan | None = None
    by_person: bool = False
    found_with: list[str] = field(default_factory=list)
    suggestion: cleanup.CleanupPlan | None = field(default=None, repr=False)
    suggested_with: list[str] = field(default_factory=list)


def _copy(plan: cleanup.CleanupPlan | None) -> cleanup.CleanupPlan | None:
    """An independent copy of a plan (own lists of corners and masks)."""
    return None if plan is None else cleanup.CleanupPlan.from_dict(plan.full_dict())


def _plan_key(plan: cleanup.CleanupPlan | None) -> str:
    """A plan as a string that is equal for plans that make the same page."""
    if plan is None or not plan.active:
        return ""
    return json.dumps(plan.full_dict(), sort_keys=True)


def frame(page: pymupdf.Page, plan: cleanup.CleanupPlan | None) -> str:
    """The frame of a page: a fingerprint of where things lie on it once prepared by
    ``plan``, its size and what of the plan moves the page (a quarter turn, the sheet's
    corners, the tilt straightened), each rounded as the configuration stores it.  Light,
    contrast, colour and masks leave it as it is."""
    moved = cleanup.geometry_only(plan) if plan is not None and plan.active else None
    geometry = None if moved is None else {
        "rotation": moved.rotation,
        "corners": ([[round(x, 2), round(y, 2)] for x, y in moved.corners]
                    if moved.unwarp and moved.corners else None),
        "angle": round(moved.angle, 3) if moved.straighten and abs(moved.angle) >= 0.05
        else None}
    if geometry is not None and not geometry["rotation"] and geometry["corners"] is None \
            and geometry["angle"] is None:
        geometry = None  # a page only lit or cleaned lies where the page as it came lies
    rect = page.rect
    key = json.dumps({"size": [round(rect.width, 2), round(rect.height, 2)],
                      "geometry": geometry}, sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def load_config(path: str | Path) -> dict[str, Any]:
    """A configuration document from its file, or from the PDF optdoc wrote, which
    carries it.  Raises "missing", or "bad-config" (reason "json" or "format")."""
    try:
        return documents.load_document(path, FORMAT, FORMAT_VERSION, EMBEDDED, "optdoc")
    except DocError as e:  # optdoc's own, so that callers catch one kind of error
        reason = e.details.get("reason")
        raise (OptdocError(e.kind, reason=reason) if reason is not None
               else OptdocError(e.kind)) from e


def config_bytes(config: dict[str, Any]) -> bytes:
    """A configuration document as optdoc writes it: JSON, the same bytes for the same
    content."""
    return documents.document_bytes(config)


@dataclass
class Prepared:
    """The result of a project: the document with its pages prepared, the configuration
    that makes it again, and the pages (from 0) that were changed.  Call :meth:`close`
    when done."""

    source: Path
    doc: pymupdf.Document
    config: dict[str, Any]
    cleaned_up: list[int]
    unwarped: list[int]

    def close(self) -> None:
        """Close the document."""
        self.doc.close()


def reader() -> Any | None:
    """An OCR engine that tells an upside-down page from an upright one, where ocrdoc is
    installed (a provider, not a dependency): its engine of choice; None without."""
    try:
        from ocrdoc import ocr as ocrlib  # type: ignore[import-not-found]

        return ocrlib.backend("auto")
    except Exception:  # not installed, or no engine: the lines alone decide
        return None


class Project:
    """The preparation of one document; see the module.  Open with :meth:`open`, close
    with :meth:`close`.  Page numbers count from 0."""

    def __init__(self, source: Path, doc: pymupdf.Document, sha256: str, size: int,
                 options: Options) -> None:
        self.source = source
        self.original = doc  # every page upright, as it came
        self.sha256 = sha256
        self.size = size
        self.options = options
        self.pages = [_Page() for _ in range(len(doc))]
        self.models: Path | None = None  # the folder of models the suggestion may use
        self._layer: dict[int, bool] = {}
        self._images: dict[int, tuple[str, tuple[bytes, float, float]]] = {}

    # -- opening and saving --------------------------------------------------------------------
    @classmethod
    def open(cls, source: str | Path, options: Options | None = None,
             config: dict[str, Any] | None = None) -> Project:
        """A project on ``source`` (a photo, an image, a PDF): fresh with ``options``, or
        as ``config`` left it (whose settings then count).  Raises "config-mismatch" when
        the document belongs to another file, and what
        :func:`optdoc.loading.open_document` raises."""
        source = Path(source)
        if not source.is_file():
            raise OptdocError("missing")
        sha256 = documents.digest(source)
        if config is not None:
            named = config.get("input")
            if not isinstance(named, dict) or named.get("sha256") != sha256:
                raise OptdocError("config-mismatch")
            options = Options.from_dict(config.get("options", {}))
        options = options or Options()
        doc = open_document(source, options.paper)
        project = cls(source, doc, sha256, source.stat().st_size, options)
        if config is not None:
            try:
                project._take_pages(config.get("pages"))
            except Exception:
                project.close()
                raise
        return project

    def _take_pages(self, pages: Any) -> None:
        """The pages of a configuration document: one entry per page of the document."""
        if not isinstance(pages, list) or len(pages) != len(self.pages):
            raise OptdocError("bad-config", reason="page")
        for page, entry in zip(self.pages, pages, strict=True):
            if not isinstance(entry, dict) or entry.get("by") not in ("auto", "person"):
                raise OptdocError("bad-config", reason="field")
            plan = entry.get("plan")
            page.decided = True
            page.plan = None if plan is None else cleanup.CleanupPlan.from_dict(plan)
            page.by_person = entry["by"] == "person"
            used = entry.get("models", [])
            if not isinstance(used, list) or not all(isinstance(m, str) for m in used):
                raise OptdocError("bad-config", reason="field")
            page.found_with = list(used)

    def config(self) -> dict[str, Any]:
        """The configuration document: the input with every page's size, the settings,
        and per page its plan (the suggestion where none was decided; kept also where it
        does nothing, for the corners it found), who decided it, and its frame."""
        pages, sizes = [], []
        for n, page in enumerate(self.pages):
            plan = self.plan(n)
            rect = self.original[n].rect
            sizes.append({"width": round(rect.width, 3), "height": round(rect.height, 3)})
            entry: dict[str, Any] = {"page": n + 1,
                                     "plan": plan.full_dict() if plan is not None else None,
                                     "by": "person" if page.by_person else "auto",
                                     "frame": self.frame(n)}
            used = page.found_with if page.decided else page.suggested_with
            if used and plan is not None and not page.by_person:
                entry["models"] = list(used)  # what took part in the suggestion
            pages.append(entry)
        return {
            "format": FORMAT, "version": FORMAT_VERSION, "made_with": f"optdoc {__version__}",
            "input": {"sha256": self.sha256, "bytes": self.size,
                      "suffix": self.source.suffix.lower(), "pages": sizes},
            "options": self.options.as_dict(),
            "pages": pages,
        }

    def save(self, path: str | Path) -> Path:
        """Write the configuration document to ``path``; raises "unwritable"."""
        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(config_bytes(self.config()))
        except OSError as e:
            raise OptdocError("unwritable") from e
        return path

    def close(self) -> None:
        """Release the document."""
        self.original.close()

    # -- the pages -----------------------------------------------------------------------------
    def has_text_layer(self, n: int) -> bool:
        """True when the page as it came carries text of its own (it is born digital and
        left as it is)."""
        if n not in self._layer:
            self._layer[n] = bool(self.original[n].get_text("text").strip())
        return self._layer[n]

    def cleanable(self, n: int) -> bool:
        """True for a page without a text layer (a scan, a photo), when OpenCV is there."""
        return cleanup.available() and not self.has_text_layer(n)

    def suggestion(self, n: int) -> cleanup.CleanupPlan:
        """optdoc's suggestion for a page without a text layer (computed once); an empty
        plan for any other page."""
        page = self.pages[n]
        if page.suggestion is None:
            if self.cleanable(n):
                image, scale = cleanup.render(self.original[n], SUGGESTION_DPI)
                turn = self._model_turn(image)  # None without the model, or where it is not sure
                if turn:
                    image = cleanup.apply_plan(image, cleanup.CleanupPlan(rotation=turn))
                page.suggestion = cleanup.suggest(image, self.options.photo, scale)
                page.suggestion.rotation = turn or 0
                page.suggested_with = [] if turn is None else [catalogue.ORIENTATION.name]
            else:
                page.suggestion = cleanup.CleanupPlan()
        return _copy(page.suggestion) or cleanup.CleanupPlan()

    def _model_turn(self, image: Any) -> int | None:
        """The clockwise turn that puts the page upright as the orientation model sees it
        (:mod:`optdoc.orientation`); None where the model is not in the models folder, or
        is not sure."""
        model = catalogue.orientation(self.models)
        return None if model is None else upright.upright(image, model)

    def plan(self, n: int) -> cleanup.CleanupPlan | None:
        """The plan of a page, a copy: as decided, else the suggestion (unless the
        automatic preparation is off).  It may do nothing (every step off), and keeps
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

    def set_plan(self, n: int, plan: cleanup.CleanupPlan | None, by_person: bool = True) -> None:
        """Decide the plan of a page: a person's (``by_person``), or optdoc's suggestion
        taken back (with the models that took part in it)."""
        page = self.pages[n]
        page.decided = True
        page.plan = _copy(plan)
        page.by_person = by_person
        page.found_with = [] if by_person else list(page.suggested_with)

    def frame(self, n: int) -> str:
        """The frame of a page as its plan prepares it (:func:`frame`)."""
        return frame(self.original[n], self.plan(n))

    def _image(self, n: int) -> tuple[bytes, float, float] | None:
        """The prepared image of a page and the size of its page (computed once per
        plan); None for a page that is left as it came."""
        plan = self.active_plan(n)
        if plan is None:
            return None
        key = _plan_key(plan) + self.options.colour_pages
        if n not in self._images or self._images[n][0] != key:
            self._images[n] = (key, cleanup.cleaned_image(self.original[n], plan, DPI,
                                                          self.options.colour_pages))
        return self._images[n][1]

    def original_png(self, n: int, dpi: int = 100) -> bytes:
        """The page as it came, as PNG."""
        return self.original[n].get_pixmap(dpi=dpi, alpha=False).tobytes("png")

    def preview(self, n: int, plan: cleanup.CleanupPlan, dpi: int = 100) -> tuple[bytes, float]:
        """The page as ``plan`` would prepare it, as PNG, and its pixels per point
        (:func:`optdoc.cleanup.preview_png`)."""
        return cleanup.preview_png(self.original[n], plan, dpi)

    def cleaned_width(self, n: int, plan: cleanup.CleanupPlan) -> float:
        """The width in points of the page ``plan`` makes (a quarter turn swaps sides)."""
        rect = self.original[n].rect
        return rect.width if plan.rotation in (0, 180) else rect.height

    def orientation(self, n: int) -> int:
        """The quarter turns (clockwise, degrees) that put the page upright: as the
        orientation model sees it, where it lies in the models folder and is sure; else
        portrait or landscape from the page's lines, upside down where ocrdoc is installed
        to read it (:func:`reader`)."""
        image, _scale = cleanup.render(self.original[n], SUGGESTION_DPI)
        turn = self._model_turn(image)
        return turn if turn is not None else cleanup.estimate_orientation(image, reader())

    # -- the result ----------------------------------------------------------------------------
    @property
    def cleaned_up(self) -> list[int]:
        """The pages a plan changes (from 0)."""
        return [n for n in range(len(self.pages)) if self.active_plan(n) is not None]

    @property
    def decided_by_person(self) -> list[int]:
        """The pages whose plan a person decided (from 0)."""
        return [n for n, page in enumerate(self.pages) if page.by_person]

    def build(self, progress: Progress | None = None) -> Prepared:
        """The result: a copy of the input with every page its plan changes replaced by
        the prepared page.  The caller closes it."""
        doc = pymupdf.open("pdf", self.original.tobytes())
        try:
            for n in range(len(self.pages)):
                if progress is not None:
                    progress(n + 1, len(self.pages))
                image = self._image(n)
                if image is not None:
                    cleanup.put_page_image(doc, n, *image)
        except Exception:
            doc.close()
            raise
        unwarped = [n for n in self.cleaned_up
                    if (p := self.active_plan(n)) is not None and p.unwarp and p.corners]
        return Prepared(self.source, doc, self.config(), self.cleaned_up, unwarped)


__all__ = ["EMBEDDED", "FORMAT", "FORMAT_VERSION", "SUFFIX", "Options", "Prepared",
           "Project", "config_bytes", "frame", "load_config", "reader"]
