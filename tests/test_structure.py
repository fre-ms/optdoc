"""Markdown structure of a recognised page from the geometry of its lines."""

from __future__ import annotations

import pymupdf

from optdoc import structure as gl
from optdoc.ocr import OCRWord, page_text_from_words
from optdoc.pagetext import PageText, read_text_layer


def _line(text: str, x: float, y: float, h: float = 10.0, chars: float = 5.0,
           space: float = 3.0) -> list[OCRWord]:
    """Words of one line with boxes: ``chars`` points per character, ``space`` between."""
    words = []
    for w in text.split(" "):
        if not w:
            continue
        b = len(w) * chars
        words.append(OCRWord(w, x, y, x + b, y + h))
        x += b + space
    return words


FULL1 = "Die Patientin berichtet über seit drei Wochen bestehende Kopfschmerzen und einen Blut-"
FULL2 = "druck von 160 zu 95 mmHg, dazu Schwindel beim Aufstehen, ohne Sturz, ohne Doppelbilder."
FULL3 = "Die Beschwerden begannen nach einer fieberhaften Infektion und haben seither zugenommen,"
SHORT = "weshalb sie sich heute vorstellt."


def _page():
    words = _line("Arztbrief Neurologie", 60, 60, h=18, chars=9)
    words += _line(FULL1, 60, 100) + _line(FULL2, 60, 114) + _line(FULL3, 60, 128)
    words += _line(SHORT, 60, 142)
    words += _line("Diagnosen:", 60, 170)
    words += _line("- Kopfschmerz seit drei Wochen", 60, 190)
    words += _line("- Schwindel beim Aufstehen", 60, 204)
    words += _line("Medikament", 60, 240) + _line("Dosis", 260, 240)
    words += _line("morgens", 360, 240)
    words += _line("Ramipril", 60, 254) + _line("5 mg", 260, 254) + _line("1", 360, 254)
    words += _line("Amlodipin", 60, 268) + _line("5 mg", 260, 268) + _line("0", 360, 268)
    return page_text_from_words(words, 0, 595, 842)


def test_tabs_for_cell_boundaries() -> None:
    s = _page()
    lines = s.text.splitlines()
    assert lines[-3] == "Medikament\tDosis\tmorgens" and lines[-1] == "Amlodipin\t5 mg\t0"
    assert "\t" not in lines[1]  # ordinary word gaps stay spaces


def test_structure_as_markdown() -> None:
    s = _page()
    diagnoses = s.text.splitlines().index("Diagnosen:")
    g = gl.analyse_structure(s, bold={diagnoses})
    md = g.render(s.text)
    assert md.startswith("### Arztbrief Neurologie\n\n")
    assert "Kopfschmerzen und einen Blutdruck von 160" in md  # hyphenation undone
    assert "ohne Doppelbilder. Die Beschwerden" in md  # full lines joined with a space
    assert "zugenommen, weshalb sie sich heute vorstellt." in md  # short last line joined
    assert "\n\n#### Diagnosen:\n\n" in md  # short bold line on its own: a heading
    assert "- Kopfschmerz seit drei Wochen\n- Schwindel beim Aufstehen\n\n" in md
    assert "| Medikament | Dosis | morgens |\n| --- | --- | --- |\n| Ramipril | 5 mg | 1 |" in md
    assert g.tables == 1 and g.headings == 2
    # the same structure over the pseudonymised text (same lines, other words)
    anonymous = s.text.replace("Die Patientin", "Patient K7Q4MX")
    md2 = g.render(anonymous)
    assert md2.startswith("### Arztbrief Neurologie") and "Patient K7Q4MX berichtet" in md2
    assert "| Ramipril | 5 mg | 1 |" in md2
    assert g.render("ganz anderer Text") == "ganz anderer Text"  # lines do not match: as is


def test_paragraph_without_bold_or_lines() -> None:
    """Short lines stay lines of one block; a colon line before a long one opens a block."""
    words = _line("Konzentration: gut.", 60, 100) + _line("Haltung: aufrecht.", 60, 114)
    words += _line("Gangbild: sicher.", 60, 128) + _line("Beurteilung:", 60, 150)
    words += _line(FULL3, 60, 164) + _line(SHORT, 60, 178)
    words += _line(FULL2, 60, 192) + _line("Medikation: Ramipril 5 mg morgens.", 60, 206)
    s = page_text_from_words(words, 0, 595, 842)
    md = gl.analyse_structure(s).render(s.text)
    assert "Konzentration: gut.\nHaltung: aufrecht.\nGangbild: sicher.\n\n" in md
    assert "Beurteilung:\n\nDie Beschwerden" in md and "zugenommen, weshalb" in md
    # a labelled line opens a block even after a line that ran to the margin
    assert "ohne Doppelbilder.\n\nMedikation: Ramipril" in md


