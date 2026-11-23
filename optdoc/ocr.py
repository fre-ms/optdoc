"""OCR for scanned pages and photos, delivered as a :class:`PageText`.

Two backends: RapidOCR (pure pip wheels, default when installed, Latin model
for German text) and Tesseract (system binary, ``deu``).  Both return words
with boxes in page points; :func:`page_text_from_words` turns them into the
same character map the text layer produces, so that recognition and
redaction do not care where the text came from.  Character boxes inside a
word are approximated by dividing the word box evenly.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

import pymupdf

from optdoc.errors import OCRError, OptdocError
from optdoc.offline import no_telemetry
from optdoc.pagetext import PageText
from optdoc.settings import load_settings

if TYPE_CHECKING:
    from rapidocr import RapidOCR

OCR_DPI = 300
MAX_PIXELS = 4000  # longest side; photos from phones are larger than needed
UNCERTAIN_CONFIDENCE = 0.6

Bounds = tuple[float, float, float, float]


@dataclass
class OCRWord:
    """One recognised word: its text, its box in page points and the engine's confidence."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float = 1.0  # 0..1


class OCRBackend(Protocol):
    """An OCR engine: turns a rendered page into words with boxes."""

    name: str

    def recognise(self, pix: pymupdf.Pixmap, scale: float) -> list[OCRWord]:
        """Words of the rendered page; coordinates already divided by ``scale``."""


def _render(page: pymupdf.Page, dpi: int = OCR_DPI,
             max_pixel: int = MAX_PIXELS) -> tuple[pymupdf.Pixmap, float]:
    """Render the page for OCR; returns the pixmap and the pixels-per-point scale."""
    scale = dpi / 72.0
    longest = max(page.rect.width, page.rect.height) * scale
    if longest > max_pixel:
        scale *= max_pixel / longest
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False,
                          colorspace=pymupdf.csRGB)
    return pix, scale


def _png(pix: pymupdf.Pixmap) -> bytes:
    """The pixmap as PNG bytes, the form Tesseract reads on its standard input."""
    return pix.tobytes("png")


def _image_from_pixmap(pix: pymupdf.Pixmap) -> Any:
    """The pixmap as a NumPy array, in BGR order for colour (what OpenCV and RapidOCR
    expect); a grey pixmap keeps its single channel."""
    import numpy as np

    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return np.ascontiguousarray(image[:, :, ::-1]) if pix.n == 3 else image


