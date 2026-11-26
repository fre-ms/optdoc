"""Finding the areas of a page that are not plain text: barcodes (read as well),
pictures, stamps and handwriting (:mod:`optdoc.layout` keeps them).

Each finder looks at the cleaned page as an image, together with the words read on it;
what it finds is a suggestion, shown in the window to be corrected.  The mistakes are
not equal: a picture keeps its words out of the text, so a page's text taken for a
picture would be lost, while a stamp or handwriting is still read, only marked.  So a
picture needs a clear case (filled, hardly any readable word), a stamp or handwriting
less of one.

- **Barcodes** (the extra "barcodes", zxing-cpp): every format it reads, QR and
  DataMatrix included; the region carries the format and what the code says.
- **Stamps:** a cluster of one strong ink colour (blue, violet, red), mostly lines and
  letters (little of its box filled), with at least two lines of readable text.
- **Pictures:** a cluster of ink that is mostly filled or in many tones, with hardly
  any readable word in it.
- **Handwriting:** stroke-like ink of the height of writing, in which OCR read hardly
  anything (cursive comes out as single letters and marks, with little confidence).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from optdoc.layout import Box, Region

MM = 72 / 25.4  # points per millimetre
WORK_DPI = 100  # pictures, stamps and handwriting are looked for at this resolution


@dataclass
class Word:
    """A word read on the page: its text, its box in points and how sure the reader was."""

    text: str
    box: Box
    confidence: float = 1.0


def barcodes_available() -> bool:
    """True when zxing-cpp is installed (the extra "barcodes"); it is not loaded for that."""
    return importlib.util.find_spec("zxingcpp") is not None


def find_barcodes(image: Any, scale: float) -> list[Region]:
    """Every barcode zxing-cpp reads on the page image (``scale``: pixels per point), as a
    region with its format and content; none without the extra "barcodes"."""
    if not barcodes_available():
        return []
    import zxingcpp

    from optdoc.cleanup import _grey

    grey = _grey(image)
    found = []
    for code in zxingcpp.read_barcodes(grey, try_rotate=True, try_downscale=True):
        corners = [code.position.top_left, code.position.top_right, code.position.bottom_right,
                   code.position.bottom_left]
        xs, ys = [p.x for p in corners], [p.y for p in corners]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        name = code.format.name if hasattr(code.format, "name") else str(code.format)
        if name not in TWO_DIMENSIONAL and x1 - x0 > y1 - y0:
            top, bottom = _bars(grey, int(x0), int(x1), int((y0 + y1) / 2))
            y0, y1 = min(y0, top), max(y1, bottom)  # grown only, never cut
        box = (x0 / scale, y0 / scale, x1 / scale, max(y1, y0 + 2) / scale)
        found.append(Region("barcode", box, "auto", content=code.text, format=name))
    return found


TWO_DIMENSIONAL = {"QRCode", "MicroQRCode", "RMQRCode", "DataMatrix", "Aztec", "AztecCode",
                   "AztecRune", "PDF417", "CompactPDF417", "MicroPDF417", "MaxiCode"}


def _bars(grey: Any, x0: int, x1: int, middle: int) -> tuple[int, int]:
    """How far the bars of a linear barcode reach up and down from the line zxing-cpp
    read it on (it gives that line, or a little band): row by row, as long as a row
    shows the pattern of bars of the row before it (so that bars slanted a little on a
    tilted scan are followed)."""
    import numpy as np

    row = grey[middle, x0:x1]
    if row.size == 0:
        return middle - 1, middle + 1
    threshold = (int(row.min()) + int(row.max())) / 2
    limit = 2 * (x1 - x0)

    def follow(step: int) -> int:
        y, previous = middle, row < threshold
        while 0 < y + step < grey.shape[0] - 1 and abs(y - middle) < limit:
            current = grey[y + step, x0:x1] < threshold
            if not current.any() or np.mean(current == previous) < 0.85:
                break
            y, previous = y + step, current
        return y

    return follow(-1), follow(1) + 1


# -- pictures, stamps, handwriting -------------------------------------------------------------
@dataclass
class _Blob:
    """A cluster of ink: its box in points and what it is made of."""

    box: Box
    fill: float  # share of the box that is ink
    coloured: float  # share of the ink in a strong colour
    one_hue: float  # share of the coloured ink in its most common hue
    tones: float  # share of the ink in middle greys (a photo, a shaded logo)


def _overlap(a: Box, b: Box) -> float:
    """The share of box ``a`` that lies in box ``b``."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    area = (a[2] - a[0]) * (a[3] - a[1])
    return max(0.0, w) * max(0.0, h) / area if area > 0 else 0.0


