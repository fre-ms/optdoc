"""Layout of a recognised page as Markdown: paragraphs, headings, lists and tables.

OCR hands over lines.  A language model wants the text the way the document meant
it: paragraphs in one piece, headings marked, lists and tables kept apart.  The
geometry of the lines tells the layout: a line that runs to the right margin goes on
in the next one; a gap taller than the usual line spacing ends a paragraph; a line in
a larger face, or a short bold line on its own, is a heading; a bullet starts a list
item; big gaps inside a line (tabs in the page text, see
:func:`~optdoc.ocr.page_text_from_words`) are table cells.

The roles are computed once from the OCR geometry and applied to the page text later,
raw or with the pseudonyms in place: both have the same lines.  Italics are not
recognised: the engines report no slant, and a stroke-angle guess is not reliable
enough to mark text with.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from itertools import groupby, pairwise
from statistics import median
from typing import Any

import pymupdf

from optdoc.pagetext import Box, PageText

_BULLET = re.compile(r"^(?:(?P<symbol>[-•·▪◦●○■□*–—>])|(?P<number>\d{1,2}[.)])"
                          r"|(?P<letter>[a-zA-Z][.)]))\s+(?=\S)")
# "Diagnosen:", "Medikation:", "Aktuelle Medikation:" at the start of a line open a block of
# their own even after a line that ran to the margin
_LABEL = re.compile(r"^[A-ZÄÖÜ][\wäöüß./-]{1,24}(?: [\wäöüß./-]{1,24}){0,2}:\s")
HEADING_LARGE = 3  # Markdown levels below the page headings of the Markdown file
HEADING_SMALL = 4
_SEPARATOR_TEXT = {"word": " ", "line": "\n"}  # what a separator puts between two pieces


@dataclass
class Line:
    """One OCR line: its span in the page text and its box in page points."""

    start: int
    end: int
    text: str
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    height: float = 0.0

    @property
    def empty(self) -> bool:
        """True for a line without visible text or without a box of its own."""
        return not self.text.strip() or self.x1 <= self.x0

    @property
    def width(self) -> float:
        """Width of the line's box in page points."""
        return self.x1 - self.x0


@dataclass
class Role:
    """What a line is and how it attaches to the line before it."""

    kind: str = "paragraph"  # paragraph, heading, list, table
    level: int = 0  # heading level
    bold: bool = False
    # paragraph (blank line), line (newline), word (space), syllable (joined without a space)
    separator: str = "paragraph"
    table: int = -1


GRID = 1000  # tables with a known grid are numbered from here, apart from those found by gaps


@dataclass
class Structure:
    """The roles of the lines of one page; :meth:`render` turns a page text into
    Markdown.  Built by :func:`analyse_structure`; tables whose grid is known come in
    with :meth:`use_tables`."""

    roles: list[Role] = field(default_factory=list)
    grids: dict[int, list[list[str]]] = field(default_factory=dict)

    def use_tables(self, page_text: PageText,
                   tables: list[tuple[Box, list[list[str]]]]) -> None:
        """Tables whose grid is known (a box and the texts of its cells, row by row,
        :mod:`optdoc.layout`): the lines whose middle lies in a table's box are its rows,
        and the table is written from its cells, not from the gaps between words."""
        lines = lines_of(page_text)
        for k, (box, rows) in enumerate(tables):
            self.grids[GRID + k] = rows
            for line, role in zip(lines, self.roles, strict=False):
                x, y = (line.x0 + line.x1) / 2, (line.y0 + line.y1) / 2
                if not line.empty and box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                    role.kind, role.table = "table", GRID + k

    @property
    def tables(self) -> int:
        """Number of tables on the page."""
        return len({r.table for r in self.roles if r.kind == "table"})

    @property
    def headings(self) -> int:
        """Number of headings on the page."""
        return sum(1 for r in self.roles if r.kind == "heading")

    def render(self, text: str) -> str:
        """Markdown of ``text``, which must have the lines the roles were computed for
        (the raw OCR text or that text with pseudonyms).  Anything else comes back as
        it is."""
        segments = self._segments(text)
        if segments is None:
            return text
        return "\n\n".join(b for b in _blocks(self.roles, segments, self.grids)
                           if b.strip()) + "\n"

    def _segments(self, text: str) -> list[str] | None:
        """The lines of ``text`` when they match the roles one to one (a trailing
        newline is tolerated), else None."""
        segments = text.split("\n")
        if len(segments) == len(self.roles) + 1 and segments[-1] == "":
            segments.pop()
        return segments if len(segments) == len(self.roles) else None


