"""The invisible text layer: its font, one line per OCR line with real spaces, every
character as it was read, words where they are printed, pages turned or sharing their
resources; and on macOS, a printed row read by PDFKit as one line."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

from optdoc import ocr as ocrlib
from optdoc import textlayer
from optdoc.ocr import OCRWord, page_text_from_words
from optdoc.reading import read
from tests.synthetic import lab_report, photograph

ROWS = [  # (text, x0, y0) of every word: two rows of a laboratory table and a heading
    [("Befund", 60, 60)],
    [("Kalium", 60, 100), ("5,8", 200, 100), ("mmol/l", 260, 100), ("3,5", 340, 100),
     ("-", 365, 100), ("5,1", 375, 100), ("↑", 420, 100)],
    [("Albumin", 60, 120), ("≤", 200, 120), ("3,5", 212, 120), ("µg/ml", 260, 120)],
]


def _words(rows: list[list[tuple[str, float, float]]], slope: float = 0.0) -> list[OCRWord]:
    """OCR words 10 pt high, 6 pt per character, each row tilted by ``slope``."""
    return [OCRWord(text, x, y + slope * x, x + 6 * len(text), y + 10 + slope * x)
            for row in rows for text, x, y in row]


def _page_with_layer(words: list[OCRWord], rotation: int = 0) -> pymupdf.Document:
    """A blank page with the words laid on it as the text layer, saved and opened again."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.set_rotation(rotation)
    rect = page.rect
    page_text = page_text_from_words(words, 0, rect.width, rect.height)
    font = textlayer.add_font(doc)
    assert textlayer.write_page(doc, page, page_text, font) == len(words)
    again = pymupdf.open("pdf", doc.tobytes(garbage=3, deflate=True))
    doc.close()
    return again


def test_font() -> None:
    """A valid TrueType font: two glyphs, ascent and descent spanning the em, its
    checksum adjusted."""
    data = textlayer.invisible_font()
    font = pymupdf.Font(fontbuffer=data)
    assert font.glyph_count == 2
    assert font.ascender == pytest.approx(0.8) and font.descender == pytest.approx(-0.2)
    assert textlayer._checksum(data) == 0xB1B0AFBA
    assert len(data) < 1024


def test_lines_with_spaces_and_every_character() -> None:
    """Each OCR line comes out as one line, its words parted by real spaces, characters
    outside Windows-1252 as they were read; a search finds the word where it is
    printed, no wider."""
    with _page_with_layer(_words(ROWS)) as doc:
        page = doc[0]
        assert page.get_text().splitlines() == [
            "Befund", "Kalium 5,8 mmol/l 3,5 - 5,1 ↑", "Albumin ≤ 3,5 µg/ml"]
        found = page.search_for("mmol/l")
        assert len(found) == 1
        assert abs(found[0].x0 - 260) < 0.5 and abs(found[0].x1 - 296) < 1.0
        assert abs(found[0].y0 - 100) < 1.0 and abs(found[0].y1 - 110) < 1.0
        assert page.get_pixmap(dpi=20).is_unicolor  # invisible


def test_tilted_line_stays_one_line() -> None:
    """A line tilted by 2° (so far that the first and the last word do not overlap in
    height) is still one line, written along its own slope."""
    words = _words(ROWS[1:2], slope=0.035)
    assert words[-1].y0 > words[0].y1
    with _page_with_layer(words) as doc:
        lines = doc[0].get_text().splitlines()
    assert lines == ["Kalium 5,8 mmol/l 3,5 - 5,1 ↑"]


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_turned_page(rotation: int) -> None:
    """On a page turned by ``/Rotate`` the words lie where they are shown."""
    with _page_with_layer(_words(ROWS), rotation) as doc:
        page = doc[0]
        assert page.get_text().splitlines()[1] == "Kalium 5,8 mmol/l 3,5 - 5,1 ↑"
        found = page.search_for("Kalium")[0]
        assert abs(found.x0 - 60) < 0.5 and abs(found.y0 - 100) < 1.0