def _working(image: Any, scale: float) -> tuple[Any, Any, float]:
    """The page at WORK_DPI in colour (BGR) and HSV, and its pixels per point."""
    import cv2

    f = WORK_DPI / 72 / scale
    small = cv2.resize(image, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else image
    colour = small if small.ndim == 3 else cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    return colour, cv2.cvtColor(colour, cv2.COLOR_BGR2HSV), scale * small.shape[1] / image.shape[1]


def _without_specks(mask: Any) -> Any:
    """A mask without the specks of a noisy scan (pieces of a few pixels)."""
    import cv2
    import numpy as np

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    small = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] < 4)
    small = small[small > 0]
    out = mask.copy()
    if len(small):
        out[np.isin(labels, small)] = 0
    return out


def _ruled(ink: Any) -> Any:
    """The ruled lines of a page (long and thin: 25 mm or more, under 1.5 mm thick);
    a filled picture holds long runs of ink too, but it is thick."""
    import cv2
    import numpy as np

    px_per_mm = WORK_DPI / 25.4
    long = max(15, int(25 * px_per_mm))
    thick = max(3, int(1.5 * px_per_mm))
    lines = np.zeros_like(ink)
    for run, across in (((1, long), (thick, 1)), ((long, 1), (1, thick))):
        found = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones(run, np.uint8))
        filled = cv2.morphologyEx(found, cv2.MORPH_OPEN, np.ones(across, np.uint8))
        lines = cv2.bitwise_or(lines, cv2.bitwise_and(found, cv2.bitwise_not(filled)))
    return cv2.dilate(lines, np.ones((3, 3), np.uint8))


def _components(mask: Any, kernel: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """The boxes (x, y, w, h in pixels) of the clusters of a mask, closed by ``kernel``
    (height, width)."""
    import cv2
    import numpy as np

    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones(kernel, np.uint8))
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(closed)
    return [tuple(int(v) for v in stats[i][:4]) for i in range(1, n)]  # type: ignore[misc]


def _blob(box: tuple[int, int, int, int], ink: Any, strong: Any, hsv: Any, grey: Any,
          paper: float, f: float) -> _Blob | None:
    """What a cluster is made of; None for an empty one."""
    import numpy as np

    x, y, w, h = box
    inside = ink[y:y + h, x:x + w] > 0
    count = int(inside.sum())
    if count == 0:
        return None
    hues = hsv[y:y + h, x:x + w, 0][inside & strong[y:y + h, x:x + w]]
    one_hue = 0.0
    if len(hues):  # OpenCV's hue runs 0..179; red wraps round
        bins = np.histogram((hues.astype(int) + 8) % 180, bins=12, range=(0, 180))[0]
        one_hue = float(bins.max() / bins.sum())
    greys = grey[y:y + h, x:x + w][inside]
    tones = float(((greys > 70) & (greys < paper - 45)).mean())
    return _Blob((x / f, y / f, (x + w) / f, (y + h) / f), count / (w * h), len(hues) / count,
                 one_hue, tones)


def _masks(image: Any, scale: float) -> tuple[Any, Any, Any, Any, float, float]:
    """Ink (specks and ruled lines left out), strongly coloured ink, HSV, grey, the
    paper's grey and the working pixels per point."""
    import cv2

    colour, hsv, f = _working(image, scale)
    grey = cv2.cvtColor(colour, cv2.COLOR_BGR2GRAY)
    import numpy as np

    paper = float(np.percentile(grey, 90))
    strong = (hsv[:, :, 1] > 60) & (hsv[:, :, 2] > 70)
    ink = _without_specks(((grey < paper - 45) | strong).astype(np.uint8))
    ink[_ruled(ink) > 0] = 0
    return ink, strong, hsv, grey, paper, f


def _blobs(image: Any, scale: float, blank: Sequence[Box] = ()) -> list[_Blob]:
    """The clusters of ink on the page, ruled lines and specks left out, and the boxes
    ``blank`` (areas found already: a signature beside a stamp is a cluster of its own);
    words written apart (handwriting) stay together."""
    ink, strong, hsv, grey, paper, f = _masks(image, scale)
    for x0, y0, x1, y1 in blank:
        ink[max(0, int(y0 * f)):int(y1 * f) + 1, max(0, int(x0 * f)):int(x1 * f) + 1] = 0
    px_per_mm = WORK_DPI / 25.4
    kernel = (max(3, int(2.5 * px_per_mm)), max(5, int(5 * px_per_mm)))
    blobs = []
    for box in _components(ink, kernel):
        if box[2] < 6 * px_per_mm and box[3] < 6 * px_per_mm:
            continue
        blob = _blob(box, ink, strong, hsv, grey, paper, f)
        if blob is not None:
            blobs.append(blob)
    return blobs


