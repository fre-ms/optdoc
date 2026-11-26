"""The regions of a page: what is text, a table, a picture, a barcode, handwriting, a
stamp, or not to be read, and for a table its grid.

FineReader's way: before the text is read, the page is divided into regions, found
automatically and corrected by a person, and a table's grid of rows and columns can be
moved, added to, taken away from and its cells merged.  optdoc keeps the regions of a
page in its configuration like everything else that decides the result
(:mod:`optdoc.project`), so that they are reproduced and the work can be resumed.

A region's box is in points of the cleaned page (from its top left, as the masks of the
clean-up).  The order of the regions is their reading order.  What lies in no region is
read as text, so that regions are needed only where they change something:

=============  ==================================================================
kind           what becomes of the words in it
=============  ==================================================================
text           read
table          read, and placed into the cells of its grid
handwriting    read; marked, so that a program can treat it apart (cover it)
stamp          read; marked likewise
image          not read
barcode        not read as text
ignore         not read
=============  ==================================================================

A table's grid is its inner column lines (``columns``, x in points) and row lines
(``rows``, y), between the edges of its box, and the merged cells, each as the first
and last row and column it spans, counted from 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from optdoc.errors import OptdocError
from optdoc.tables import Cell, Table

Box = tuple[float, float, float, float]
Span = tuple[int, int, int, int]  # first row, first column, last row, last column

KINDS = ("text", "table", "image", "barcode", "handwriting", "stamp", "ignore")
NOT_READ = frozenset({"image", "barcode", "ignore"})
BY = ("auto", "person")
SMALLEST = 2.0  # points: no region, row or column is narrower


@dataclass
class Region:
    """One region of a page; see the module."""

    kind: str
    box: Box
    by: str = "auto"
    columns: list[float] = field(default_factory=list)
    rows: list[float] = field(default_factory=list)
    merged: list[Span] = field(default_factory=list)
    confidence: float | None = None  # how sure the automatic finder was (0 to 1)

    # -- the grid ------------------------------------------------------------------------------
    @property
    def xs(self) -> list[float]:
        """Every column line of a table, its edges included, left to right."""
        return [self.box[0], *self.columns, self.box[2]]

    @property
    def ys(self) -> list[float]:
        """Every row line of a table, its edges included, top to bottom."""
        return [self.box[1], *self.rows, self.box[3]]

    @property
    def size(self) -> tuple[int, int]:
        """Rows and columns of the grid."""
        return len(self.rows) + 1, len(self.columns) + 1

    def span_of(self, row: int, column: int) -> Span:
        """The cells merged with the cell at ``row``, ``column`` (itself alone when it is
        not merged)."""
        for span in self.merged:
            if span[0] <= row <= span[2] and span[1] <= column <= span[3]:
                return span
        return row, column, row, column

    def span_box(self, span: Span) -> Box:
        """The box of the cells ``span`` covers."""
        xs, ys = self.xs, self.ys
        return xs[span[1]], ys[span[0]], xs[span[3] + 1], ys[span[2] + 1]

    def cell_at(self, x: float, y: float) -> tuple[int, int] | None:
        """The row and column of the grid at a point, None outside the table."""
        if not (self.box[0] <= x <= self.box[2] and self.box[1] <= y <= self.box[3]):
            return None
        row = sum(1 for line in self.rows if y >= line)
        column = sum(1 for line in self.columns if x >= line)
        return row, column

    # -- the form in the configuration and the reading -----------------------------------------
    def as_dict(self) -> dict[str, Any]:
        """The region for the configuration (and, without the grid, the reading)."""
        d: dict[str, Any] = {"kind": self.kind, "box": [round(v, 3) for v in self.box],
                             "by": self.by}
        if self.kind == "table":
            d["columns"] = [round(v, 3) for v in self.columns]
            d["rows"] = [round(v, 3) for v in self.rows]
            d["merged"] = [list(span) for span in self.merged]
        if self.confidence is not None:
            d["confidence"] = round(self.confidence, 3)
        return d

    @classmethod
    def from_dict(cls, d: Any) -> Region:
        """A region from the configuration; anything not of its kind or out of its range
        is a "bad-config" (reason "field")."""
        try:
            region = cls(kind=d["kind"], box=tuple(float(v) for v in d["box"]),  # type: ignore[arg-type]
                         by=d.get("by", "auto"),
                         columns=[float(v) for v in d.get("columns", [])],
                         rows=[float(v) for v in d.get("rows", [])],
                         merged=[tuple(int(v) for v in span) for span in d.get("merged", [])],  # type: ignore[misc]
                         confidence=(None if d.get("confidence") is None
                                     else float(d["confidence"])))
        except (KeyError, TypeError, ValueError) as e:
            raise OptdocError("bad-config", reason="field") from e
        if not region.valid():
            raise OptdocError("bad-config", reason="field")
        return region

    def valid(self) -> bool:
        """True when the region is of a known kind and its box and grid make sense."""
        x0, y0, x1, y1 = self.box
        if self.kind not in KINDS or self.by not in BY or len(self.box) != 4:
            return False
        if x1 - x0 < SMALLEST or y1 - y0 < SMALLEST:
            return False
        if self.kind != "table":
            return not (self.columns or self.rows or self.merged)
        for lines, low, high in ((self.columns, x0, x1), (self.rows, y0, y1)):
            edges = [low, *lines, high]
            if any(b - a < SMALLEST for a, b in zip(edges, edges[1:], strict=False)):
                return False
        n_rows, n_columns = self.size
        covered: set[tuple[int, int]] = set()
        for r0, c0, r1, c1 in self.merged:
            if not (0 <= r0 <= r1 < n_rows and 0 <= c0 <= c1 < n_columns):
                return False
            if r0 == r1 and c0 == c1:
                return False  # one cell is no merge
            cells = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)}
            if cells & covered:
                return False
            covered |= cells
        return True


def copy(region: Region) -> Region:
    """An independent copy of a region."""
    return Region(region.kind, tuple(region.box), region.by, list(region.columns),  # type: ignore[arg-type]
                  list(region.rows), list(region.merged), region.confidence)


def rounded(region: Region) -> Region:
    """A region as the configuration keeps it: positions to a thousandth of a point, the
    confidence to three places; the result is made from these, live or reproduced."""
    return Region(region.kind, tuple(round(v, 3) for v in region.box),  # type: ignore[arg-type]
                  region.by, [round(v, 3) for v in region.columns],
                  [round(v, 3) for v in region.rows], list(region.merged),
                  None if region.confidence is None else round(region.confidence, 3))


# -- what the regions make of the words ---------------------------------------------------------
Word = tuple[str, Box]


def _middle(box: Box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _contains(box: Box, x: float, y: float) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def region_of(regions: list[Region], box: Box) -> int | None:
    """The region a word with ``box`` belongs to, by its middle: of the regions that hold
    it, the smallest (a region drawn within another wins); None for none."""
    x, y = _middle(box)
    holding = [k for k, r in enumerate(regions) if _contains(r.box, x, y)]
    if not holding:
        return None
    return min(holding, key=lambda k: (regions[k].box[2] - regions[k].box[0])
               * (regions[k].box[3] - regions[k].box[1]))


def is_read(regions: list[Region], box: Box) -> bool:
    """True unless the word with ``box`` lies in a region that is not read."""
    k = region_of(regions, box)
    return k is None or regions[k].kind not in NOT_READ


def _cell_text(words: list[Word]) -> str:
    """The words of one cell as text: lines top to bottom (a word belongs to the line
    whose middle it shares), each left to right, joined by spaces."""
    if not words:
        return ""
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: _middle(w[1])[1]):
        middle = _middle(word[1])[1]
        if lines:
            last = lines[-1]
            height = max(b[3] - b[1] for _t, b in last)
            if abs(middle - sum(_middle(b)[1] for _t, b in last) / len(last)) <= height / 2:
                last.append(word)
                continue
        lines.append([word])
    return " ".join(" ".join(t for t, _b in sorted(line, key=lambda w: w[1][0]))
                    for line in lines).strip()


def table_of(region: Region, words: list[Word]) -> Table:
    """The table a table region makes of the words of the page: every word whose middle
    lies in a cell goes into that cell (of merged cells, into the first, which carries
    the box of all of them; the others stay empty)."""
    n_rows, n_columns = region.size
    held: dict[tuple[int, int], list[Word]] = {}
    for word in words:
        at = region.cell_at(*_middle(word[1]))
        if at is not None:
            span = region.span_of(*at)
            held.setdefault((span[0], span[1]), []).append(word)
    rows: list[list[Cell]] = []
    for r in range(n_rows):
        row = []
        for c in range(n_columns):
            span = region.span_of(r, c)
            first = (span[0], span[1]) == (r, c)
            box = region.span_box(span) if first else region.span_box((r, c, r, c))
            row.append(Cell(_cell_text(held.get((r, c), [])) if first else "", box))
        rows.append(row)
    return Table(rows, 1.0 if region.confidence is None else region.confidence,
                 by=region.by)


def from_table(table: Table) -> Region:
    """A table region from a table found automatically (:mod:`optdoc.tables`): its box,
    and the lines between its rows and columns where its cells meet."""
    first = table.rows[0]
    columns = sorted(_middle_of([row[c].box[2] for row in table.rows if len(row) > c])
                     for c in range(len(first) - 1))
    rows = sorted(_middle_of([c.box[3] for c in row]) for row in table.rows[:-1])
    region = Region("table", table.box, "auto", columns, rows, [], table.confidence)
    region.columns = _spaced(region.columns, region.box[0], region.box[2])
    region.rows = _spaced(region.rows, region.box[1], region.box[3])
    return region


def _middle_of(values: list[float]) -> float:
    """The median of some positions."""
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _spaced(lines: list[float], low: float, high: float) -> list[float]:
    """Lines strictly between ``low`` and ``high``, each at least SMALLEST from the last."""
    kept: list[float] = []
    for line in sorted(lines):
        if line - (kept[-1] if kept else low) >= SMALLEST and high - line >= SMALLEST:
            kept.append(line)
    return kept


# -- changing a grid (what the window does) -------------------------------------------------------
def _shifted(merged: list[Span], axis: int, at: int, by: int) -> list[Span]:
    """Merged spans with every index from ``at`` on (rows: axis 0, columns: axis 1)
    moved by ``by``; a span reaching over ``at`` grows with it."""
    out = []
    for span in merged:
        s = list(span)
        first, last = (0, 2) if axis == 0 else (1, 3)
        if s[first] >= at:
            s[first] += by
        if s[last] >= at:
            s[last] += by
        out.append(tuple(s))
    return [s for s in out if s[0] <= s[2] and s[1] <= s[3]]  # type: ignore[misc]


def add_line(region: Region, axis: int, at: float) -> Region:
    """A new column line at x (``axis`` 1) or row line at y (``axis`` 0); merged cells
    it crosses stay merged.  Unchanged where the line would come too close to another."""
    out = copy(region)
    lines = out.rows if axis == 0 else out.columns
    low, high = (out.box[1], out.box[3]) if axis == 0 else (out.box[0], out.box[2])
    edges = [low, *lines, high]
    if any(abs(at - e) < SMALLEST for e in edges) or not low < at < high:
        return region
    index = sum(1 for line in lines if line < at)  # the cell the line splits
    lines.insert(index, at)
    out.merged = _shifted(out.merged, axis, index + 1, 1)
    # a merged span that ended at the split cell now also covers its new neighbour
    grown = []
    for span in out.merged:
        s = list(span)
        first, last = (0, 2) if axis == 0 else (1, 3)
        if s[first] <= index and s[last] == index:
            s[last] = index + 1
        grown.append(tuple(s))
    out.merged = grown  # type: ignore[assignment]
    out.by, out.confidence = "person", None  # a person is sure of it
    return out


def remove_line(region: Region, axis: int, index: int) -> Region:
    """Take away the ``index``-th inner row line (``axis`` 0) or column line (``axis``
    1): the cells on both sides become one row or column."""
    out = copy(region)
    lines = out.rows if axis == 0 else out.columns
    if not 0 <= index < len(lines):
        return region
    del lines[index]
    out.merged = _consolidated(_shifted(out.merged, axis, index + 1, -1))
    out.by, out.confidence = "person", None  # a person is sure of it
    return out


def _consolidated(spans: list[Span]) -> list[Span]:
    """Merged spans without overlaps (overlapping ones become one) and without single
    cells."""
    result: list[Span] = []
    for span in spans:
        r0, c0, r1, c1 = span
        changed = True
        while changed:
            changed = False
            for s in list(result):
                if s[0] <= r1 and s[2] >= r0 and s[1] <= c1 and s[3] >= c0:
                    result.remove(s)
                    r0, c0, r1, c1 = min(r0, s[0]), min(c0, s[1]), max(r1, s[2]), max(c1, s[3])
                    changed = True
        result.append((r0, c0, r1, c1))
    return [s for s in result if not (s[0] == s[2] and s[1] == s[3])]


def move_line(region: Region, axis: int, index: int, at: float) -> Region:
    """Move the ``index``-th inner row (``axis`` 0) or column line (``axis`` 1) to
    ``at``, kept between its neighbours."""
    out = copy(region)
    lines = out.rows if axis == 0 else out.columns
    if not 0 <= index < len(lines):
        return region
    low, high = (out.box[1], out.box[3]) if axis == 0 else (out.box[0], out.box[2])
    before = lines[index - 1] if index > 0 else low
    after = lines[index + 1] if index + 1 < len(lines) else high
    lines[index] = min(max(at, before + SMALLEST), after - SMALLEST)
    out.by, out.confidence = "person", None  # a person is sure of it
    return out


def merge(region: Region, span: Span) -> Region:
    """Merge the cells ``span`` covers, together with any merged cells it touches."""
    r0, c0, r1, c1 = min(span[0], span[2]), min(span[1], span[3]), \
        max(span[0], span[2]), max(span[1], span[3])
    out = copy(region)
    out.merged = _consolidated([*out.merged, (r0, c0, r1, c1)])
    out.by, out.confidence = "person", None  # a person is sure of it
    return out


def split(region: Region, row: int, column: int) -> Region:
    """Undo the merge the cell at ``row``, ``column`` belongs to."""
    out = copy(region)
    out.merged = [s for s in out.merged if not (s[0] <= row <= s[2] and s[1] <= column <= s[3])]
    out.by, out.confidence = "person", None  # a person is sure of it
    return out


def moved(region: Region, box: Box) -> Region:
    """The region with a new box; a table's lines go with it, in proportion, and merged
    cells stay merged."""
    out = copy(region)
    (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = region.box, box
    fx = (bx1 - bx0) / max(ax1 - ax0, SMALLEST)
    fy = (by1 - by0) / max(ay1 - ay0, SMALLEST)
    out.box = (min(bx0, bx1), min(by0, by1), max(bx0, bx1), max(by0, by1))
    out.columns = [bx0 + (x - ax0) * fx for x in region.columns]
    out.rows = [by0 + (y - ay0) * fy for y in region.rows]
    if not out.valid():  # squeezed below the smallest row or column: the grid goes
        out.columns, out.rows, out.merged = [], [], []
    out.by, out.confidence = "person", None  # a person is sure of it
    return out


def regions_from_dicts(value: Any) -> list[Region]:
    """The regions of a page from the configuration (a list)."""
    if not isinstance(value, list):
        raise OptdocError("bad-config", reason="field")
    return [Region.from_dict(d) for d in value]
