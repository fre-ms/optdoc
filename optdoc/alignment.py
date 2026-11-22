"""Boxes for a corrected or restructured OCR text.

The user may correct the recognised text, and the structured Markdown joins and
rewraps lines.  The invisible text layer of the output must still sit on the image
words, so that a reader selects text exactly where it is printed.  This module aligns
the words of such a text to the OCR words (longest common subsequence on normalised
words), gives every word the box of its OCR counterpart, splits or merges boxes where
the counts differ, and places words without counterpart between or after their
neighbours.  Markdown markup (``**``, ``|``, ``#``, list dashes) gets no box and no
place in the layer.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from itertools import groupby

import pymupdf

from optdoc.pagetext import PageText

_WORD = re.compile(r"\S+")
_MARKUP = re.compile(r"^[#*_>|`~=-]+$")
_EDGE = "*_`#|>"
_LEFT_MARGIN = 36.0  # left margin (pt) of lines invented for words without any anchor


@dataclass(frozen=True)
class _Run:
    """A run of consecutive corrected words without an OCR counterpart, framed by the
    boxes of the matched words before and after it (``None`` at the page's ends)."""

    start: int
    end: int
    lengths: tuple[int, ...]
    previous: pymupdf.Rect | None
    following: pymupdf.Rect | None


def _core(token: str) -> tuple[int, int]:
    """Start and end of the token's text without the surrounding Markdown markup."""
    a, b = 0, len(token)
    while a < b and token[a] in _EDGE:
        a += 1
    while b > a and token[b - 1] in "*_`|":
        b -= 1
    return a, b


def _key(word: str) -> str:
    """Comparison key of a word: letters and digits only, case folded."""
    return re.sub(r"[\W_]+", "", word).casefold()


def _box(page_text: PageText, a: int, b: int) -> pymupdf.Rect | None:
    """Union of the character boxes of ``page_text.text[a:b]``, ``None`` without any box."""
    rects = page_text.rects(a, b)
    if not rects:
        return None
    r = pymupdf.Rect(rects[0])
    for q in rects[1:]:
        r |= q
    return r


def text_layer_from_correction(text: str, ocr: PageText) -> PageText:
    """A page text whose string is ``text`` and whose boxes come from ``ocr``."""
    tokens = _word_spans(text)
    boxes = _aligned_boxes(text, tokens, ocr)
    _place_rest(tokens, boxes, ocr)
    return _page_text(text, tokens, boxes, ocr)


def _word_spans(text: str) -> list[tuple[int, int]]:
    """Spans of the words of ``text`` that belong in the layer: markup tokens are
    skipped, the markup around the remaining words is stripped."""
    spans: list[tuple[int, int]] = []
    for m in _WORD.finditer(text):
        tok = m.group(0)
        if _MARKUP.match(tok):
            continue
        a, b = _core(tok)
        if a < b:
            spans.append((m.start() + a, m.start() + b))
    return spans


def _ocr_words(ocr: PageText) -> tuple[list[str], list[pymupdf.Rect]]:
    """Comparison keys and boxes of the OCR words that have a printed box."""
    pairs = [(_key(ocr.text[a:b]), _box(ocr, a, b)) for a, b in ocr.words()]
    valid = [(s, r) for s, r in pairs if r is not None and not r.is_empty]
    return [s for s, _ in valid], [r for _, r in valid]


def _word_lengths(tokens: list[tuple[int, int]], indices: range | list[int]) -> list[int]:
    """Character count of the listed words, at least one so that every share has width."""
    return [max(1, tokens[k][1] - tokens[k][0]) for k in indices]


def _aligned_boxes(
    text: str, tokens: list[tuple[int, int]], ocr: PageText
) -> list[pymupdf.Rect | None]:
    """A box for every word with an OCR counterpart (longest common subsequence of the
    comparison keys), ``None`` for the rest; a replaced stretch shares out the boxes of
    the OCR words it replaces."""
    key_text = [_key(text[a:b]) for a, b in tokens]
    key_ocr, ocr_boxes = _ocr_words(ocr)
    boxes: list[pymupdf.Rect | None] = [None] * len(tokens)
    sm = difflib.SequenceMatcher(None, key_text, key_ocr, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            boxes[i1:i2] = ocr_boxes[j1:j2]
        elif tag == "replace":
            lengths = _word_lengths(tokens, range(i1, i2))
            boxes[i1:i2] = _shared_boxes(lengths, ocr_boxes[j1:j2])
    return boxes


def _shared_boxes(lengths: list[int], ocr_boxes: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """n corrected words for m OCR words: share the boxes out in order; when several
    words fall on one OCR word, its box is split by word length."""
    n, m = len(lengths), len(ocr_boxes)
    clusters: dict[tuple[int, int], list[int]] = {}
    for k in range(n):
        ja = (k * m) // n
        jb = max(ja + 1, ((k + 1) * m) // n)
        clusters.setdefault((ja, jb), []).append(k)
    boxes: dict[int, pymupdf.Rect] = {}
    for (ja, jb), indices in clusters.items():
        merged = _line_union(ocr_boxes[ja:jb])
        parts = _split_by_length(merged, [lengths[k] for k in indices])
        boxes.update(zip(indices, parts, strict=True))
    return [boxes[k] for k in range(n)]


def _line_union(boxes: list[pymupdf.Rect]) -> pymupdf.Rect:
    """Union of the boxes on the line of the first one; a word joined across lines
    keeps the first box."""
    merged = pymupdf.Rect(boxes[0])
    highest = merged.height
    for r in boxes[1:]:
        if r.y0 < merged.y1 + highest * 0.5 and r.y1 > merged.y0 - highest * 0.5:
            merged |= r
    return merged


def _split_by_length(box: pymupdf.Rect, lengths: list[int]) -> list[pymupdf.Rect]:
    """``box`` cut into one piece per word, the widths proportional to the word lengths."""
    total = sum(lengths)
    return _row(box.x0, box.y0, box.y1, [box.width * length / total for length in lengths])


def _row(
    x: float, y0: float, y1: float, widths: list[float], gap: float = 0.0
) -> list[pymupdf.Rect]:
    """Boxes of the given widths laid side by side from ``x``, ``gap`` apart."""
    rects = []
    for width in widths:
        rects.append(pymupdf.Rect(x, y0, x + width, y1))
        x += width + gap
    return rects


def _place_rest(
    tokens: list[tuple[int, int]], boxes: list[pymupdf.Rect | None], ocr: PageText
) -> None:
    """Words without an OCR counterpart: between their neighbours on the same line,
    else after the previous word (wrapping to a new line below), else before the next."""
    height = _line_height(boxes) or max(ocr.height / 60.0, 8.0)
    for run in _runs(tokens, boxes):
        rects = _between_neighbours(run, height)
        if rects is None:
            rects = _after_anchor(run, height, ocr.width)
        boxes[run.start:run.end] = rects


def _runs(tokens: list[tuple[int, int]], boxes: list[pymupdf.Rect | None]) -> list[_Run]:
    """The runs of consecutive words without a box, each with its neighbours' boxes.
    The neighbours are matched words, so the runs are independent of each other."""
    runs: list[_Run] = []
    for without_box, cluster in groupby(range(len(boxes)), key=lambda k: boxes[k] is None):
        if not without_box:
            continue
        indices = list(cluster)
        start, end = indices[0], indices[-1] + 1
        runs.append(_Run(start, end, tuple(_word_lengths(tokens, indices)),
                            previous=boxes[start - 1] if start > 0 else None,
                            following=boxes[end] if end < len(boxes) else None))
    return runs


def _on_one_line(previous: pymupdf.Rect, following: pymupdf.Rect, height: float) -> bool:
    """True when ``following`` follows ``previous`` on the same line with a gap between them."""
    same_line = abs(following.y0 - previous.y0) < 0.6 * height
    return same_line and following.x0 - previous.x1 > 0.05 * height


def _between_neighbours(run: _Run, height: float) -> list[pymupdf.Rect] | None:
    """Boxes for the run in the gap between its neighbours, ``None`` when the run has
    no neighbour on either side or the neighbours do not share a line.  However narrow
    the gap: the words have no printed counterpart, what matters is that they stay in
    reading order."""
    previous, following = run.previous, run.following
    if previous is None or following is None or not _on_one_line(previous, following, height):
        return None
    space = following.x0 - previous.x1
    total = sum(run.lengths) + (len(run.lengths) + 1) * 0.5
    padding = space * 0.5 / total
    widths = [space * length / total for length in run.lengths]
    return _row(previous.x1 + padding, previous.y0, previous.y1, widths, padding)


def _start_point(run: _Run, height: float) -> tuple[float, float, pymupdf.Rect]:
    """Where a run without a gap to sit in starts (x, y0), and the box whose height it
    borrows: after the previous word, else before the next word, else on an invented
    first line at the top left of the page."""
    if run.previous is not None:
        return run.previous.x1 + 0.3 * height, run.previous.y0, run.previous
    if run.following is not None:
        following = run.following
        x = max(0.0, following.x0 - 0.3 * height - 0.55 * height * sum(run.lengths))
        return x, following.y0, following
    anchor = pymupdf.Rect(_LEFT_MARGIN, 36 - 1.2 * height, _LEFT_MARGIN, 36 - 0.2 * height)
    return anchor.x0, anchor.y1 + 0.2 * height, anchor


def _after_anchor(run: _Run, height: float, page_width: float) -> list[pymupdf.Rect]:
    """Boxes for the run laid out from its start point, 0.55 line heights per character,
    wrapping to a new line below at the page's right edge."""
    x, y0, anchor = _start_point(run, height)
    h = anchor.height if anchor.height > 0 else height
    rects = []
    for length in run.lengths:
        width = 0.55 * h * length
        if page_width and x + width > page_width - 10 and x > _LEFT_MARGIN:
            x, y0 = _LEFT_MARGIN, y0 + 1.2 * h  # wrap below
        rects.append(pymupdf.Rect(x, y0, x + width, y0 + h))
        x += width + 0.3 * h
    return rects


def _line_height(boxes: list[pymupdf.Rect | None]) -> float:
    """Median height of the boxes found so far, 0 when there is none."""
    heights = sorted(r.height for r in boxes if r is not None and r.height > 0)
    return heights[len(heights) // 2] if heights else 0.0


def _page_text(
    text: str, tokens: list[tuple[int, int]], boxes: list[pymupdf.Rect | None], ocr: PageText
) -> PageText:
    """The page text: every word's box shared out over its characters, lines counted
    from the newlines of ``text``, line boxes and word spans as the OCR page has them."""
    n = len(text)
    page_text = PageText(number=ocr.number, width=ocr.width, height=ocr.height, text=text,
                       source="ocr")
    page_text.boxes = [None] * n
    page_text.sizes = [0.0] * n
    page_text.baselines = [0.0] * n
    lines: list[int] = []
    line = 0
    for c in text:
        lines.append(line)
        if c == "\n":
            line += 1
    page_text.lines = lines
    for (a, b), r in zip(tokens, boxes, strict=True):
        if r is None or r.is_empty:
            continue
        step = r.width / max(1, b - a)
        for k, i in enumerate(range(a, b)):
            page_text.boxes[i] = (r.x0 + k * step, r.y0, r.x0 + (k + 1) * step, r.y1)
            page_text.sizes[i] = max(r.height, 1.0) * 0.8
            page_text.baselines[i] = r.y1 - 0.2 * r.height
        z = lines[a]
        old = page_text.line_boxes.get(z)
        page_text.line_boxes[z] = tuple(r) if old is None else (
            min(old[0], r.x0), min(old[1], r.y0), max(old[2], r.x1), max(old[3], r.y1))
        page_text.word_spans.append((a, b))
        page_text.confidences.append(1.0)
    return page_text