# -- blocks ----------------------------------------------------------------------------------------
_Piece = tuple[Role, str]  # a role with the raw text of its line


def _block_key(idx: int, piece: _Piece) -> tuple[str, int]:
    """Consecutive lines with the same key form one Markdown block: the rows of a table
    by its number, the lines of a list, a heading by itself, and runs of ordinary
    lines, which the separators then split into paragraphs."""
    role = piece[0]
    if role.kind == "table":
        return "table", role.table
    if role.kind == "heading":
        return "heading", idx
    if role.kind == "list":
        return "list", 0
    return "paragraph", 0


def _blocks(roles: list[Role], segments: list[str],
            grids: dict[int, list[list[str]]] | None = None) -> Iterator[str]:
    """The Markdown blocks of a page in order; some of them may be empty.  A table whose
    grid is known (``grids``) is written once, where its first line is, from its cells."""
    paragraph = _Paragraph()
    numbered = enumerate(zip(roles, segments, strict=True))
    written: set[int] = set()
    for (kind, key), run in groupby(numbered, key=lambda p: _block_key(*p)):
        pieces = [piece for _i, piece in run]
        if kind == "paragraph":
            yield from _paragraph_blocks(pieces, paragraph)
            continue
        yield paragraph.closing()
        if kind == "table" and grids and key in grids:
            if key not in written:
                written.add(key)
                yield _table(grids[key])
            continue
        yield _BLOCK_BUILDERS[kind](pieces)
    yield paragraph.closing()


def _paragraph_blocks(pieces: list[_Piece], paragraph: _Paragraph) -> Iterator[str]:
    """Feeds ordinary lines into ``paragraph`` and yields a paragraph wherever a line opens
    a new one; empty lines are skipped.  The last paragraph stays open in ``paragraph``."""
    for role, raw in pieces:
        text = raw.strip()
        if not text:
            continue
        if role.separator == "paragraph":
            yield paragraph.closing()
        paragraph.append_char(text, role.bold, role.separator)


def _table_block(pieces: list[_Piece]) -> str:
    """Markdown table of the rows; the tabs of the page text are the cell boundaries."""
    return _table([[cell.strip() for cell in raw.split("\t")] for _role, raw in pieces])


def _heading_block(pieces: list[_Piece]) -> str:
    """Markdown heading of the one line; empty for a line without text."""
    role, raw = pieces[0]
    text = raw.strip()
    return "#" * role.level + " " + text if text else ""


def _list_block(pieces: list[_Piece]) -> str:
    """Markdown list of the lines; a line joined by word or syllable continues the item
    before it."""
    points: list[str] = []
    for role, raw in pieces:
        text = raw.strip()
        if points and role.separator in ("word", "syllable"):
            points[-1] = _append(points[-1], text, role.separator)
        elif text:
            points.append(_list_item(text))
    return "\n".join(points)


_BLOCK_BUILDERS: dict[str, Callable[[list[_Piece]], str]] = {
    "table": _table_block, "heading": _heading_block, "list": _list_block}


