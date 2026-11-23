"""Character-level view of a page's text layer.

PyMuPDF's ``rawdict`` gives every character with its bounding box and
baseline.  We flatten that into one string per page plus parallel lists (box,
line id, font size, baseline per character) so that ordinary regular
expressions can be run over the page and every match can be mapped back to
rectangles for redaction.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from optdoc.errors import OptdocError

Box = tuple[float, float, float, float]

# A glyph of the text layer: character, box, font size, baseline y.
_Glyph = tuple[str, Box, float, float]

# Expand ligatures ("ﬁ" -> "f", "i") so that names match letter by letter.
_FLAGS = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_LIGATURES


@dataclass
class PageText:
    """Reconstructed text of one page with a box for every character."""

    number: int
    width: float
    height: float
    text: str = ""
    boxes: list[Box | None] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)
    sizes: list[float] = field(default_factory=list)
    baselines: list[float] = field(default_factory=list)
    line_boxes: dict[int, Box] = field(default_factory=dict)
    source: str = "text"  # "text" (PDF text layer) or "ocr"
    confidences: list[float] = field(default_factory=list)  # OCR word confidences
    word_spans: list[tuple[int, int]] = field(default_factory=list)  # OCR word offsets

    MIN_CHARS_TEXT_LAYER = 20

    @property
    def has_text_layer(self) -> bool:
        """True when the page carries enough real text to work without OCR."""
        return len("".join(self.text.split())) >= self.MIN_CHARS_TEXT_LAYER

    @property
    def uncertain_words(self) -> int:
        """Number of OCR words below 60 % confidence (0 for a text layer)."""
        return sum(1 for k in self.confidences if k < 0.6)

    def rects(self, start: int, end: int) -> list[pymupdf.Rect]:
        """Union of character boxes in ``[start, ende)``, one rectangle per line."""
        per_line: dict[int, pymupdf.Rect] = {}
        for i in range(start, min(end, len(self.text))):
            box = self.boxes[i]
            if box is None:
                continue
            r = pymupdf.Rect(box)
            z = self.lines[i]
            if z in per_line:
                per_line[z] |= r
            else:
                per_line[z] = r
        return [r for _, r in sorted(per_line.items())]

    def words(self) -> list[tuple[int, int]]:
        """Word spans: the OCR words, or runs of printed characters between whitespace."""
        if self.word_spans:
            return list(self.word_spans)
        spans: list[tuple[int, int]] = []
        start: int | None = None
        for i, c in enumerate(self.text + " "):
            printed = i < len(self.text) and not c.isspace() and self.boxes[i] is not None
            if printed and start is None:
                start = i
            elif not printed and start is not None:
                spans.append((start, i))
                start = None
        return spans

    def line_of(self, index: int) -> int:
        """Line id of the character at ``index``; -1 outside the text."""
        return self.lines[index] if 0 <= index < len(self.lines) else -1

    def font_size(self, start: int, end: int) -> float:
        """Median font size of the printed characters in ``[start, ende)``, 10 pt when
        the span holds none (whitespace only)."""
        sizes = sorted(
            self.sizes[i]
            for i in range(start, min(end, len(self.text)))
            if self.boxes[i] is not None
        )
        return sizes[len(sizes) // 2] if sizes else 10.0

    def baseline(self, start: int, end: int) -> float | None:
        """Baseline (y) of the first printed character of the match."""
        for i in range(start, min(end, len(self.text))):
            if self.boxes[i] is not None:
                return self.baselines[i]
        return None

    def free_space_right(self, end: int) -> float:
        """x coordinate of the next printed character on the same line after ``end``.

        Used to widen a redaction box so that the pseudonym stays legible when
        it is longer than the text it replaces.  Spaces count as free.
        """
        if end <= 0 or end > len(self.text):
            return self.width
        line_no = self.lines[end - 1]
        for k in range(end, len(self.text)):
            if self.lines[k] != line_no:
                break
            box = self.boxes[k]
            if box is None or self.text[k].isspace():
                continue
            return box[0]
        return self.width - 18.0

    def as_dict(self) -> dict[str, Any]:
        """Everything needed to rebuild the page without reading it again (the working
        state); boxes rounded to a hundredth of a point."""
        def rounded(b: Box | None) -> list[float] | None:
            """A box as a rounded list, ``None`` for whitespace."""
            return [round(v, 2) for v in b] if b is not None else None

        return {
            "number": self.number, "width": round(self.width, 2), "height": round(self.height, 2),
            "text": self.text, "source": self.source,
            "boxes": [rounded(b) for b in self.boxes], "lines": self.lines,
            "sizes": [round(g, 2) for g in self.sizes],
            "baselines": [round(b, 2) for b in self.baselines],
            "line_boxes": {str(z): rounded(b) for z, b in self.line_boxes.items()},
            "confidences": [round(k, 3) for k in self.confidences],
            "word_spans": [list(s) for s in self.word_spans],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PageText:
        """Rebuild a page from :meth:`as_dict`; missing lists default to empty, and a
        character list that does not match the text length raises an
        :class:`~optdoc.errors.OptdocError` of kind "page-text"."""
        page_text = cls(number=int(d["number"]), width=float(d["width"]), height=float(d["height"]),
                    text=str(d["text"]), source=str(d.get("source", "text")))
        page_text.boxes = _boxes_from(d.get("boxes", []))
        page_text.lines = [int(z) for z in d.get("lines", [])]
        page_text.sizes = [float(g) for g in d.get("sizes", [])]
        page_text.baselines = [float(b) for b in d.get("baselines", [])]
        page_text.line_boxes = _line_boxes_from(d.get("line_boxes", {}))
        page_text.confidences = [float(k) for k in d.get("confidences", [])]
        page_text.word_spans = [(int(a), int(b)) for a, b in d.get("word_spans", [])]
        if not page_text._char_lists_match():
            raise OptdocError("page-text", page=page_text.number + 1)
        return page_text

    def _char_lists_match(self) -> bool:
        """True when every per-character list has one entry per character of the text."""
        n = len(self.text)
        return all(len(items) == n
                   for items in (self.boxes, self.lines, self.sizes, self.baselines))

    def _append_char(
        self, chars: str, box: Box | None, line_no: int, size: float, baseline: float
    ) -> None:
        """Append ``chars`` with the same box, line, size and baseline for each of its
        characters, and grow the line's box when the glyph is printed."""
        for c in chars:
            self.text += c
            self.boxes.append(box)
            self.lines.append(line_no)
            self.sizes.append(size)
            self.baselines.append(baseline)
        if box is not None:
            old = self.line_boxes.get(line_no)
            if old is None:
                self.line_boxes[line_no] = box
            else:
                self.line_boxes[line_no] = (
                    min(old[0], box[0]), min(old[1], box[1]),
                    max(old[2], box[2]), max(old[3], box[3]),
                )