def test_bold_lines_from_the_image() -> None:
    """Ink coverage finds the bold line of a rendered page."""
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    texts = ["Sehr geehrte Frau Kollegin,", "wir berichten über die Patientin.",
             "Die Untersuchung ergab einen regelrechten Befund.", "Diagnosen und Befunde",
             "Die Medikation wurde unverändert fortgeführt.", "Mit freundlichen Grüßen",
             "Die Wiedervorstellung ist in drei Monaten geplant."]
    for i, t in enumerate(texts):
        p.insert_text((60, 100 + 20 * i), t, fontsize=11, fontname="hebo" if i == 3 else "helv")
    page_text = read_text_layer(p, 0)
    lines = gl.lines_of(page_text)
    import numpy as np

    scale = 100 / 72.0
    pix = p.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY, alpha=False)
    grey = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    bold = gl.bold_lines(lines, grey, scale)
    assert bold == {next(i for i, z in enumerate(lines) if "Diagnosen" in z.text)}
    md = gl.analyse_page_structure(p, page_text).render(page_text.text)
    assert "#### Diagnosen und Befunde" in md
    doc.close()


def _z(text: str, x0: float = 60.0, y0: float = 100.0, width: float = 200.0,
       height: float = 10.0) -> gl.Line:
    """A line with a box, for the rules that look at geometry only."""
    return gl.Line(0, len(text), text, x0, y0, x0 + width, y0 + height, height)


MEASURE = gl._PageMeasure(height=10.0, left=60.0, right=500.0, width=440.0, space=4.0)


def test_tables_only_from_three_cells_or_two_lines() -> None:
    """A lone line with two cells is a label with its value, not a table."""
    lines = [_z("Name:\tWert"), _z("Text"), _z("a\tb\tc"), _z("Text"), _z("a\tb"), _z("c\td")]
    roles = [gl.Role() for _ in lines]
    gl._mark_tables(lines, roles)
    assert [r.kind for r in roles] == ["paragraph", "paragraph", "table", "paragraph", "table",
                                       "table"]
    assert [r.table for r in roles] == [-1, -1, 0, -1, 1, 1]


def test_line_kind_by_type_and_form() -> None:
    """Large face, bullets, capitals and bold decide the kind of a line."""
    assert gl._line_kind(_z("Befund", height=17.0), False, MEASURE) == ("heading", 3)
    assert gl._line_kind(_z("Befund", height=14.0), False, MEASURE) == ("heading", 4)
    assert gl._line_kind(_z("- Punkt eins"), False, MEASURE) == ("list", 0)
    assert gl._line_kind(_z("ANAMNESE"), False, MEASURE) == ("heading", 4)
    assert gl._line_kind(_z("Anamnese"), True, MEASURE) == ("heading", 4)
    assert gl._line_kind(_z("Anamnese."), True, MEASURE) == ("paragraph", 0)  # ends a sentence
    assert gl._line_kind(_z("Anamnese", width=400.0), True, MEASURE) == ("paragraph", 0)  # long
    assert gl._line_kind(_z("Anamnese"), False, MEASURE) == ("paragraph", 0)


def test_block_separators() -> None:
    """Tables, headings and list items settle the separator without geometry."""
    tab0, tab1 = gl.Role("table", table=0), gl.Role("table", table=1)
    flipped, items, text = gl.Role("heading", 4), gl.Role("list"), gl.Role()
    assert gl._block_separators(tab0, tab0) == "line"
    assert gl._block_separators(tab1, tab0) == "paragraph"
    assert gl._block_separators(text, tab0) == "paragraph"
    assert gl._block_separators(flipped, text) == gl._block_separators(text, flipped) == "paragraph"
    assert gl._block_separators(items, items) == "line"
    assert gl._block_separators(items, text) == "paragraph"
    assert gl._block_separators(text, items) is None  # the geometry decides
    assert gl._block_separators(text, text) is None


