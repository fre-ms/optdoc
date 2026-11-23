"""The invisible text layer of a searchable PDF, written line by line.

A program that takes the text out of a PDF (PDFKit, MuPDF, pdf.js, Poppler) builds its
lines from the positions of the glyphs.  Words laid on the page one by one, each on a
baseline of its own and with no space between them, come out glued together
("Abnahme:05.10.202607:45") or split where a row of a table is a little skewed.  So
every OCR line becomes one text object here, much as Tesseract's PDF writer does
it:

- the words of the line sit on one baseline, a straight line fitted through the word
  boxes, so that a slightly tilted line stays one line;
- every word is scaled (``Tz``) to the width of the printed word, so that a search or
  a selection covers it and a program reading positions finds it where it is printed;
- between two words stands a real space, stretched over the gap, so that words are
  never glued together and the line runs on without a jump (MuPDF starts a new line
  at a jump, PDFKit splits a table into columns at gaps it has to guess);
- the font has a single glyph, a box over the em, which every character of the Basic
  Multilingual Plane is drawn with, and a ``ToUnicode`` map gives each its own code,
  so that "≤", "↑" or "µ" are written as they were read (the standard fonts know only
  Windows-1252).

Text render mode 3 makes it invisible.  The font is a few hundred bytes, built here.
Measured on photographed invented laboratory reports, read by PDFKit as medorello does:
every row of the table came out as one line, as with the former word-by-word layer,
but with real spaces between the words, where PDFKit and MuPDF used to glue some
together.  With empty glyphs PDFKit read every word as a line of its own; with words
placed one by one and no space over the gaps, MuPDF read every word of a table row as
a line of its own.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from statistics import median

import pymupdf

from optdoc.pagetext import PageText

FONT_NAME = "OptdocInvisible"
RESOURCE = "FOptdocOCR"  # the name of the font in a page's resources
EM = 1000  # font units per em
ASCENT, DESCENT = 800, -200  # a glyph box spans the em: CoreGraphics wants a descent
ADVANCE = 500  # the width of every glyph, in font units
MAX_SLOPE = math.tan(math.radians(3.0))  # a steeper fit is noise: such a page is straightened
REPLACEMENT = 0xFFFD  # what a character outside the Basic Multilingual Plane becomes


# -- the font ----------------------------------------------------------------------------------
def _checksum(data: bytes) -> int:
    """The TrueType checksum of a table: its 32-bit words added up."""
    padded = data + b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(padded) // 4}I", padded)) & 0xFFFFFFFF


def _name_table() -> bytes:
    """The naming table: family, style, unique name, full name and PostScript name, in
    UTF-16 for Windows (platform 3, encoding 1, English)."""
    names = {1: FONT_NAME, 2: "Regular", 3: f"{FONT_NAME} 1.0", 4: FONT_NAME, 6: FONT_NAME}
    records, strings = b"", b""
    for name_id, text in names.items():
        raw = text.encode("utf-16-be")
        records += struct.pack(">6H", 3, 1, 0x409, name_id, len(raw), len(strings))
        strings += raw
    return struct.pack(">3H", 0, len(names), 6 + len(records)) + records + strings


def _box_glyph() -> bytes:
    """The glyph every character is drawn with: a rectangle over the whole em, from the
    descent to the ascent.  It is never seen (render mode 3), but PDFKit builds its lines
    from the glyphs' bounds; with empty glyphs it read every word as a line of its own."""
    points = ((0, DESCENT), (ADVANCE, DESCENT), (ADVANCE, ASCENT), (0, ASCENT))
    xs = [b[0] - a[0] for a, b in zip(((0, 0), *points), points, strict=False)]
    ys = [b[1] - a[1] for a, b in zip(((0, 0), *points), points, strict=False)]
    glyph = (struct.pack(">5h", 1, 0, DESCENT, ADVANCE, ASCENT) + struct.pack(">HH", 3, 0)
             + bytes([0x01] * 4) + struct.pack(">4h", *xs) + struct.pack(">4h", *ys))
    return glyph + b"\0" * (-len(glyph) % 4)