def _boxes_from(raw: list[Any]) -> list[Box | None]:
    """Character boxes from their JSON lists; ``None`` (whitespace) stays ``None``."""
    return [tuple(b) if b is not None else None for b in raw]


def _line_boxes_from(raw: dict[str, Any]) -> dict[int, Box]:
    """Line boxes keyed by line id from their JSON form; lines without a box are dropped."""
    return {int(z): tuple(b) for z, b in raw.items() if b is not None}


def _box(values: Sequence[float]) -> Box:
    """A rawdict ``bbox`` as a four-tuple of floats."""
    x0, y0, x1, y1 = (float(v) for v in values)
    return x0, y0, x1, y1


def _text_blocks(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """The text blocks of a rawdict page (type 0); image blocks carry no characters."""
    return [block for block in raw.get("blocks", []) if block.get("type") == 0]


def _glyphs(line: dict[str, Any]) -> Iterator[_Glyph]:
    """Every character of a rawdict line with its box, font size and baseline.

    A character without its own origin inherits the span's baseline, as does one
    whose origin sits at y = 0 (MuPDF reports that for some synthetic glyphs).
    """
    for span in line.get("spans", []):
        size = float(span.get("size", 10.0))
        span_base = float(span.get("origin", (0.0, 0.0))[1])
        for ch in span.get("chars", []):
            base = float(ch.get("origin", (0.0, span_base))[1]) or span_base
            yield ch["c"], _box(ch["bbox"]), size, base


def _word_gap(text: str, last: Box, box: Box, size: float) -> bool:
    """True when the gap between two neighbouring glyphs is a word space the text layer
    does not carry itself: wider than a quarter of the font size, and the text so far
    does not already end in a space."""
    return box[0] - last[2] > 0.25 * size and not text.endswith(" ")


def _read_line(page_text: PageText, line: dict[str, Any], line_no: int) -> None:
    """Append one rawdict line to the page: its glyphs, a space for every visible gap
    between them, and the line break."""
    last_box: Box | None = None
    for c, box, size, base in _glyphs(line):
        if last_box is not None and _word_gap(page_text.text, last_box, box, size):
            page_text._append_char(" ", None, line_no, size, base)
        page_text._append_char(c, box, line_no, size, base)
        last_box = box
    page_text._append_char("\n", None, line_no, 0.0, 0.0)


def read_text_layer(page: pymupdf.Page, number: int | None = None) -> PageText:
    """Flatten the page's text layer into a :class:`PageText`."""
    number = page.number if number is None else number
    page_text = PageText(number=number, width=page.rect.width, height=page.rect.height)
    raw = page.get_text("rawdict", flags=_FLAGS, sort=True)
    line_no = 0
    for block in _text_blocks(raw):
        for line in block.get("lines", []):
            line_no += 1
            _read_line(page_text, line, line_no)
        page_text._append_char("\n", None, line_no, 0.0, 0.0)
    return page_text


def read_text_layers(doc: pymupdf.Document) -> list[PageText]:
    """One :class:`PageText` per page of ``doc``, numbered from 0."""
    return [read_text_layer(page, i) for i, page in enumerate(doc.pages())]