def test_paragraph_separator_by_geometry() -> None:
    """Gap, indent, a full predecessor, a label and a colon line decide the join."""
    full = _z("Die Beschwerden bestehen seit drei Wochen und", y0=100.0, width=440.0)
    short = _z("seit drei Wochen.", y0=100.0, width=100.0)
    assert gl._paragraph_separator(_z("weiter", y0=130.0), full, MEASURE) == "paragraph"  # tall gap
    indented = _z("weiter", x0=80.0, y0=114.0)
    assert gl._paragraph_separator(indented, short, MEASURE) == "paragraph"  # indent
    assert gl._paragraph_separator(_z("weiter", y0=114.0), full, MEASURE) == "word"
    assert gl._paragraph_separator(_z("Diagnosen: keine", y0=114.0), full, MEASURE) == "paragraph"
    assert gl._paragraph_separator(_z("weiter", y0=114.0), short, MEASURE) == "line"
    colon = _z("Beurteilung:", y0=100.0, width=100.0)
    assert gl._paragraph_separator(_z("lange Zeile", y0=114.0, width=400.0), colon,
                             MEASURE) == "paragraph"
    assert gl._paragraph_separator(_z("kurz", y0=114.0, width=100.0), colon, MEASURE) == "line"
    separated = _z("ein Blut-", y0=100.0, width=440.0)
    assert gl._paragraph_separator(_z("druck", y0=114.0), separated, MEASURE) == "syllable"
    assert gl._paragraph_separator(_z("Druck", y0=114.0), separated, MEASURE) == "word"


def test_continuation_under_list_item() -> None:
    """A line close under a bullet and indented past it continues the item."""
    point = _z("- Kopfschmerz seit", y0=100.0)
    assert gl._hangs_under_list_item(_z("drei Wochen", x0=70.0, y0=114.0), point, MEASURE)
    assert not gl._hangs_under_list_item(_z("drei Wochen", x0=60.0, y0=114.0), point, MEASURE)
    assert not gl._hangs_under_list_item(_z("drei Wochen", x0=70.0, y0=130.0), point, MEASURE)


def test_paragraph_bold_runs() -> None:
    """Bold runs stay open across a space, close at a newline, and join across a hyphen."""
    a = gl._Paragraph()
    a.append_char("Eins", True, "paragraph")
    a.append_char("zwei", True, "word")
    a.append_char("drei", False, "word")
    assert a.closing() == "**Eins zwei** drei" and a.closing() == ""
    a.append_char("Eins", True, "paragraph")
    a.append_char("zwei", True, "line")
    assert a.closing() == "**Eins**\n**zwei**"
    a.append_char("Blut-", False, "paragraph")
    a.append_char("druck", False, "syllable")
    a.append_char("hoch", False, "syllable")  # no hyphen before it: joined without a gap
    assert a.closing() == "Blutdruckhoch"


def test_lines_without_boxes() -> None:
    """Lines without character boxes keep the zero box and count as empty."""
    text = "ab\n\ncd\n"
    boxes = [(10.0, 20.0, 15.0, 30.0), None, None, None, None, None]
    page_text = PageText(0, 595, 842, text=text, boxes=boxes)
    lines = gl.lines_of(page_text)
    assert [z.text for z in lines] == ["ab", "", "cd"]
    assert (lines[0].x0, lines[0].y0, lines[0].x1, lines[0].y1) == (10.0, 20.0, 15.0, 30.0)
    assert lines[0].height == 10.0 and not lines[0].empty
    assert lines[1].empty and lines[2].empty and lines[2].width == 0.0
    assert gl.analyse_structure(page_text).render(text) == "ab\n\ncd\n"


def test_page_measure_with_fallback() -> None:
    """Without measured heights or usual gaps the measures fall back to defaults."""
    one = gl._PageMeasure.out([gl.Line(0, 4, "Text", 60.0, 100.0, 260.0, 110.0, 0.0)])
    assert (one.height, one.left, one.right, one.width, one.space) == (10.0, 60.0, 260.0,
                                                                                200.0, 3.0)
    assert one.paragraph_gap == 8.0
    two = gl._PageMeasure.out([_z("a", y0=100.0), _z("b", y0=114.0, width=400.0)])
    assert (two.height, two.width, two.space) == (10.0, 400.0, 4.0)