def preprocess(pix: pymupdf.Pixmap) -> pymupdf.Pixmap:
    """Median filter against salt-and-pepper noise; a no-op when Pillow is missing."""
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return pix
    image = Image.frombytes("RGB" if pix.n == 3 else "L", (pix.width, pix.height), pix.samples)
    image = image.filter(ImageFilter.MedianFilter(3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    new = pymupdf.Pixmap(buffer.getvalue())
    if new.n != 3 or new.alpha:
        new = pymupdf.Pixmap(pymupdf.csRGB, new) if new.n != 3 else pymupdf.Pixmap(new, 0)
    return new


# -- Tesseract -----------------------------------------------------------------------------------
_TESSERACT_PLACES = (
    "/opt/homebrew/bin/tesseract",  # Homebrew on Apple silicon
    "/usr/local/bin/tesseract",  # Homebrew on Intel, MacPorts, manual installs
    "/usr/bin/tesseract",  # apt, dnf, pacman
    "/snap/bin/tesseract",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def tesseract_program(path: str | None = None) -> str | None:
    """The system's Tesseract: configured path, PATH, then the usual install locations.

    Applications started from the Finder or a desktop menu get a minimal PATH
    without Homebrew or /usr/local, so the fixed locations matter.
    """
    candidates: list[str | None] = [path] if path else []
    candidates.append(shutil.which("tesseract"))
    candidates += list(_TESSERACT_PLACES)
    for k in candidates:
        if k and Path(k).is_file():
            return str(k)
    return None


def tesseract_languages(program: str) -> list[str]:
    """The language packs ``program --list-langs`` reports; empty when it cannot run."""
    try:
        run = subprocess.run([program, "--list-langs"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    lines = (run.stdout + run.stderr).splitlines()
    return [z.strip() for z in lines if z.strip() and not z.lower().startswith("list of")
            and " " not in z.strip()]


def _words_from_tsv(tsv: str, scale: float, offset: tuple[float, float]) -> list[OCRWord]:
    """Tesseract's TSV output as words in page points: the word rows (level 5) with
    text, shifted by ``offset`` pixels; rows with unreadable numbers are skipped."""
    dx, dy = offset
    words: list[OCRWord] = []
    for line in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (line.get("text") or "").strip()
        if not text or line.get("level") != "5":
            continue
        try:
            x, y = float(line["left"]) + dx, float(line["top"]) + dy
            w, h = float(line["width"]), float(line["height"])
            conf = float(line.get("conf") or 0) / 100.0
        except (KeyError, ValueError):
            continue
        words.append(OCRWord(text, x / scale, y / scale, (x + w) / scale, (y + h) / scale,
                               max(0.0, conf)))
    return words


class TesseractBackend:
    """Tesseract with ``--psm 3`` for the page and, when asked for, a second pass for
    tables: Tesseract's layout analysis takes a boxed grid for graphics and drops the
    cells (a bordered medication table came back as a single word).  For every grid
    :func:`cleanup.grid_areas` finds, the crop is read again without its rules
    as one block (``--psm 6``); the reading with the higher confidence mass wins the box.
    Measured on synthetic bordered tables at 200 dpi: 0 of 45 cell words → 42; pages
    without grids are untouched."""

    name = "tesseract"

    def __init__(self, language: str | None = None, program: str | None = None,
                 tables: bool = True) -> None:
        """Locate the program and settle the language packs: the ones given, else the
        configured ones, else whatever of ``deu`` and ``eng`` is installed (``eng`` as
        the last resort).  Raises :class:`OCRError` without a program."""
        self.tables = tables
        settings = load_settings()
        found = tesseract_program(program or settings.tesseract_path or None)
        if not found:
            raise OCRError("no-reader", reader="tesseract")
        self.program = found
        wanted = language or settings.tesseract_languages
        installed = set(tesseract_languages(self.program))
        if wanted:
            self.language = wanted
        else:
            present = [s for s in ("deu", "eng") if s in installed]
            self.language = "+".join(present) if present else "eng"

    @staticmethod
    def available() -> bool:
        """True when a Tesseract program is found (configured path, PATH or usual places)."""
        return tesseract_program(load_settings().tesseract_path or None) is not None

    def recognise(self, pix: pymupdf.Pixmap, scale: float) -> list[OCRWord]:
        """Words of the page from the ``--psm 3`` run, revised inside table grids when
        the second pass is switched on."""
        words = self._run(_png(pix), "3", scale)
        if self.tables:
            words = self._reread_tables(pix, scale, words)
        return words

    def _run(self, png: bytes, psm: str, scale: float,
              offset: tuple[float, float] = (0.0, 0.0)) -> list[OCRWord]:
        """One Tesseract run on PNG bytes, handed over on standard input so that no image
        of the page is ever written to a file; ``offset`` (pixels) places a crop on the
        page.  Tesseract's own messages are not passed on: they may quote the page."""
        try:
            run = subprocess.run(
                [self.program, "stdin", "-", "-l", self.language, "--psm", psm, "tsv"],
                input=png, capture_output=True, check=False, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise OCRError("reader-failed", reader="tesseract") from e
        if run.returncode != 0:
            raise OCRError("reader-failed", reader="tesseract")
        return _words_from_tsv(run.stdout.decode("utf-8", "replace"), scale, offset)

    def _reread_tables(self, pix: pymupdf.Pixmap, scale: float,
                            words: list[OCRWord]) -> list[OCRWord]:
        """The second pass: every table grid on the page is read again without its
        rules as one block, and the better reading replaces the words in the grid's box.
        Needs OpenCV; without it the words come back unchanged."""
        from optdoc import cleanup

        if not cleanup.available():
            return words
        image = _image_from_pixmap(pix)
        margin, padding = 10, 30
        for grid in cleanup.grid_areas(image):
            x0, y0, x1, y1 = _with_margin(grid, margin, pix.width, pix.height)
            png = _grid_png(image[y0:y1, x0:x1], padding)
            if png is None:
                continue
            new = self._run(png, "6", scale, (x0 - padding, y0 - padding))
            bounds = (x0 / scale, y0 / scale, x1 / scale, y1 / scale)
            words = _better_reading(words, new, bounds)
        return words


def _with_margin(grid: tuple[int, int, int, int], margin: int, width: int,
              height: int) -> tuple[int, int, int, int]:
    """The grid's pixel box widened by ``margin`` on every side and clamped to the image."""
    x0, y0, x1, y1 = grid
    return (max(0, x0 - margin), max(0, y0 - margin),
            min(width, x1 + margin), min(height, y1 + margin))


def _grid_png(crop: Any, padding: int) -> bytes | None:
    """The crop of a table grid as PNG for the second pass: rules removed and a white
    border of ``padding`` pixels added, so Tesseract sees a free-standing text block.
    None when OpenCV cannot encode the image."""
    import cv2

    from optdoc import cleanup

    without = cleanup.without_lines(crop)
    white = (255, 255, 255) if without.ndim == 3 else 255
    without = cv2.copyMakeBorder(without, padding, padding, padding, padding, cv2.BORDER_CONSTANT,
                              value=white)
    ok, png = cv2.imencode(".png", without)
    return png.tobytes() if ok else None


def _better_reading(words: list[OCRWord], new: list[OCRWord], bounds: Bounds) -> list[OCRWord]:
    """The page words with those inside ``bounds`` replaced by ``new`` when the new
    reading carries the higher confidence mass; otherwise the words unchanged."""
    inside = [w for w in words if _inside(w, bounds)]
    if _confidence_mass(new) <= _confidence_mass(inside):
        return words
    return [w for w in words if w not in inside] + new


def _inside(w: OCRWord, bounds: Bounds) -> bool:
    """True when the word's box lies entirely inside ``bounds`` (page points)."""
    x0, y0, x1, y1 = bounds
    return w.x0 >= x0 and w.y0 >= y0 and w.x1 <= x1 and w.y1 <= y1


def _confidence_mass(words: Iterable[OCRWord]) -> float:
    """Confidence weighted by length, letters and digits only: the better of two
    readings of the same box."""
    return sum(w.confidence * len(w.text) for w in words if any(c.isalnum() for c in w.text))


# -- RapidOCR ------------------------------------------------------------------------------------
class RapidOCRBackend:
    """RapidOCR (ONNX models from the wheel, no download) with the language model asked
    for; the bundled default model takes over when the language model is unknown to
    the installed version or fails on first use."""

    name = "rapidocr"
    # RapidOCR's text-line classifier is meant to turn upside-down lines round before
    # reading them.  It also turns upright ones: "Medikation: Ramipril 5 mg 1-0-0, ..."
    # came back as "Mebt t -- t --1 t tn te.." (rapidocr 3.10.0, onnxruntime 1.31 and
    # 1.32).  Measured on the synthetic report (similarity to the true text, page 1 and
    # 2): clean 200 dpi 0.936/1.0 with it, 1.0/1.0 without; noisy 150 dpi 0.997/0.856
    # against 0.997/1.0; never worse without.  So it is off; an upside-down page is a
    # matter for estimate_orientation and the plan's rotation.
    turn_lines = False

    def __init__(self, language: str | None = "de") -> None:
        """Start the engine for ``language`` (a RapidOCR ``lang_type``), else the default."""
        no_telemetry()  # before ONNX Runtime is loaded, or it is too late
        try:
            from rapidocr import RapidOCR
        except ImportError as e:
            raise OCRError("no-reader", reader="rapidocr") from e
        self._RapidOCR = RapidOCR
        self._params = {"Global.log_level": "error"}
        language_model = self._language_model(language)
        self._default = language_model is None
        self._engine = (language_model if language_model is not None
                        else RapidOCR(params=self._params))

    def _language_model(self, language: str | None) -> RapidOCR | None:
        """The engine with ``Rec.lang_type`` set, or None when no language was asked
        for or RapidOCR refuses it at start-up."""
        if not language:
            return None
        try:
            return self._RapidOCR(params={**self._params, "Rec.lang_type": language})
        except Exception:
            return None

    @staticmethod
    def available() -> bool:
        """True when the ``rapidocr`` package is installed; it is not loaded for that,
        which takes a second or two."""
        return importlib.util.find_spec("rapidocr") is not None

    def recognise(self, pix: pymupdf.Pixmap, scale: float) -> list[OCRWord]:
        """Words of the page: the engine's own word boxes where it gives them, else its
        text lines split into words by character share."""
        return _words_from_result(self._recognition(_image_from_pixmap(pix)), scale)

    def _recognition(self, image: Any) -> Any:
        """The engine's result for the image.  The language model is loaded lazily;
        when it is unsupported or missing, the first page fails and the bundled default
        model takes over for good."""
        try:
            return self._engine(image, return_word_box=True, use_cls=self.turn_lines)
        except OptdocError:
            raise  # the network guard, for one: its kind says more than "failed"
        except Exception as e:
            if self._default:
                raise OCRError("reader-failed", reader="rapidocr") from e
        self._engine = self._RapidOCR(params=self._params)
        self._default = True
        try:
            return self._engine(image, return_word_box=True, use_cls=self.turn_lines)
        except OptdocError:
            raise
        except Exception as e:
            raise OCRError("reader-failed", reader="rapidocr") from e


def _words_from_result(result: Any, scale: float) -> list[OCRWord]:
    """RapidOCR's output as words in page points: for every text line the engine's
    word boxes when it reports them, otherwise the line box split by character share."""
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return []
    word_boxes = getattr(result, "word_results", None) or ()
    words: list[OCRWord] = []
    for i, (box, text, score) in enumerate(zip(boxes, result.txts, result.scores,
                                               strict=False)):
        if i < len(word_boxes) and word_boxes[i]:
            words.extend(_words_from_word_boxes(word_boxes[i], scale))
        else:
            line = OCRWord(str(text).strip(), *_bounds(box, scale), float(score))
            words.extend(_split_line(line))
    return words


def _bounds(points: Iterable[Any], scale: float) -> Bounds:
    """Bounding box of a polygon in page points: pixel corners divided by ``scale``."""
    xs = [float(pt[0]) for pt in points]
    ys = [float(pt[1]) for pt in points]
    return min(xs) / scale, min(ys) / scale, max(xs) / scale, max(ys) / scale


def _words_from_word_boxes(word_boxes: Iterable[Any], scale: float) -> list[OCRWord]:
    """The engine's ``(word, score, polygon)`` triples of one line as words, blanks dropped."""
    return [OCRWord(str(word).strip(), *_bounds(wbox, scale), float(word_score))
            for word, word_score, wbox in word_boxes if str(word).strip()]


def _split_line(line: OCRWord) -> list[OCRWord]:
    """RapidOCR returns text lines; split into words with boxes by character share."""
    parts = line.text.split()
    if len(parts) <= 1:
        return [line] if line.text else []
    total = len(line.text)
    width = line.x1 - line.x0
    words: list[OCRWord] = []
    pos = 0
    for part in parts:
        start = line.text.index(part, pos)
        end = start + len(part)
        pos = end
        words.append(OCRWord(part, line.x0 + width * start / total, line.y0,
                               line.x0 + width * end / total, line.y1, line.confidence))
    return words


# -- selection -----------------------------------------------------------------------------------
_BACKEND_NAMES = ("rapidocr", "tesseract", "none")


def _preferred_backend(name: str) -> str:
    """The name "auto" resolved to the configured preference (``OPTDOC_OCR``, or what
    the calling application set) when that names an engine or "none"; any other name
    unchanged."""
    if name != "auto":
        return name
    preferred = (load_settings().ocr_backend or "auto").lower()
    return preferred if preferred in _BACKEND_NAMES else name


def _first_available(languages: str | None, tables: bool) -> OCRBackend | None:
    """RapidOCR when installed, else Tesseract, else None.  ``languages`` only reaches
    the engine whose notation it uses: "+" joins Tesseract packs, a single word is a
    RapidOCR language type."""
    if RapidOCRBackend.available():
        return RapidOCRBackend(languages if languages and "+" not in languages else "de")
    if TesseractBackend.available():
        return TesseractBackend(language=languages if languages and "+" in languages else None,
                                tables=tables)
    return None


def backend(name: str = "auto", languages: str | None = None,
            tables: bool = True) -> OCRBackend | None:
    """Return the requested backend, or for "auto" the configured preference
    (``OPTDOC_OCR``, or what the calling application set), else the first
    available one; None for "none".  ``languages`` names the language packs:
    "deu+eng" for Tesseract, a RapidOCR language type such as "de" or "latin";
    ``tables`` switches Tesseract's second pass for table grids."""
    name = _preferred_backend((name or "auto").lower())
    languages = (languages or "").strip() or None
    options: dict[str, Callable[[], OCRBackend | None]] = {
        "none": lambda: None,
        "rapidocr": lambda: RapidOCRBackend(languages or "de"),
        "tesseract": lambda: TesseractBackend(language=languages, tables=tables),
        "auto": lambda: _first_available(languages, tables),
    }
    if name not in options:
        raise OCRError("unknown-reader", name=name)
    return options[name]()


def available_backends() -> list[str]:
    """Names of the installed engines in order of preference: "rapidocr", "tesseract"."""
    names = []
    if RapidOCRBackend.available():
        names.append("rapidocr")
    if TesseractBackend.available():
        names.append("tesseract")
    return names


# -- words -> PageText ---------------------------------------------------------------------------
CELL_GAP = 1.0  # in word heights: a wider gap is no word space but a cell boundary


def _cell_boundary(space: float, line_height: float) -> bool:
    """True for a gap wider than the word is high: no word space (a quarter to half an em)
    but the boundary of a table cell or a column.  Measured on invented laboratory
    reports in three layouts: the former rule, a gap far wider than the page's usual one,
    found no boundary at all in two of them, whose gaps are mostly column gaps."""
    return space > CELL_GAP * line_height


def _same_line(w: OCRWord, ref: OCRWord) -> bool:
    """True when the word's vertical centre falls into the reference word's band and
    both heights are of the same order, so a heading is not pulled into a body line."""
    middle = (w.y0 + w.y1) / 2
    height, ref_height = w.y1 - w.y0, ref.y1 - ref.y0
    return ref.y0 - 1 <= middle <= ref.y1 + 1 and abs(height - ref_height) < max(height, ref_height)


def _lines_from_words(words: Iterable[OCRWord]) -> list[list[OCRWord]]:
    """Words grouped into lines, left to right: a word joins the line whose last word
    lies to its left and shares its height (:func:`_same_line`), the closest such line,
    else it starts a line.  So a line follows a slight tilt word by word, where the band
    of its first word loses the far end: a table row 450 pt wide, tilted by 1.2° (less
    than optdoc straightens), drops by a whole line height.  The lines top to bottom,
    the words of a line left to right; blank words dropped."""
    lines: list[list[OCRWord]] = []
    for w in sorted((w for w in words if w.text), key=lambda w: (w.x0, w.y0)):
        slack = 0.5 * (w.y1 - w.y0)  # neighbouring boxes may overlap a little
        candidates = [z for z in lines if z[-1].x1 <= w.x0 + slack and _same_line(w, z[-1])]
        if candidates:
            middle = (w.y0 + w.y1) / 2
            min(candidates, key=lambda z: abs((z[-1].y0 + z[-1].y1) / 2 - middle)).append(w)
        else:
            lines.append([w])
    lines.sort(key=lambda z: (min(w.y0 for w in z), z[0].x0))
    return lines


def _append_word(page_text: PageText, w: OCRWord, line_no: int) -> None:
    """Append the word's characters to line ``line_no`` with boxes from an even split of the
    word box, then record the word's confidence and its span in the page text."""
    n = max(len(w.text), 1)
    step = (w.x1 - w.x0) / n
    size = max(w.y1 - w.y0, 1.0) * 0.8
    baseline = w.y1 - 0.2 * (w.y1 - w.y0)
    start = len(page_text.text)
    for k, c in enumerate(w.text):
        box = (w.x0 + k * step, w.y0, w.x0 + (k + 1) * step, w.y1)
        page_text._append_char(c, box, line_no, size, baseline)
    page_text.confidences.append(w.confidence)
    page_text.word_spans.append((start, len(page_text.text)))


def page_text_from_words(
    words: Iterable[OCRWord], number: int, width: float, height: float
) -> PageText:
    """Group words into lines by vertical overlap, order them, and build the character map.
    A gap wider than the word is high (table cells, columns) becomes a tab in the page
    text: the rules treat it like a space, the Markdown structuring reads it as a cell
    boundary, and the text layer leaves the gap open there (:mod:`optdoc.textlayer`)."""
    page_text = PageText(number=number, width=width, height=height, source="ocr")
    for line_no, line in enumerate(_lines_from_words(words), 1):
        for i, w in enumerate(line):
            if i > 0:
                cell_boundary = _cell_boundary(w.x0 - line[i - 1].x1, w.y1 - w.y0)
                page_text._append_char("\t" if cell_boundary else " ", None, line_no,
                                       w.y1 - w.y0, w.y1)
            _append_word(page_text, w, line_no)
        page_text._append_char("\n", None, line_no, 0.0, 0.0)
    return page_text


# -- unreadable lines ------------------------------------------------------------------------------
class _WordSpan(NamedTuple):
    """An OCR word's offsets in the page text and whether it counts as uncertain."""

    start: int
    end: int
    uncertain: bool


def _word_uncertain(text: str, confidence: float) -> bool:
    """True below the confidence threshold, or for a lone letter (punctuation aside)
    that is not read with near certainty: a fragment of a word OCR could not read."""
    core = text.strip(",.;:()*\"'")
    if confidence < UNCERTAIN_CONFIDENCE:
        return True
    # a lone letter in the middle of a line is a fragment of a word OCR could not read
    return len(core) == 1 and core.isalpha() and confidence < 0.995


def _words_per_line(page_text: PageText) -> dict[int, list[_WordSpan]]:
    """The page's OCR words grouped by line, in text order, each judged for certainty."""
    per_line: dict[int, list[_WordSpan]] = {}
    for (a, b), conf in zip(page_text.word_spans, page_text.confidences, strict=True):
        spans = _WordSpan(a, b, _word_uncertain(page_text.text[a:b], conf))
        per_line.setdefault(page_text.line_of(a), []).append(spans)
    return per_line


def _line_unreadable(words: list[_WordSpan], min_share: float) -> bool:
    """True for a line with at least three uncertain words, or with a share of them
    at or above ``min_share``; a single uncertain word only counts when it is the
    whole line.  Confidently "read" fragments next to garbage are garbage too, so the
    whole line is taken."""
    uncertain = sum(1 for w in words if w.uncertain)
    if uncertain == 0:
        return False
    many = uncertain >= 3 or uncertain / len(words) >= min_share
    return many and (uncertain >= 2 or len(words) == 1)


@dataclass
class UnreadableLine:
    """A line OCR could not read: its page, its span ``[start, ende)`` in the page text,
    that text, its boxes in page points and the font size the line was set in."""

    page_number: int
    start: int
    end: int
    text: str
    rects: list[Bounds]
    font_size: float


def _unreadable_line(page_text: PageText, a: int, b: int) -> UnreadableLine:
    """The unreadable line covering the page text ``[a, b)``."""
    return UnreadableLine(
        page_number=page_text.number, start=a, end=b, text=page_text.text[a:b],
        rects=[(r.x0, r.y0, r.x1, r.y1) for r in page_text.rects(a, b)],
        font_size=page_text.font_size(a, b),
    )


def unreadable_lines(page_text: PageText, min_share: float = 0.4) -> list[UnreadableLine]:
    """Lines OCR could not read (many uncertain words or fragments).

    What cannot be read cannot be checked: such a line may hold a name, a date
    or handwriting.  A caller decides what to do with it; a pseudonymiser covers
    the whole line.
    """
    if page_text.source != "ocr" or not page_text.word_spans:
        return []
    return [_unreadable_line(page_text, words[0].start, words[-1].end)
            for words in _words_per_line(page_text).values()
            if _line_unreadable(words, min_share)]


# -- page ------------------------------------------------------------------------------------------
def _filtered(pix: pymupdf.Pixmap, filter_: Callable[[Any], Any]) -> pymupdf.Pixmap:
    """The rendering after the NumPy filter, back as an RGB pixmap; a grey result is
    spread over three channels."""
    import numpy as np

    image = filter_(_image_from_pixmap(pix))
    if image.ndim == 2:
        image = np.repeat(image[:, :, None], 3, axis=2)
    else:
        image = image[:, :, ::-1]
    image = np.ascontiguousarray(image)
    return pymupdf.Pixmap(pymupdf.csRGB, image.shape[1], image.shape[0], image.tobytes(), False)


def recognise_page(page: pymupdf.Page, backend_: OCRBackend, number: int | None = None,
                  dpi: int = OCR_DPI, preprocessing: bool = True,
                  max_pixel: int = MAX_PIXELS, filter_=None) -> PageText:
    """OCR of one page.  ``filter_`` (NumPy BGR image -> image) runs on the rendering
    before the engine, for the letter-aware finish of upscaled pages."""
    pix, scale = _render(page, dpi, max_pixel)
    if preprocessing:
        pix = preprocess(pix)
    if filter_ is not None:
        pix = _filtered(pix, filter_)
    words = backend_.recognise(pix, scale)
    number = page.number if number is None else number
    return page_text_from_words(words, number, page.rect.width, page.rect.height)


def needs_ocr(page: pymupdf.Page, text_layer: PageText, min_share: float = 0.2) -> bool:
    """True without a text layer, or when images cover a good part of the page
    (a scanned letter embedded in a PDF with a text layer)."""
    if not text_layer.has_text_layer:
        return True
    area = 0.0
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if r.width > 40 and r.height > 40:
            area += r.width * r.height
    return area >= min_share * page.rect.width * page.rect.height
