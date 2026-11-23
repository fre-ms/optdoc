"""Character map of a page: offsets map back to rectangles."""

from __future__ import annotations

import pymupdf
import pytest

from optdoc.errors import OptdocError
from optdoc.pagetext import (
    PageText,
    _glyphs,
    _read_line,
    _word_gap,
    read_text_layer,
)


def _page() -> pymupdf.Page:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Erste Zeile mit Mustermann, Komma", fontsize=11, fontname="helv")
    page.insert_text((72, 116), "Zweite Zeile", fontsize=11, fontname="helv")
    return page


def test_text_and_lines() -> None:
    s = read_text_layer(_page())
    assert "Erste Zeile mit Mustermann, Komma" in s.text
    assert "Zweite Zeile" in s.text
    assert s.has_text_layer
    a = s.text.index("Mustermann")
    b = a + len("Mustermann")
    assert s.line_of(a) == s.line_of(b - 1)
    assert s.line_of(a) != s.line_of(s.text.index("Zweite"))


def test_rects_and_free_space() -> None:
    s = read_text_layer(_page())
    a = s.text.index("Mustermann")
    b = a + len("Mustermann")
    rects = s.rects(a, b)
    assert len(rects) == 1
    r = rects[0]
    assert 72 < r.x0 < r.x1 < s.width
    assert 85 < r.y0 < r.y1 < 110
    # the comma follows immediately, so there is no free space to the right
    assert abs(s.free_space_right(b) - r.x1) < 0.5
    assert s.font_size(a, b) == 11.0
    assert s.baseline(a, b) is not None and abs(s.baseline(a, b) - 100) < 0.5


def test_empty_page() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    s = read_text_layer(page)
    assert s.text.strip() == ""
    assert not s.has_text_layer


def test_dict_round_trip_and_check() -> None:
    """The JSON reader restores tuples, drops line boxes without a box and rejects
    character lists that do not fit the text."""
    raw = {"number": 3, "width": 595.2, "height": 841.9, "text": "ab c\n", "source": "ocr",
           "boxes": [[1, 2, 3, 4], [5, 6, 7, 8], None, [9, 10, 11, 12], None],
           "lines": [1, 1, 1, 1, 1], "sizes": [10, 10, 0, 10, 0],
           "baselines": [4, 4, 0, 12, 0], "line_boxes": {"1": [1, 2, 11, 12], "2": None},
           "confidences": [0.9, 0.4], "word_spans": [[0, 2], [3, 4]]}
    s = PageText.from_dict(raw)
    assert s.boxes[0] == (1, 2, 3, 4) and s.boxes[2] is None
    assert s.line_boxes == {1: (1, 2, 11, 12)}
    assert s.word_spans == [(0, 2), (3, 4)] and s.words() == [(0, 2), (3, 4)]
    assert s.uncertain_words == 1 and s.source == "ocr"
    assert PageText.from_dict(s.as_dict()) == s
    assert PageText.from_dict({"number": 0, "width": 1, "height": 2, "text": ""}).boxes == []
    with pytest.raises(OptdocError, match="Page text 4"):
        PageText.from_dict(dict(raw, lines=[1, 1]))


def test_glyphs_and_word_gap() -> None:
    """A rawdict line yields one glyph per character (baseline from the span when the
    character has none), and a wide gap without a space in the text gets one."""
    line = {"spans": [
        {"size": 12, "origin": (72, 100),
         "chars": [{"c": "a", "bbox": (72, 90, 78, 102), "origin": (72, 100)},
                   {"c": "b", "bbox": (78, 90, 84, 102)}]},
        {"size": 8, "origin": (100, 100),
         "chars": [{"c": "c", "bbox": (100, 92, 104, 102), "origin": (100, 0)}]},
    ]}
    glyphs = list(_glyphs(line))
    assert [g[0] for g in glyphs] == ["a", "b", "c"]
    assert glyphs[1] == ("b", (78.0, 90.0, 84.0, 102.0), 12.0, 100.0)
    assert glyphs[2][3] == 100.0  # origin y = 0 falls back to the span's baseline
    assert _word_gap("ab", (72, 90, 84, 102), (100, 92, 104, 102), 8.0)
    assert not _word_gap("ab ", (72, 90, 84, 102), (100, 92, 104, 102), 8.0)
    assert not _word_gap("ab", (72, 90, 84, 102), (85, 92, 104, 102), 8.0)
    s = PageText(number=0, width=200, height=200)
    _read_line(s, line, 1)
    assert s.text == "ab c\n" and s.boxes[2] is None and s.lines == [1] * 5
    assert s.line_boxes == {1: (72.0, 90.0, 104.0, 102.0)}