class _Paragraph:
    """Collects the pieces of one paragraph: joined with spaces, newlines or across a
    hyphen; bold runs are wrapped in ``**``."""

    def __init__(self) -> None:
        """Starts with no pieces."""
        self.parts: list[tuple[str, str, bool]] = []  # (trenner, text, fett)

    def append_char(self, text: str, bold: bool, separator: str) -> None:
        """Adds a piece; the first piece of a paragraph needs no separator."""
        if not self.parts:
            separator = "paragraph"
        self.parts.append((separator, text, bold))

    def closing(self) -> str:
        """The paragraph as Markdown; the collector is empty afterwards.  A bold run
        stays open across a space when the next piece is bold too, any other join
        closes it."""
        out = ""
        pending = False  # inside a bold run
        for separator, text, bold in self.parts:
            out, joint = _joint(out, separator)
            still_bold = pending and bold and joint == " "
            if pending and not still_bold:
                out += "**"
            out += joint
            if bold and not still_bold:
                out += "**"
            out += text
            pending = bold
        self.parts = []
        return out + "**" if pending else out


def _joint(so_far: str, separator: str) -> tuple[str, str]:
    """``so_far`` made ready for the next piece, and the string to put between them: a
    syllable join drops the hyphen at the end, a word join puts a space, a line join a
    newline, a paragraph start nothing."""
    if separator == "syllable" and so_far.rstrip().endswith("-"):
        return so_far.rstrip()[:-1], ""
    return so_far, _SEPARATOR_TEXT.get(separator, "")


def _append(so_far: str, text: str, separator: str) -> str:
    """``text`` joined to a list item: across the hyphen for a syllable join, else with
    a space."""
    if separator == "syllable" and so_far.rstrip().endswith("-"):
        return so_far.rstrip()[:-1] + text
    return so_far + " " + text


def _list_item(text: str) -> str:
    """The line as a Markdown list item: numbers keep their number, letters stay as
    text of a bullet item, symbols become the bullet."""
    m = _BULLET.match(text)
    if m is None:
        return "- " + text
    rest = text[m.end():]
    if m.group("number"):
        return m.group("number").rstrip(")") .rstrip(".") + ". " + rest
    if m.group("letter"):
        return "- " + m.group("letter") + " " + rest
    return "- " + rest


def _table(rows: list[list[str]]) -> str:
    """Markdown table of the rows, the first one as header; short rows are padded."""
    columns = max(len(r) for r in rows)
    rows = [r + [""] * (columns - len(r)) for r in rows]
    cell = lambda c: c.replace("|", "\\|")  # noqa: E731
    lines = ["| " + " | ".join(cell(c) for c in rows[0]) + " |",
              "|" + " --- |" * columns]
    lines += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


# -- geometry --------------------------------------------------------------------------------------
def lines_of(page_text: PageText) -> list[Line]:
    """The lines of a page text with their boxes (from the character boxes)."""
    segments = page_text.text.split("\n")
    if page_text.text.endswith("\n"):
        segments.pop()
    lines: list[Line] = []
    start = 0
    for text in segments:
        lines.append(_line_with_box(page_text, start, text))
        start += len(text) + 1
    return lines


def _line_with_box(page_text: PageText, start: int, text: str) -> Line:
    """The line ``text`` at ``start`` of the page text with the box around its
    characters; a line without boxes keeps the zero box."""
    end = start + len(text)
    boxes = [(box, chars) for box, chars
             in zip(page_text.boxes[start:end], text, strict=False) if box is not None]
    if not boxes:
        return Line(start, end, text)
    return Line(start, end, text,
                 x0=min(b[0] for b, _z in boxes), y0=min(b[1] for b, _z in boxes),
                 x1=max(b[2] for b, _z in boxes), y1=max(b[3] for b, _z in boxes),
                 height=_line_height(boxes))


def _line_height(boxes: list[tuple[Box, str]]) -> float:
    """Median height of the letter and digit boxes, or of all boxes when the line has
    none: punctuation sits lower than the face."""
    heights = [b[3] - b[1] for b, z in boxes if z.isalnum()] or [b[3] - b[1] for b, _z in boxes]
    return median(heights)


