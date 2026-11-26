"""The tables of a page with their cells, found by Camelot in the PDF optdoc writes.

A laboratory reader wants a result as a row of cells (name, value, unit, range, flag),
not as a line of words to take apart.  Camelot (MIT) finds tables in the text of a PDF:
its "hybrid" way joins the columns it reads from the alignment of the text with the
ruled lines it sees in the rendered page.  On a scan or a photo that text is optdoc's
own invisible layer, whose gaps between cells are left open for this
(:mod:`optdoc.textlayer`).

Measured on invented laboratory reports in three layouts (a ruled grid, open columns,
two blocks with the flag before the value; 54 results), as born-digital PDFs and as
optdoc's PDFs of photos of them; a row counts when it comes out as a table row whose
cells are each at least 0.8 similar to the printed ones:

=================================  =========  =====================
                                    digital    photo, through optdoc
=================================  =========  =====================
Camelot hybrid (used here)          54/54      49/54
Camelot stream                      54/54      45/54
img2table                           44/54      39/54
pdfplumber, text strategy           39/54      35/54
RapidTable after rapid-layout       32/54      35/54
Tabula stream                       54/54      29/54
PyMuPDF ``find_tables``, text       39/54      14/54
=================================  =========  =====================

The five rows Camelot missed on the photos were all cut right; OCR had read "U/l" as
"U/I".  Tabula needs a Java runtime besides; Camelot is pure Python.  With
:func:`_distinct` taking each row once, ``optdoc bench`` counts on twelve photographed
reports (all three layouts, two sets of values) 211 of 216 rows cut right and 193 read
exactly; on the born-digital PDFs of 24 reports every row (432).

Needs the extra "tables".  Camelot is given the path of a PDF: for a path, Camelot 2.2
renders pages in memory and writes no file anywhere else (checked with an empty
temporary folder); a PDF in memory it would write to the temporary folder first.  The
project writes the page it looks at into a folder of its own for a moment
(:meth:`optdoc.project.Project.find_regions`).
"""

from __future__ import annotations

import gc
import importlib.util
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

Box = tuple[float, float, float, float]


def available() -> bool:
    """True when Camelot is installed (the extra "tables"); it is not loaded for that."""
    return importlib.util.find_spec("camelot") is not None


@dataclass
class Cell:
    """One cell: its text (spaces collapsed, lines joined by a space; empty for an empty
    or a spanned cell) and its box in points from the top left of the page as shown."""

    text: str
    box: Box

    def as_dict(self) -> dict[str, Any]:
        """The cell for the reading."""
        return {"text": self.text, "box": [round(v, 2) for v in self.box]}


@dataclass
class Table:
    """A table: its rows of cells, top to bottom, each left to right, its box, the
    confidence of the automatic finder in it (0 to 1), and who set its grid: "auto"
    (found) or "person" (set or corrected in the window, :mod:`optdoc.layout`)."""

    rows: list[list[Cell]] = field(default_factory=list)
    confidence: float = 0.0
    by: str = "auto"

    @property
    def box(self) -> Box:
        """The box around all cells."""
        boxes = [c.box for row in self.rows for c in row]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def as_dict(self) -> dict[str, Any]:
        """The table for the reading."""
        return {"box": [round(v, 2) for v in self.box], "confidence": round(self.confidence, 3),
                "by": self.by, "rows": [[c.as_dict() for c in row] for row in self.rows]}


def _shown(page: pymupdf.Page, x0: float, y0: float, x1: float, y1: float) -> Box:
    """A box in Camelot's coordinates (points from the bottom left of the media box) as
    points from the top left of the page as shown (optdoc's pages are upright)."""
    top = page.mediabox.height
    dx, dy = page.cropbox.x0, page.cropbox.y0
    return (min(x0, x1) - dx, top - max(y0, y1) - dy, max(x0, x1) - dx, top - min(y0, y1) - dy)


def _table(found: Any, page: pymupdf.Page) -> Table | None:
    """optdoc's form of a table Camelot found; None for fewer than two rows or columns,
    which is no table worth the name."""
    texts = found.df.values.tolist()
    if len(found.cells) < 2 or len(found.cells[0]) < 2:
        return None

    def text(r: int, c: int) -> str:
        # Camelot's table of texts may have fewer rows or columns than its grid of
        # cells (on scans it often has); a cell without text is empty
        return " ".join(str(texts[r][c]).split()) if r < len(texts) and c < len(texts[r]) \
            else ""

    rows = [[Cell(text(r, c), _shown(page, cell.x1, cell.y1, cell.x2, cell.y2))
             for c, cell in enumerate(row)]
            for r, row in enumerate(found.cells)]
    return Table(rows, float(getattr(found, "confidence", 0.0) or 0.0))


def _row_box(row: list[Cell]) -> Box:
    """The box around the cells of a row."""
    return (min(c.box[0] for c in row), min(c.box[1] for c in row),
            max(c.box[2] for c in row), max(c.box[3] for c in row))


def _inside(row: list[Cell], box: Box) -> bool:
    """True when the middle of the row lies within ``box`` (and the two meet sideways)."""
    x0, y0, x1, y1 = _row_box(row)
    return box[1] <= (y0 + y1) / 2 <= box[3] and x0 < box[2] and x1 > box[0]


def _filled(row: list[Cell]) -> int:
    """How many cells of the row hold text."""
    return sum(1 for c in row if c.text)


def _distinct(tables: list[Table]) -> list[Table]:
    """The tables of a page with every row once.  Hybrid finds a table both by its ruled
    lines and by the alignment of its text, and the second may take in more: the head
    of the letter above a photographed grid, or a second block below the first.  Taken
    in order of Camelot's confidence, a table keeps the rows that no table taken before
    holds; what is left of it stays a table of its own when two of its rows have at
    least two filled cells.  Top to bottom."""
    kept: list[Table] = []
    for table in sorted(tables, key=lambda t: -t.confidence):
        rows = [r for r in table.rows if not any(_inside(r, other.box) for other in kept)]
        if len(rows) == len(table.rows):
            kept.append(table)
        elif sum(1 for r in rows if _filled(r) >= 2) >= 2:
            kept.append(Table(rows, table.confidence))
    return sorted(kept, key=lambda t: t.box[1])


def find_tables(pdf: str | Path) -> dict[int, list[Table]]:
    """The tables of every page of the PDF at ``pdf`` by page number (from 0), top to
    bottom, each once; a page without tables is not named.  Needs Camelot.  Only a path:
    Camelot writes a PDF given in memory to the temporary folder."""
    import camelot

    with warnings.catch_warnings():  # "no tables found" on a page is no news
        warnings.simplefilter("ignore")
        found = camelot.read_pdf(str(pdf), pages="all", flavor="hybrid")
    tables: dict[int, list[Table]] = {}
    with pymupdf.open(pdf) as doc:
        for each in found:
            number = int(each.page) - 1
            table = _table(each, doc[number])
            if table is not None:
                tables.setdefault(number, []).append(table)
    # Camelot's objects hold the PDF open in reference cycles until a garbage collection;
    # an open file cannot be deleted or replaced on Windows
    found = each = None
    gc.collect()
    return {number: _distinct(page_tables) for number, page_tables in tables.items()}