def _tables() -> dict[bytes, bytes]:
    """The tables of a TrueType font with two glyphs, both ``ADVANCE`` wide: .notdef,
    empty, and the box every character is drawn with; ascent and descent span the em."""
    glyph = _box_glyph()
    # a format-4 subtable with nothing but its closing segment: no character has a glyph
    # of its own, which is right, since the PDF maps every code to the box
    cmap_format4 = struct.pack(">7H", 4, 24, 0, 2, 2, 0, 0) + struct.pack(">5H", 0xFFFF, 0,
                                                                          0xFFFF, 1, 0)
    os2 = (  # version 4: widths and classes, sub- and superscript, strikeout, family class
        struct.pack(">HhHHH", 4, ADVANCE, 400, 5, 0)
        + struct.pack(">10h", 650, 600, 0, 75, 650, 600, 0, 350, 50, 250)
        + struct.pack(">h10s4I4s", 0, b"\0" * 10, 1, 0, 0, 0, b"NONE")  # panose, Basic Latin
        + struct.pack(">3H3h2H2I", 0x40, 0x20, 0xFFFF, ASCENT, DESCENT, 0, ASCENT, -DESCENT, 1,
                      0)  # Latin-1 page
        + struct.pack(">2h3H", ADVANCE, ASCENT, 0, 32, 0))
    return {
        b"OS/2": os2,
        b"cmap": struct.pack(">HHHHI", 0, 1, 3, 1, 12) + cmap_format4,
        b"glyf": glyph,
        b"head": struct.pack(">IIIIHHqqhhhhHHhhh", 0x00010000, 0x00010000, 0, 0x5F0F3CF5,
                             0x000B, EM, 0, 0, 0, DESCENT, ADVANCE, ASCENT, 0, 3, 2, 0, 0),
        b"hhea": struct.pack(">IhhhHhhhhhhhhhhhH", 0x00010000, ASCENT, DESCENT, 0, ADVANCE, 0, 0,
                             ADVANCE, 1, 0, 0, 0, 0, 0, 0, 0, 2),
        b"hmtx": struct.pack(">4H", ADVANCE, 0, ADVANCE, 0),
        b"loca": struct.pack(">3H", 0, 0, len(glyph) // 2),
        b"maxp": struct.pack(">IHHHHHHHHHHHHHH", 0x00010000, 2, 4, 1, 0, 0, 2, 0, 0, 0, 0, 0,
                             0, 0, 0),
        b"name": _name_table(),
        b"post": struct.pack(">IIhhIIIII", 0x00030000, 0, -100, 50, 0, 0, 0, 0, 0),
    }


def invisible_font() -> bytes:
    """The TrueType font of the text layer: one glyph, a box over the em, for every
    character, all equally wide."""
    tables = _tables()
    count = len(tables)
    power = 1 << (count.bit_length() - 1)
    header = struct.pack(">IHHHH", 0x00010000, count, power * 16, power.bit_length() - 1,
                         count * 16 - power * 16)
    offset = len(header) + 16 * count
    directory, body = b"", b""
    for tag in sorted(tables):
        data = tables[tag]
        directory += struct.pack(">4sIII", tag, _checksum(data), offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    font = bytearray(header + directory + body)
    head = font.index(tables[b"head"][:16], len(header) + len(directory))
    struct.pack_into(">I", font, head + 8, (0xB1B0AFBA - _checksum(bytes(font))) & 0xFFFFFFFF)
    return bytes(font)


def _to_unicode() -> bytes:
    """The ``ToUnicode`` map: every two-byte code is the UTF-16 unit of the same value
    (surrogates left out), in ranges that keep their first byte, at most 100 a block."""
    ranges = [f"<{hi:02X}00> <{hi:02X}FF> <{hi:02X}00>" for hi in range(256)
              if not 0xD8 <= hi <= 0xDF]
    blocks = [ranges[i:i + 100] for i in range(0, len(ranges), 100)]
    body = "\n".join(f"{len(b)} beginbfrange\n" + "\n".join(b) + "\nendbfrange" for b in blocks)
    return (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        f"{body}\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode("ascii")


def _stream(doc: pymupdf.Document, data: bytes, keys: str = "") -> int:
    """A new compressed stream object; returns its xref."""
    xref = doc.get_new_xref()
    doc.update_object(xref, f"<<{keys}>>")
    doc.update_stream(xref, data, compress=True)
    return xref


def _object(doc: pymupdf.Document, source: str) -> int:
    """A new dictionary object; returns its xref."""
    xref = doc.get_new_xref()
    doc.update_object(xref, source)
    return xref


def add_font(doc: pymupdf.Document) -> int:
    """Put the font of the text layer into ``doc`` as a Type0 font with Identity-H encoding and its
    ``ToUnicode`` map; returns the xref of the font for :func:`write_page`."""
    font = invisible_font()
    program = _stream(doc, font, f"/Length1 {len(font)}")
    descriptor = _object(doc, (
        f"<</Type/FontDescriptor/FontName/{FONT_NAME}/Flags 4"
        f"/FontBBox[0 {DESCENT} {ADVANCE} {ASCENT}]/ItalicAngle 0"
        f"/Ascent {ASCENT}/Descent {DESCENT}/CapHeight {ASCENT}/StemV 80"
        f"/FontFile2 {program} 0 R>>"))
    to_gid = _stream(doc, b"\x00\x01" * 0x10000)  # every code is drawn with the box glyph
    descendant = _object(doc, (
        f"<</Type/Font/Subtype/CIDFontType2/BaseFont/{FONT_NAME}"
        "/CIDSystemInfo<</Registry(Adobe)/Ordering(Identity)/Supplement 0>>"
        f"/FontDescriptor {descriptor} 0 R/DW {ADVANCE}/CIDToGIDMap {to_gid} 0 R>>"))
    to_unicode = _stream(doc, _to_unicode())
    return _object(doc, (
        f"<</Type/Font/Subtype/Type0/BaseFont/{FONT_NAME}/Encoding/Identity-H"
        f"/DescendantFonts[{descendant} 0 R]/ToUnicode {to_unicode} 0 R>>"))


# -- the lines of a page -----------------------------------------------------------------------
@dataclass
class _Word:
    """A word of the page text as it is written: its text and its box in page points."""

    text: str
    box: pymupdf.Rect


def _lines(page_text: PageText) -> Iterator[list[_Word]]:
    """The words of the page with a box, grouped by their line, left to right."""
    per_line: dict[int, list[_Word]] = {}
    for a, b in page_text.words():
        rects = page_text.rects(a, b)
        text = page_text.text[a:b].strip()
        if not rects or not text:
            continue
        box = pymupdf.Rect(rects[0])
        for r in rects[1:]:
            box |= r
        if box.width > 0 and box.height > 0:
            per_line.setdefault(page_text.line_of(a), []).append(_Word(text, box))
    for words in per_line.values():
        yield sorted(words, key=lambda w: w.box.x0)


def _baseline(words: list[_Word]) -> tuple[float, float, float]:
    """Slope, intercept and font size of a line: a straight line fitted through the
    centres of the word boxes (weighted by width, slope at most 3°), moved down to where
    the glyph boxes, as high as the median word, end at the bottom of the words."""
    height = median(w.box.height for w in words)
    weights = [max(w.box.width, 1e-3) for w in words]
    xs = [(w.box.x0 + w.box.x1) / 2 for w in words]
    ys = [(w.box.y0 + w.box.y1) / 2 for w in words]
    total = sum(weights)
    mx = sum(g * x for g, x in zip(weights, xs, strict=True)) / total
    my = sum(g * y for g, y in zip(weights, ys, strict=True)) / total
    spread = sum(g * (x - mx) ** 2 for g, x in zip(weights, xs, strict=True))
    slope = (sum(g * (x - mx) * (y - my) for g, x, y in zip(weights, xs, ys, strict=True))
             / spread) if spread > 1e-6 else 0.0
    slope = max(-MAX_SLOPE, min(MAX_SLOPE, slope))
    return slope, my - slope * mx + height * (0.5 + DESCENT / EM), height


def _hex(text: str) -> str:
    """The text as two-byte codes (Identity-H), one per character."""
    return "".join(f"{c if c < 0xD800 or 0xE000 <= c < 0x10000 else REPLACEMENT:04X}"
                   for c in map(ord, text))


def _number(value: float) -> str:
    """A number for the content stream: four decimals at most, no trailing zeros."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _scaling(width: float, characters: int, size: float) -> str:
    """The horizontal scaling (``Tz``, per cent) that makes ``characters`` glyphs at
    ``size`` exactly ``width`` wide."""
    return _number(100 * width / (characters * size * ADVANCE / EM))


def _line_operators(words: list[_Word], to_pdf: pymupdf.Matrix) -> list[str]:
    """The operators that write one line: per word its text matrix on the fitted
    baseline (page points turned into the page's own space by ``to_pdf``), the word
    scaled to its printed width, and a space stretched over the gap to the next word,
    so that the line runs on without a jump."""
    slope, intercept, size = _baseline(words)
    angle = math.atan(slope)
    along = pymupdf.Point(math.cos(angle), math.sin(angle))  # page points, y downwards
    up = pymupdf.Point(math.sin(angle), -math.cos(angle))
    operators = [f"/{RESOURCE} {_number(size)} Tf"]
    for i, word in enumerate(words):
        origin = pymupdf.Point(word.box.x0, slope * word.box.x0 + intercept)
        o = origin * to_pdf
        a = (origin + along) * to_pdf - o
        u = (origin + up) * to_pdf - o
        matrix = " ".join(_number(v) for v in (a.x, a.y, u.x, u.y, o.x, o.y))
        scaling = _scaling(word.box.width / math.cos(angle), len(word.text), size)
        operators.append(f"{matrix} Tm {scaling} Tz <{_hex(word.text)}> Tj")
        if i < len(words) - 1:  # boxes that touch or overlap still get a narrow space
            gap = max(words[i + 1].box.x0 - word.box.x1, 0.05 * size) / math.cos(angle)
            operators.append(f"{_scaling(gap, 1, size)} Tz <0020> Tj")
    return operators


def _reference(value: str) -> int | None:
    """The object number of an indirect reference ("12 0 R"), else None."""
    parts = value.split()
    return int(parts[0]) if len(parts) == 3 and parts[2] == "R" else None


def _inherited_resources(doc: pymupdf.Document, xref: int) -> str:
    """The resources a page inherits from its ancestors in the page tree ("<<>>" when
    none has any), as a PDF value."""
    seen: set[int] = set()
    while xref and xref not in seen:
        seen.add(xref)
        kind, value = doc.xref_get_key(xref, "Resources")
        if kind != "null":
            return value
        parent = _reference(doc.xref_get_key(xref, "Parent")[1])
        xref = parent or 0
    return "<<>>"


def _add_font_resource(doc: pymupdf.Document, page: pymupdf.Page, font: int) -> None:
    """Name the font in the page's resources: in the page's own dictionary, or in the
    resources (or font) object the page points to, which other pages may share and which
    then name an unused font; inherited resources become the page's own first."""
    kind, value = doc.xref_get_key(page.xref, "Resources")
    if kind == "null":
        doc.xref_set_key(page.xref, "Resources", _inherited_resources(doc, page.xref))
        kind, value = doc.xref_get_key(page.xref, "Resources")
    holder, prefix = page.xref, "Resources/"
    if kind == "xref":
        holder, prefix = _reference(value) or holder, ""
    kind, value = doc.xref_get_key(holder, f"{prefix}Font")
    if kind == "xref":
        holder, prefix = _reference(value) or holder, ""
    else:
        prefix += "Font/"
    doc.xref_set_key(holder, f"{prefix}{RESOURCE}", f"{font} 0 R")


def write_page(doc: pymupdf.Document, page: pymupdf.Page, page_text: PageText,
               font: int) -> int:
    """Lay the words of ``page_text`` invisibly onto ``page``, one text object per line,
    with the font :func:`add_font` put into ``doc``; returns the number of words
    written."""
    to_pdf = ~page.transformation_matrix  # page points (top left, as shown) -> PDF space
    words_per_line = list(_lines(page_text))
    written = sum(len(z) for z in words_per_line)
    if not written:
        return 0
    lines = [_line_operators(words, to_pdf) for words in words_per_line]
    page.wrap_contents()  # the page's own operators cannot leave a state behind for ours
    content = "q\n" + "".join("BT 3 Tr\n" + "\n".join(z) + "\nET\n" for z in lines) + "Q\n"
    stream = _stream(doc, content.encode("ascii"))
    _add_font_resource(doc, page, font)
    contents = " ".join(f"{x} 0 R" for x in [*page.get_contents(), stream])
    doc.xref_set_key(page.xref, "Contents", f"[{contents}]")
    return written