def bold_lines(lines: list[Line], grey: Any, scale: float) -> set[int]:
    """Indices of lines whose ink coverage stands well above the page's median: bold
    face.  ``grey`` is a 2-D uint8 array at ``scale`` pixels per point."""
    import numpy as np

    image = np.asarray(grey)
    densities = {idx: d for idx, z in enumerate(lines)
               if (d := _ink_density(z, image, scale)) is not None}
    if len(densities) < 4:
        return set()
    middle = median(densities.values())
    if middle <= 0:
        return set()
    return {i for i, d in densities.items() if _clearly_darker(d, middle)}


def _ink_density(z: Line, image: Any, scale: float) -> float | None:
    """Share of dark pixels in the line's box on the grey rendering, or None for a line
    with fewer than three letters or digits or a box too small to measure."""
    if z.empty or _alnum(z.text) < 3:
        return None
    h, w = image.shape[:2]
    x0, y0 = max(0, int(z.x0 * scale)), max(0, int(z.y0 * scale))
    x1, y1 = min(w, int(z.x1 * scale) + 1), min(h, int(z.y1 * scale) + 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    band = image[y0:y1, x0:x1]
    return float((band < 128).mean())


def _clearly_darker(density: float, middle: float) -> bool:
    """True when an ink coverage stands well above the page's median both in ratio and
    in absolute terms, so that a faint page does not turn every line bold."""
    return density >= 1.45 * middle and density - middle >= 0.06


# -- roles -----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _PageMeasure:
    """Typical measures of the printed lines of a page, the yardstick of every rule:
    median line height, left and right text edge (the 10th and 90th percentile of the
    line edges, so that a stray word does not move them), their distance and the median
    gap between consecutive lines."""

    height: float
    left: float
    right: float
    width: float
    space: float

    @classmethod
    def out(cls, printed: list[Line]) -> _PageMeasure:
        """Measures of the printed lines of a page (at least one)."""
        height = _typical_height(printed)
        left, right = _text_edges(printed)
        return cls(height, left, right, max(right - left, height),
                   _line_spacing(printed, height))

    @property
    def paragraph_gap(self) -> float:
        """Gap above which a line starts a paragraph of its own."""
        return self.space + 0.5 * self.height


def _typical_height(printed: list[Line]) -> float:
    """Median height of the lines with a measured height; 10 points when none has one."""
    heights = [z.height for z in printed if z.height > 0]
    return median(heights) if heights else 10.0


def _text_edges(printed: list[Line]) -> tuple[float, float]:
    """Left and right text edge: the 10th percentile of the line starts and the 90th of
    the line ends, so that a stray word does not move them."""
    xs0 = sorted(z.x0 for z in printed)
    xs1 = sorted(z.x1 for z in printed)
    return xs0[len(xs0) // 10], xs1[(len(xs1) * 9) // 10]


def _line_spacing(printed: list[Line], height: float) -> float:
    """Median gap between consecutive lines, leaving out overlaps and paragraph gaps;
    three tenths of the line height when no gap is usual."""
    spaces = [b.y0 - a.y1 for a, b in pairwise(printed)]
    normal = [g for g in spaces if -0.3 * height < g < 1.0 * height]
    return median(normal) if normal else 0.3 * height


def analyse_structure(page_text: PageText, bold: set[int] | None = None) -> Structure:
    """Roles of the lines of an OCR page from their geometry (see the module notes):
    tables first, then headings and list items, then how each line attaches to the
    one before it."""
    lines = lines_of(page_text)
    roles = [Role() for _ in lines]
    printed = [z for z in lines if not z.empty]
    if not printed:
        return Structure(roles)
    measure = _PageMeasure.out(printed)
    _mark_tables(lines, roles)
    _mark_line_kinds(lines, roles, bold or set(), measure)
    _join_lines(lines, roles, measure)
    return Structure(roles)


def _mark_tables(lines: list[Line], roles: list[Role]) -> None:
    """Numbers the tables of the page: every run of lines with cell gaps, and a single
    such line only when it has at least three cells, because two cells alone are as
    likely a label with its value."""
    tables = (run for run in _cell_runs(lines) if _is_table(lines, *run))
    for number, (start, end) in enumerate(tables):
        for role in roles[start:end]:
            role.kind, role.table = "table", number


def _cell_runs(lines: list[Line]) -> Iterator[tuple[int, int]]:
    """Index ranges ``(start, ende)`` of consecutive lines that contain a cell gap."""
    for with_cells, run in groupby(range(len(lines)), key=lambda i: "\t" in lines[i].text):
        if with_cells:
            indices = list(run)
            yield indices[0], indices[-1] + 1


def _is_table(lines: list[Line], start: int, end: int) -> bool:
    """A run of at least two lines with cell gaps, or one line with at least three cells."""
    return end - start >= 2 or lines[start].text.count("\t") >= 2


def _mark_line_kinds(lines: list[Line], roles: list[Role], bold: set[int],
                          measure: _PageMeasure) -> None:
    """Marks every printed line outside the tables as heading, list item or ordinary
    line, and notes bold face on all but headings."""
    for idx, (z, role) in enumerate(zip(lines, roles, strict=True)):
        if z.empty or role.kind == "table":
            continue
        role.kind, role.level = _line_kind(z, idx in bold, measure)
        role.bold = idx in bold and role.kind != "heading"


def _line_kind(z: Line, bold: bool, measure: _PageMeasure) -> tuple[str, int]:
    """Kind and heading level of a printed line: a larger face is a heading (two sizes
    give two levels), a bullet or number opens a list item, and a short line that is
    bold or in capitals and does not end a sentence is a small heading."""
    text = z.text.strip()
    if _alnum(text) >= 2 and z.height >= 1.3 * measure.height:
        level = HEADING_LARGE if z.height >= 1.6 * measure.height else HEADING_SMALL
        return "heading", level
    if _BULLET.match(text):
        return "list", 0
    if _short_emphasised_line(z, bold, measure):
        return "heading", HEADING_SMALL
    return "paragraph", 0


def _short_emphasised_line(z: Line, bold: bool, measure: _PageMeasure) -> bool:
    """A short line in bold or in capitals that does not end with a full stop or comma:
    a heading set in the running face."""
    text = z.text.strip()
    return (_is_short(z, measure) and _alnum(text) >= 3 and (bold or _is_capitals(text))
            and not text.endswith((".", ",")))


def _alnum(text: str) -> int:
    """Number of letters and digits in ``text``."""
    return sum(c.isalnum() for c in text)


def _is_capitals(text: str) -> bool:
    """True for at least four letters, all of them capitals."""
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def _is_short(z: Line, measure: _PageMeasure) -> bool:
    """True for a line narrower than six tenths of the text width."""
    return z.width < 0.6 * measure.width


def _join_lines(lines: list[Line], roles: list[Role], measure: _PageMeasure) -> None:
    """Sets how every printed line attaches to the printed line before it.  The first
    printed line keeps the default: it opens a paragraph."""
    printed = [(z, r) for z, r in zip(lines, roles, strict=True) if not z.empty]
    for (previous, previous_role), (z, role) in pairwise(printed):
        _join_with_previous(z, role, previous, previous_role, measure)


def _join_with_previous(z: Line, role: Role, previous: Line, previous_role: Role,
                           measure: _PageMeasure) -> None:
    """Decides the separator of ``z`` after ``previous``.  Tables, headings and list items
    settle it by themselves; an ordinary line hanging under a list item becomes part of
    that item; between two ordinary lines the geometry decides."""
    fixed = _block_separators(role, previous_role)
    if fixed is not None:
        role.separator = fixed
    elif previous_role.kind != "list":
        role.separator = _paragraph_separator(z, previous, measure)
    elif _hangs_under_list_item(z, previous, measure):
        role.kind, role.separator = "list", _word_joint(previous, z)
    else:
        role.separator = "paragraph"


def _block_separators(role: Role, previous_role: Role) -> str | None:
    """Separator settled by the block kinds alone: the rows of one table follow each
    other on new lines and so do list items; any other table boundary, a heading on
    either side and a list item after a non-list line open a block.  None when both
    lines are ordinary or the line hangs under a list item."""
    if role.kind == "table" or previous_role.kind == "table":
        same = role.kind == "table" and role.table == previous_role.table
        return "line" if same else "paragraph"
    if role.kind == "heading" or previous_role.kind == "heading":
        return "paragraph"
    if role.kind == "list":
        return "line" if previous_role.kind == "list" else "paragraph"
    return None


def _hangs_under_list_item(z: Line, previous: Line, measure: _PageMeasure) -> bool:
    """True for a line close under a list item and indented past its bullet: the item
    goes on in it."""
    return _gap(z, previous) <= measure.paragraph_gap and z.x0 >= previous.x0 + 0.8 * measure.height


def _paragraph_separator(z: Line, previous: Line, measure: _PageMeasure) -> str:
    """How an ordinary line attaches to the ordinary line before it: a tall gap or a
    fresh indent opens a paragraph; a predecessor that ran to the margin goes on in
    this line, unless the line opens a labelled block; a colon line before a long line
    opens a block; otherwise the lines stay lines of one block."""
    if _gap(z, previous) > measure.paragraph_gap or _newly_indented(z, previous, measure):
        return "paragraph"
    if _to_the_margin(previous, measure):
        return "paragraph" if _opens_label(z, previous) else _word_joint(previous, z)
    if previous.text.rstrip().endswith(":") and not _is_short(z, measure):
        return "paragraph"
    return "line"


def _gap(z: Line, previous: Line) -> float:
    """Vertical gap between the bottom of ``previous`` and the top of ``z``."""
    return z.y0 - previous.y1


def _newly_indented(z: Line, previous: Line, measure: _PageMeasure) -> bool:
    """True when the line is indented well past the left edge while the line before it
    was not: a paragraph that starts with an indent."""
    return (z.x0 - measure.left > 1.2 * measure.height
            and previous.x0 - measure.left <= 0.6 * measure.height)


def _to_the_margin(previous: Line, measure: _PageMeasure) -> bool:
    """True when the line reaches nearly the right text edge: it goes on in the next."""
    return previous.x1 >= measure.right - 0.12 * measure.width


def _opens_label(z: Line, previous: Line) -> bool:
    """True when the line starts with a label such as "Diagnosen:" and the line before
    it does not end in a hyphen: the label opens a block of its own."""
    return _LABEL.match(z.text.strip()) is not None and not previous.text.rstrip().endswith("-")


def _word_joint(previous: Line, z: Line) -> str:
    """How a continuation line joins the line before it: across the hyphen when that
    line ends in one and this line starts in lower case, otherwise with a space."""
    syllable = previous.text.rstrip().endswith("-") and z.text.strip()[:1].islower()
    return "syllable" if syllable else "word"


def analyse_page_structure(page: pymupdf.Page, ocr: PageText, dpi: int = 100) -> Structure:
    """Roles of an OCR page including bold detection on a grey rendering of the page
    (needs NumPy; without it there is no bold)."""
    lines = lines_of(ocr)
    bold: set[int] = set()
    try:
        import numpy as np

        scale = dpi / 72.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY,
                              alpha=False)
        grey = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        bold = bold_lines(lines, grey, scale)
    except ImportError:
        pass
    return analyse_structure(ocr, bold)
