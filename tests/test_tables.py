"""Tables with their cells: every result row of the invented laboratory reports as a
row of cells, in born-digital PDFs and in optdoc's PDFs of photos; none in a letter;
each table once; the cells where the words are."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from optdoc import ocr as ocrlib
from optdoc import output, tables
from optdoc.bench import score_tables
from optdoc.reading import read
from optdoc.tables import Cell, Table, find_tables
from tests.synthetic import lab_report, photograph

pytestmark = pytest.mark.skipif(not tables.available(), reason="needs Camelot (extra 'tables')")
needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                   reason="no OCR engine installed")


def _cells(pdf: Path) -> list[list[str]]:
    return json.loads(pdf.with_name(pdf.stem + ".cells.json").read_text(encoding="utf-8"))


def _texts(found: dict[int, list[Table]]) -> list[list[list[str]]]:
    return [[[c.text for c in row] for row in t.rows] for page in found.values() for t in page]


@pytest.mark.parametrize("layout", [1, 2, 3])
def test_born_digital_reports(tmp_path: Path, layout: int) -> None:
    """A ruled grid, open columns, two blocks with the flag before the value: every row
    exactly, as one table."""
    pdf, _ = lab_report(tmp_path, layout)
    found = find_tables(pdf)
    assert list(found) == [0] and len(found[0]) == 1
    score = score_tables(_cells(pdf), _texts(found))
    assert score.table_rows_exact == score.table_rows == 18


def test_pdf_is_let_go(tmp_path: Path) -> None:
    """Once the tables are found, the PDF is closed again: on Windows a file still open
    cannot be deleted, and the bench removes its working copies."""
    pdf, _ = lab_report(tmp_path, 1)
    find_tables(pdf)
    moved = pdf.rename(tmp_path / "moved.pdf")  # Windows refuses for an open file, too
    moved.unlink()
    assert not moved.exists()
    if sys.platform != "win32":
        import subprocess

        held = subprocess.run(["lsof", "-p", str(os.getpid())], capture_output=True,
                              text=True, check=False).stdout
        assert "lab-01.pdf" not in held and "moved.pdf" not in held


@needs_backend
def test_photographed_report(tmp_path: Path) -> None:
    """A photo of the ruled report, read by optdoc: every row once, cut into the right
    cells, each cell's box around the word printed in it; the reading carries
    the tables, unless they are not wanted."""
    pdf, _ = lab_report(tmp_path, 1)
    reading = read(photograph(pdf, tmp_path / "foto.jpg"))
    try:
        paths = output.write(reading, tmp_path / "out")
        words = reading.pages[0].text
        found = reading.tables
        assert found is not None
        firsts = [row[0].text for t in found[0] for row in t.rows]
        assert firsts.count("Leukozyten") == 1  # every row once, not the grid twice
        score = score_tables(_cells(pdf), _texts(found))
        assert score.table_rows_cut_right >= 16, score
        first = words.text.index("Leukozyten")
        word = words.rects(first, first + len("Leukozyten"))[0]
        cell = next(row[0] for t in found[0] for row in t.rows if row[0].text == "Leukozyten")
        x0, y0, x1, y1 = cell.box
        assert x0 - 1 <= word.x0 and word.x1 <= x1 + 1 and y0 - 1 <= word.y0 <= word.y1 <= y1 + 1
        page = json.loads(paths["reading"].read_text(encoding="utf-8"))["pages"][0]
        assert page["tables"] and all(t["confidence"] > 0 for t in page["tables"])
        assert {"text", "box"} == set(page["tables"][0]["rows"][1][0])
        output.write(reading, tmp_path / "ohne", cells=False)
        assert reading.tables is None
        page = json.loads((tmp_path / "ohne" / "foto.reading.json").read_text())["pages"][0]
        assert page["tables"] is None
    finally:
        reading.close()


def test_letter_has_no_tables(tmp_path: Path, report: Path) -> None:
    """A letter is no table: the reading says so with an empty list per page."""
    reading = read(report)
    try:
        paths = output.write(reading, tmp_path / "out")
    finally:
        reading.close()
    pages = json.loads(paths["reading"].read_text(encoding="utf-8"))["pages"]
    assert [p["tables"] for p in pages] == [[], []]


def test_each_row_once() -> None:
    """A table found twice keeps the rows of the one Camelot is more confident in; of the
    other, what lies outside stays a table of its own (a second block below the first),
    unless it is too little to be one (a line of a letter's head above a grid)."""
    def row(y: float, *texts: str) -> list[Cell]:
        return [Cell(t, (60 + 100 * i, y, 160 + 100 * i, y + 15)) for i, t in enumerate(texts)]

    grid = Table([row(150, "Kalium", "5,8"), row(165, "Natrium", "140")], 0.86)
    with_head = Table([row(70, "Labor am Beispielpark", ""), *grid.rows], 0.79)
    assert tables._distinct([with_head, grid]) == [grid]
    second = [row(300, "Klinische Chemie", ""), row(315, "CRP", "2,1"), row(330, "TSH", "1,2")]
    both = Table([*grid.rows, *second], 0.79)
    found = tables._distinct([both, grid])
    assert found == [grid, Table(second, 0.79)]