def _letter_rows(mask: Any, box: tuple[int, int, int, int]) -> int:
    """The rows of letter shapes in a box of a mask: separate small pieces of the
    height of print (1.2 to 5 mm, at most 6 mm wide), at least four to a row.  Print
    falls into such pieces; cursive writing joins its letters into a few long strokes."""
    import cv2

    x, y, w, h = box
    px_per_mm = WORK_DPI / 25.4
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(mask[y:y + h, x:x + w])
    middles = sorted(float(top + height / 2) for _x, top, width, height, _a in stats[1:]
                     if 1.2 * px_per_mm <= height <= 5 * px_per_mm and width <= 6 * px_per_mm)
    rows, current, last = 0, 0, None
    for m in middles:
        if last is not None and m - last > 1.5 * px_per_mm:
            rows += current >= 4
            current = 0
        current += 1
        last = m
    return rows + (current >= 4)


def find_stamps(image: Any, scale: float, words: Sequence[Word]) -> list[Region]:
    """Stamps: clusters of strongly coloured ink in one hue, mostly lines and letters,
    with at least two lines of text (a frame alone or a coloured signature is none),
    from 15 by 9 to 140 by 100 millimetres.  The text is told by the words read in it,
    or, where the clean-up took the coloured ink away before reading, by rows of letter
    shapes."""
    import numpy as np

    _ink, strong, hsv, grey, paper, f = _masks(image, scale)
    mask = _without_specks(strong.astype(np.uint8))
    px_per_mm = WORK_DPI / 25.4
    k = max(3, int(3 * px_per_mm))
    found = []
    for box in _components(mask, (k, k)):
        blob = _blob(box, mask, strong, hsv, grey, paper, f)
        if blob is None:
            continue
        x0, y0, x1, y1 = blob.box
        w, h = (x1 - x0) / MM, (y1 - y0) / MM
        if not (15 <= w <= 140 and 9 <= h <= 100 and blob.fill < 0.35 and blob.one_hue > 0.7):
            continue
        _letters, lines = _readable(words, blob.box)
        if lines >= 2 or _letter_rows(mask, box) >= 2:
            found.append(Region("stamp", blob.box))
    return found


def _readable(words: Sequence[Word], box: Box) -> tuple[int, int]:
    """Letters and digits of the words read with confidence in a box, and the lines they
    stand on."""
    letters, lines = 0, []  # type: tuple[int, list[float]]
    for w in words:
        mx, my = (w.box[0] + w.box[2]) / 2, (w.box[1] + w.box[3]) / 2
        if box[0] <= mx <= box[2] and box[1] <= my <= box[3] and w.confidence >= 0.8:
            letters += sum(c.isalnum() for c in w.text)
            if not any(abs(my - y) < (w.box[3] - w.box[1]) * 0.6 for y in lines):
                lines.append(my)
    return letters, len(lines)


def find_marks(image: Any, scale: float, words: Sequence[Word] | None,
               taken: Sequence[Box] = ()) -> list[Region]:
    """Stamps, pictures and handwriting on the page image (``scale``: pixels per point),
    outside the boxes ``taken`` (tables, barcodes).  ``words`` are the words read on the
    page; without them (no reader) only pictures are looked for, since a line of print
    would look like handwriting and a stamp is told by its text."""
    stamps = find_stamps(image, scale, words) if words else []
    found: list[Region] = list(stamps)
    taken = [*taken, *(s.box for s in stamps)]
    for blob in _blobs(image, scale, taken):
        x0, y0, x1, y1 = blob.box
        w, h = (x1 - x0) / MM, (y1 - y0) / MM  # millimetres
        if any(_overlap(blob.box, t) > 0.3 for t in taken):
            continue
        letters, _lines = _readable(words or [], blob.box)
        density = letters / max(x1 - x0, 1.0)  # print at 10 pt: about 0.17 per point
        # many tones make a photo, not lines in one colour (whose edges are grey too)
        shaded = blob.fill >= 0.15 and blob.tones >= 0.5 and (blob.coloured < 0.3
                                                              or blob.one_hue < 0.6)
        if w >= 12 and h >= 12 and (blob.fill >= 0.35 or shaded) and density < 0.02:
            found.append(Region("image", blob.box))
        elif words and blob.fill < 0.3 and w >= 15 and 3 <= h <= 30 and density < 0.05:
            found.append(Region("handwriting", blob.box))
    return found
