"""Corrected or restructured OCR text gets the boxes of the OCR words."""

from __future__ import annotations

import pymupdf

from optdoc.alignment import (
    _after_anchor,
    _between_neighbours,
    _Run,
    _runs,
    _shared_boxes,
    _word_spans,
    text_layer_from_correction,
)
from optdoc.ocr import page_text_from_words
from tests.test_structure import _line


def _ocr():
    words = _line("Herr Max Mustermann wohnt in Dresden", 60, 100)
    words += _line("Diagnosen: Mlgraene seit Jahren", 60, 120)
    return page_text_from_words(words, 0, 595, 842)


def _box(page_text, word: str) -> pymupdf.Rect:
    a = page_text.text.index(word)
    return page_text.rects(a, a + len(word))[0]


def test_words_keep_their_boxes() -> None:
    ocr = _ocr()
    text = ("**Herr Max Mustermann** wohnt heute in Dresden\n\n"
            "#### Diagnosen: Migräne seit Jahren\n\nZusatz: neu\n")
    layer = text_layer_from_correction(text, ocr)
    assert layer.text == text
    for word in ("Herr", "Mustermann", "Dresden", "Jahren"):
        assert abs(_box(layer, word).x0 - _box(ocr, word).x0) < 0.01
        assert abs(_box(layer, word).x1 - _box(ocr, word).x1) < 0.01
    # a corrected word keeps the box of the word it replaces
    assert abs(_box(layer, "Migräne").x0 - _box(ocr, "Mlgraene").x0) < 0.01
    assert abs(_box(layer, "Migräne").x1 - _box(ocr, "Mlgraene").x1) < 0.01
    # an inserted word sits between its neighbours on the same line
    today = _box(layer, "heute")
    assert _box(ocr, "wohnt").x1 <= today.x0 and today.x1 <= _box(ocr, "in").x0
    assert abs(today.y0 - _box(ocr, "wohnt").y0) < 0.01
    # markup has no box and is no word of the layer
    words = {text[a:b] for a, b in layer.word_spans}
    assert "**" not in words and "####" not in words and "Herr" in words
    # text without a counterpart continues after the last word
    extra = _box(layer, "Zusatz:")
    assert extra.x0 > _box(ocr, "Jahren").x1 and abs(extra.y0 - _box(ocr, "Jahren").y0) < 0.01


def test_joined_lines_and_empty_ocr() -> None:
    ocr = _ocr()
    text = "Herr Max Mustermann wohnt in Dresden Diagnosen: Mlgraene seit Jahren\n"
    layer = text_layer_from_correction(text, ocr)  # joined into one paragraph line
    assert abs(_box(layer, "Diagnosen:").y0 - _box(ocr, "Diagnosen:").y0) < 0.01
    assert abs(_box(layer, "Herr").y0 - _box(ocr, "Herr").y0) < 0.01
    empty = page_text_from_words([], 0, 595, 842)
    layer = text_layer_from_correction("Nur Korrektur ohne OCR\n", empty)
    assert len(layer.word_spans) == 4 and all(b is not None for b in layer.boxes[:3])


def test_word_spans_skip_markup() -> None:
    text = "#### **Herr** Max, | - (Zusatz)"
    assert [text[a:b] for a, b in _word_spans(text)] == ["Herr", "Max,", "(Zusatz)"]


def test_shared_boxes_split_and_merge() -> None:
    single, two = pymupdf.Rect(0, 0, 30, 10), pymupdf.Rect(40, 0, 60, 10)
    bottom = pymupdf.Rect(0, 30, 20, 40)
    # two words on one OCR word: its box split by word length
    a, b = _shared_boxes([1, 2], [single])
    assert (a.x0, a.x1, b.x0, b.x1) == (0, 10, 10, 30)
    # one word for two OCR words on one line: their union
    (merged,) = _shared_boxes([5], [single, two])
    assert (merged.x0, merged.x1) == (0, 60)
    # one word for two OCR words on different lines: the first box only
    (first,) = _shared_boxes([5], [single, bottom])
    assert (first.x0, first.x1, first.y1) == (0, 30, 10)


def test_runs_know_their_neighbours() -> None:
    r1, r2 = pymupdf.Rect(0, 0, 10, 10), pymupdf.Rect(50, 0, 60, 10)
    tokens = [(0, 2), (3, 7), (8, 9), (10, 12), (13, 20)]
    runs = _runs(tokens, [r1, None, None, r2, None])
    assert [(lf.start, lf.end, lf.lengths) for lf in runs] == [(1, 3, (4, 1)), (4, 5, (7,))]
    assert runs[0].previous == r1 and runs[0].following == r2
    assert runs[1].previous == r2 and runs[1].following is None


def test_rest_between_neighbours_or_after() -> None:
    previous, following = pymupdf.Rect(0, 0, 10, 10), pymupdf.Rect(40, 0, 50, 10)
    (r,) = _between_neighbours(_Run(1, 2, (3,), previous, following), 10.0)
    assert previous.x1 < r.x0 and r.x1 < following.x0 and (r.y0, r.y1) == (0, 10)
    # neighbours on different lines leave no gap to sit in
    other_line = pymupdf.Rect(40, 30, 50, 40)
    assert _between_neighbours(_Run(1, 2, (3,), previous, other_line), 10.0) is None
    # after the previous word, wrapping to a new line below at the page's right edge
    rects = _after_anchor(_Run(1, 4, (4, 4, 4), pymupdf.Rect(60, 0, 80, 10), None), 10.0, 120.0)
    assert (rects[0].x0, rects[0].y0) == (83, 0)
    assert rects[1].x0 == 36 and abs(rects[1].y0 - 12) < 1e-9 and rects[2].y0 == rects[1].y0
    # before the next word when nothing precedes the run
    (before,) = _after_anchor(_Run(0, 1, (2,), None, following), 10.0, 595.0)
    assert before.x1 < following.x0 and before.y0 == following.y0
    # no anchor at all: an invented first line at the top left of the page
    (alone,) = _after_anchor(_Run(0, 1, (2,), None, None), 10.0, 595.0)
    assert alone.x0 == 36 and abs(alone.y0 - 36) < 1e-9 and abs(alone.height - 10) < 1e-9