def test_inherited_and_shared_resources(tmp_path: Path) -> None:
    """A page whose resources come from the page tree keeps its picture; pages sharing one
    resources object both get their text."""
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page(width=200, height=200)
        page.draw_rect(pymupdf.Rect(20, 20, 60, 60), color=(1, 0, 0), fill=(1, 0, 0))
    first, second = doc[0], doc[1]
    kind, value = doc.xref_get_key(first.xref, "Resources")
    if kind == "xref":
        shared = int(value.split()[0])
    else:
        shared = doc.get_new_xref()
        doc.update_object(shared, value)
    doc.xref_set_key(first.xref, "Resources", f"{shared} 0 R")
    doc.xref_set_key(second.xref, "Resources", f"{shared} 0 R")
    root_pages = int(doc.xref_get_key(doc.pdf_catalog(), "Pages")[1].split()[0])
    doc.xref_set_key(root_pages, "Resources", f"{shared} 0 R")
    doc.xref_set_key(second.xref, "Resources", "null")  # inherited from the page tree
    before = [p.get_pixmap(dpi=36).samples for p in doc]
    font = textlayer.add_font(doc)
    for page in doc:
        text = page_text_from_words([OCRWord("Probe", 80, 80, 110, 90)], page.number, 200,
                                    200)
        textlayer.write_page(doc, page, text, font)
    path = tmp_path / "geteilt.pdf"
    doc.save(path)
    with pymupdf.open(path) as again:
        assert [p.get_text().strip() for p in again] == ["Probe", "Probe"]
        assert [p.get_pixmap(dpi=36).samples for p in again] == before


def _pdfkit_lines(tmp_path: Path, pdf: Path) -> list[str]:
    """The lines of every page as PDFKit gives them (``PDFPage.string``), as medorello's
    desktop shell reads a PDF."""
    source = tmp_path / "lines.swift"
    source.write_text(
        "import Foundation\nimport PDFKit\n"
        "let d = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1]))!\n"
        "for i in 0..<d.pageCount { print(d.page(at: i)?.string ?? \"\") }\n",
        encoding="utf-8")
    program = tmp_path / "lines"
    subprocess.run(["swiftc", "-O", str(source), "-o", str(program)], check=True,
                   capture_output=True, timeout=600)
    run = subprocess.run([str(program), str(pdf)], check=True, capture_output=True, text=True)
    return [" ".join(z.split()) for z in run.stdout.splitlines() if z.strip()]


@pytest.mark.skipif(sys.platform != "darwin" or shutil.which("swiftc") is None
                    or not ocrlib.available_backends(), reason="PDFKit is macOS's")
def test_pdfkit_reads_each_row_as_one_line(tmp_path: Path) -> None:
    """A photographed laboratory report: PDFKit gives every row of its table (name, value,
    unit, range, flag) as one line of the PDF optdoc writes, as medorello's laboratory
    reader needs it.  The row counts when PDFKit's line holds its name and its last
    item and is nearly as long as the printed row (the reading itself may differ by a
    character or a space)."""
    import difflib

    pdf, truth = lab_report(tmp_path, 1)
    reading = read(photograph(pdf, tmp_path / "foto.jpg"))
    try:
        from optdoc import output

        paths = output.write(reading, tmp_path / "out")
    finally:
        reading.close()
    lines = ["".join(z.split()) for z in _pdfkit_lines(tmp_path, paths["pdf"])]
    whole = 0
    for row in truth:
        want = "".join(row.split())
        best = max(lines, key=lambda z: difflib.SequenceMatcher(None, want, z).ratio())
        whole += (difflib.SequenceMatcher(None, want, best).ratio() >= 0.85
                  and len(best) >= 0.8 * len(want))
    assert whole == len(truth), (whole, len(truth))
