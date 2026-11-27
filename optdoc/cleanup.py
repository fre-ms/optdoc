"""The preparation of a page: upright, unwarped, straightened, evenly lit, in its own
colours.

Scans arrive tilted and with dark borders, photos are taken at an angle under uneven
light.  Every step here is optional, has an automatic suggestion and is meant to be
checked by eye.  The steps work on a rendered page (an image); the prepared image
replaces the page.  The page keeps its colours (a stamp, a blue signature, a highlighted
line stay); a page without colour is stored in grey, which keeps the file small.  What
only helps OCR read a page (upscaling, a letter mode, taking colour or ruled lines away,
black and white) is ocrdoc's, on its own copy of the page.  Needs OpenCV and NumPy (the
extra "cleanup"); without them only masks are available.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from optdoc.errors import OptdocError

Corner = tuple[float, float]
Rectangle = tuple[float, float, float, float]


def available() -> bool:
    """True when OpenCV and NumPy are installed (the extra "cleanup"); they are not
    loaded for that."""
    return all(importlib.util.find_spec(name) is not None for name in ("cv2", "numpy"))


@dataclass
class CleanupPlan:
    """What to do with one page.  Angles in degrees; corners in points of the source
    page (after ``rotation``), masks as ``(x0, y0, x1, y1)`` in points of the result
    page (see :func:`cleaned_image`)."""

    rotation: int = 0  # 0, 90, 180, 270 clockwise, applied first
    straighten: bool = False  # rotate by -angle
    angle: float = 0.0  # estimated tilt, positive = text runs downhill to the right
    unwarp: bool = False  # perspective correction with ``corners``
    corners: list[Corner] | None = None  # four corners of the page in the (rotated) image
    borders: bool = False  # dark scanner borders -> white
    denoise: bool = False  # median plus non-local means against specks and grain
    denoise_strength: int = 2  # 1 (gentle) to 5 (strong)
    contrast: bool = False  # CLAHE on faint copies
    contrast_strength: int = 2  # 1 to 5
    sharpen: bool = False  # unsharp mask
    sharpen_strength: int = 2  # 1 to 5
    background: bool = False  # even out illumination per colour channel, white paper
    masks: list[Rectangle] = field(default_factory=list)  # regions to wipe, result page points
    mask_colour: str = "white"  # "white" erases (clean-up step), "black" redacts
    grey: bool = False  # the page has no colour: stored in grey (smaller), when it is redrawn

    @property
    def active(self) -> bool:
        """True when at least one step would run, so that the page would change.  Grey is
        no step: it says how a page that is redrawn anyway is stored."""
        return any(getattr(self, switch) for switch, _ in _STEPS)

    def as_dict(self) -> dict[str, Any]:
        """The plan for the report: every switch and strength, the masks only counted."""
        return {"rotation": self.rotation, "straighten": self.straighten,
                "angle": round(self.angle, 2), "unwarp": self.unwarp,
                "borders": self.borders,
                "denoise": self.denoise, "denoise_strength": self.denoise_strength,
                "contrast": self.contrast, "contrast_strength": self.contrast_strength,
                "sharpen": self.sharpen, "sharpen_strength": self.sharpen_strength,
                "background": self.background,
                "masks": len(self.masks), "mask_colour": self.mask_colour, "grey": self.grey}

    def full_dict(self) -> dict[str, Any]:
        """Every field, masks and corners included (the working state)."""
        d = {k: v for k, v in self.__dict__.items() if k not in ("corners", "masks")}
        d["corners"] = [list(e) for e in self.corners] if self.corners is not None else None
        d["masks"] = [list(m) for m in self.masks]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CleanupPlan:
        """The plan from a :meth:`full_dict` dictionary; keys that are no field are ignored.
        A value of the wrong kind or out of its range raises an
        :class:`~optdoc.errors.OptdocError` of kind "bad-config"."""
        if not isinstance(d, dict):
            raise OptdocError("bad-config", reason="json")
        kept = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if not all(_fits(k, v) for k, v in kept.items()):
            raise OptdocError("bad-config", reason="field")
        if kept.get("corners") is not None:
            kept["corners"] = [tuple(e) for e in kept["corners"]]
        kept["masks"] = [tuple(m) for m in kept.get("masks", [])]
        return cls(**kept)


def _numbers(value: Any, count: int) -> bool:
    """True for a list (or tuple) of ``count`` numbers."""
    return (isinstance(value, list | tuple) and len(value) == count
            and all(isinstance(v, int | float) and not isinstance(v, bool) for v in value))


_RANGES: dict[str, tuple[Any, ...]] = {
    "rotation": (0, 90, 180, 270), "mask_colour": ("white", "black"),
    **{k: (1, 2, 3, 4, 5) for k in ("denoise_strength", "contrast_strength", "sharpen_strength")},
}


def _fits(name: str, value: Any) -> bool:
    """True when ``value`` is of the kind of the plan's field ``name`` and in its range."""
    if name == "corners":
        return value is None or (isinstance(value, list | tuple) and len(value) == 4
                                 and all(_numbers(c, 2) for c in value))
    if name == "masks":
        return isinstance(value, list | tuple) and all(_numbers(m, 4) for m in value)
    default = CleanupPlan.__dataclass_fields__[name].default
    if isinstance(default, bool):
        fits = isinstance(value, bool)
    elif isinstance(default, int | float):
        fits = isinstance(value, int | float) and not isinstance(value, bool)
    else:
        fits = isinstance(value, type(default))
    return fits and value in _RANGES.get(name, (value,))


# -- rendering -----------------------------------------------------------------------------------


def render(page: pymupdf.Page, dpi: int = 300, max_pixel: int = 4000) -> tuple[Any, float]:
    """The page as a BGR NumPy image and the pixels-per-point scale."""
    import numpy as np

    scale = dpi / 72.0
    longest = max(page.rect.width, page.rect.height) * scale
    if longest > max_pixel:
        scale *= max_pixel / longest
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False,
                          colorspace=pymupdf.csRGB)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return image[:, :, ::-1].copy(), scale


def _grey(image: Any) -> Any:
    import cv2

    return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _shrunk(grey: Any, longest: int = 1200) -> tuple[Any, float]:
    import cv2

    h, w = grey.shape[:2]
    f = min(1.0, longest / max(h, w))
    if f < 1.0:
        return cv2.resize(grey, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA), f
    return grey, 1.0


# -- analysis ------------------------------------------------------------------------------------


def estimate_tilt(image: Any, maximum: float = 10.0) -> float:
    """Tilt of the text lines in degrees (positive: the lines run downhill to the
    right).  Projection profile: the angle at which the row sums of the binarised,
    rotated image vary most is the one at which the lines are horizontal."""
    import cv2
    import numpy as np

    grey, _ = _shrunk(_grey(image), 800)
    _, bw = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    bw = _text_only(bw)
    h, w = bw.shape
    middle = (w / 2, h / 2)

    def quality(angle: float) -> float:
        m = cv2.getRotationMatrix2D(middle, angle, 1.0)
        rotated = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        profile = rotated.sum(axis=1, dtype=np.float64)
        return float(np.var(profile))

    best, best_value = 0.0, -1.0
    for a in np.arange(-maximum, maximum + 0.01, 0.5):  # coarse, then fine around the best
        g = quality(float(a))
        if g > best_value:
            best, best_value = float(a), g
    for a in np.arange(best - 0.5, best + 0.51, 0.1):
        g = quality(float(a))
        if g > best_value:
            best, best_value = float(a), g
    # ``best`` is the counter-clockwise correction; the tilt itself has the same sign
    # (content turned clockwise by 2° needs 2° counter-clockwise)
    return round(best, 2) if abs(best) >= 0.05 else 0.0


def _text_only(bw: Any) -> Any:
    """Drop what is not text from a binary image: borders, bars, stamps, photos (large
    or very elongated connected components), so that the line profile is not fooled."""
    import cv2
    import numpy as np

    h, w = bw.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if n <= 1:
        return bw
    widths = stats[:, cv2.CC_STAT_WIDTH]
    heights = stats[:, cv2.CC_STAT_HEIGHT]
    surfaces = stats[:, cv2.CC_STAT_AREA]
    bad = (widths > 0.25 * w) | (heights > 0.12 * h) | (surfaces > 0.01 * w * h)
    bad[0] = False  # the background label
    if not bad.any():
        return bw
    out = bw.copy()
    out[np.isin(labels, np.flatnonzero(bad))] = 0
    return out if out.any() else bw


def _content_box(grey: Any) -> tuple[int, int, int, int]:
    """``(x0, y0, x1, y1)`` of the picture on a rendered page: without the even white
    bars that placing a photo on paper adds above and below or left and right.  A
    photographed row or column is never one even white; a bar is."""
    h, w = grey.shape

    def span(bars: Any) -> tuple[int, int]:
        n = len(bars)
        a, b = 0, n
        while a < n and bars[a]:
            a += 1
        while b > a and bars[b - 1]:
            b -= 1
        return a, b

    y0, y1 = span(grey.min(axis=1) >= 250)
    x0, x1 = span(grey.min(axis=0) >= 250)
    if (x1 - x0) * (y1 - y0) < 0.3 * w * h:  # blank or nearly so: the whole page
        return 0, 0, w, h
    return int(x0), int(y0), int(x1), int(y1)


def _quad_from_edges(grey: Any) -> Any:
    """The sheet as the largest four-cornered outline among the edges, all of it inside
    the picture; None when there is none.  Precise where it works: a sheet whole in the
    picture, on something that sets it off."""
    import cv2
    import numpy as np

    h, w = grey.shape
    blurred = cv2.GaussianBlur(grey, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: Any = None
    best_area = 0.0
    for k in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        area = cv2.contourArea(k)
        if area < 0.2 * w * h:
            break
        extent = cv2.arcLength(k, True)
        approx = cv2.approxPolyDP(k, 0.02 * extent, True)
        if len(approx) == 4 and cv2.isContourConvex(approx) and area > best_area:
            best, best_area = approx.reshape(4, 2).astype(np.float64), area
    if best is None or best_area > 0.97 * w * h:
        return None  # nothing, or the whole picture: no correction needed
    return best


def _paper_region(grey: Any) -> Any:
    """The sheet as a region: the print closed over, bright paper set apart from what it
    lies on (Otsu), the largest piece; None when no piece covers a fifth of the picture."""
    import cv2
    import numpy as np

    h, w = grey.shape
    k = max(3, int(0.015 * max(h, w)) | 1)
    closed = cv2.morphologyEx(grey, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    blurred = cv2.GaussianBlur(closed, (0, 0), 2)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return None
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[best, cv2.CC_STAT_AREA] < 0.2 * w * h:
        return None
    return (labels == best).astype(np.uint8) * 255


def _crossing(a: Any, b: Any) -> Any:
    """Where two lines (point, direction) meet; None for (nearly) parallel ones."""
    import numpy as np

    (p, d), (q, e) = a, b
    det = d[0] * -e[1] - d[1] * -e[0]
    if abs(det) < 0.2:  # less than about 12 degrees apart
        return None
    t = ((q[0] - p[0]) * -e[1] - (q[1] - p[1]) * -e[0]) / det
    return np.array([p[0] + t * d[0], p[1] + t * d[1]])


def _homogeneous(line: Any) -> Any:
    """A line (point, direction) as homogeneous coefficients."""
    import numpy as np

    (x, y), (dx, dy) = line
    return np.cross([x, y, 1.0], [x + dx, y + dy, 1.0])


def _missing_edge(near: Any, middle: Any, far: Any, outline: Any, size: tuple[int, int]) -> Any:
    """The edge of the sheet opposite ``middle`` when the photo cut it off: ``near`` and
    ``far`` are the edges on either side of the gap (they converge towards ``middle`` or
    away from it), ``middle`` the edge seen opposite.  In space the missing edge runs
    parallel to ``middle``; its vanishing point lies on ``middle``'s line where the
    direction is square to that of the side edges, for a phone's focal length
    (PHONE_FOCAL).  Of the lines through that point the one is taken that keeps all of
    the visible paper (``outline``) on the sheet: nothing seen is cut off, and what lies
    beyond the photo becomes white."""
    import numpy as np

    w, h = size
    focal = PHONE_FOCAL * float(np.hypot(w, h))
    k = np.array([[focal, 0, w / 2], [0, focal, h / 2], [0, 0, 1.0]])
    k_inv = np.linalg.inv(k)
    omega = k_inv.T @ k_inv  # the image of the absolute conic
    side_vanishing = np.cross(_homogeneous(near), _homogeneous(far))
    other = np.cross(_homogeneous(middle), omega @ side_vanishing)
    if abs(other[2]) > 1e-12:
        other = other / other[2]
    near_line, middle_line = _homogeneous(near), _homogeneous(middle)
    start = np.cross(near_line, middle_line)
    if abs(start[2]) < 1e-12:
        return None
    start = start / start[2]
    direction = np.asarray(near[1], dtype=np.float64)
    # where the line from the vanishing point through each visible point meets the near
    # edge, as a distance from the corner with ``middle``; the farthest keeps all
    best, best_t = None, 0.0
    for x, y in outline[:: max(1, len(outline) // 400)]:
        line = np.cross(other, [x, y, 1.0])
        meet = np.cross(line, near_line)
        if abs(meet[2]) < 1e-12:
            continue
        meet = meet[:2] / meet[2]
        t = float(np.dot(meet - start[:2], direction))
        if best is None or abs(t) > abs(best_t):
            best, best_t = line, t
    if best is None:
        return None
    # back to (point, direction): two points of the homogeneous line
    a, b, c = best
    if abs(b) > abs(a):
        p0 = np.array([0.0, -c / b])
    else:
        p0 = np.array([-c / a, 0.0])
    d = np.array([b, -a]) / np.hypot(a, b)
    return p0, d


def _sides(outline: Any, w: int, h: int) -> list[tuple[str, Any]]:
    """The sheet's outline (``outline``, in order) as its sides round the sheet: runs
    along the edge of the picture ("frame", None) and the straight edges between them
    ("sheet", (point, direction)), each fitted to the outline points along its middle."""
    import cv2
    import numpy as np

    margin = max(3.0, 0.004 * max(w, h))
    shortest = 0.1 * min(w, h)
    border = (outline[:, 0] <= margin) | (outline[:, 0] >= w - 1 - margin) \
        | (outline[:, 1] <= margin) | (outline[:, 1] >= h - 1 - margin)
    n = len(outline)
    if border.all():
        return [("frame", None)]
    # start the round where a free run begins, so that no run is split at the seam
    start = next((i for i in range(n) if not border[i] and border[i - 1]), 0)
    order = np.roll(np.arange(n), -start)
    runs: list[tuple[bool, list[int]]] = []
    for i in order:
        if runs and runs[-1][0] == bool(border[i]):
            runs[-1][1].append(int(i))
        else:
            runs.append((bool(border[i]), [int(i)]))
    sides: list[tuple[str, Any]] = []
    for on_border, indices in runs:
        if on_border:
            if len(indices) > shortest / 4:
                sides.append(("frame", None))
            continue
        run = outline[indices]
        vertices = cv2.approxPolyDP(run.astype(np.float32).reshape(-1, 1, 2),
                                    0.015 * max(w, h), False).reshape(-1, 2)
        for p, q in zip(vertices[:-1], vertices[1:], strict=True):
            p, q = p.astype(np.float64), q.astype(np.float64)
            length = float(np.linalg.norm(q - p))
            if length < shortest:
                continue  # a bit of a corner, not an edge
            direction = (q - p) / length
            offsets = run - p
            along = offsets @ direction
            across = np.abs(offsets[:, 0] * direction[1] - offsets[:, 1] * direction[0])
            near = (along > 0.1 * length) & (along < 0.9 * length) & (across < 2 * margin)
            if near.sum() < 10:
                continue
            vx, vy, x0, y0 = cv2.fitLine(run[near].astype(np.float32), cv2.DIST_HUBER,
                                         0, 0.01, 0.01).ravel()
            line = (np.array([x0, y0], np.float64), np.array([vx, vy], np.float64))
            if sides and sides[-1][0] == "sheet" \
                    and abs(float(np.dot(sides[-1][1][1], line[1]))) > 0.995:
                continue  # the same edge, broken by the approximation
            sides.append(("sheet", line))
    if len(sides) > 1 and sides[0][0] == sides[-1][0] == "sheet" \
            and abs(float(np.dot(sides[0][1][1], sides[-1][1][1]))) > 0.995:
        sides.pop()  # the round closed on the same edge
    return sides


def _quad_from_region(grey: Any) -> Any:
    """The sheet's four corners from straight lines fitted to its visible edges; a
    corner may lie outside the picture (a sheet cut off by it).  Where a whole edge of
    the sheet is outside, it is reconstructed (:func:`_missing_edge`).  None when fewer
    than three edges of the sheet are seen, or they make no plausible sheet."""
    import cv2
    import numpy as np

    region = _paper_region(grey)
    if region is None:
        return None
    h, w = grey.shape
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    outline = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)
    sides = _sides(outline, w, h)
    edges = [line for kind, line in sides if kind == "sheet"]
    if len(edges) == 3:
        # the missing edge belongs in a gap where the frame cut the sheet off, between
        # the two edges most nearly parallel (the sheet's opposite sides)
        gaps = [k for k in range(3) if _frame_in_gap([kind for kind, _ in sides], k)]
        if not gaps:
            return None
        k = max(gaps, key=lambda g: abs(float(np.dot(edges[g][1], edges[(g + 1) % 3][1]))))
        near, far, middle = edges[k], edges[(k + 1) % 3], edges[(k + 2) % 3]
        missing = _missing_edge(near, middle, far, outline, (w, h))
        if missing is None:
            return None
        edges.insert(k + 1, missing)
    if len(edges) != 4:
        return None
    corners = [_crossing(edges[k - 1], edges[k]) for k in range(4)]
    if any(c is None for c in corners):
        return None
    quad = np.array(corners)
    inside = (quad[:, 0] > -0.6 * w) & (quad[:, 0] < 1.6 * w) & (quad[:, 1] > -0.6 * h) \
        & (quad[:, 1] < 1.6 * h)
    if not inside.all() or not cv2.isContourConvex(quad.astype(np.float32)):
        return None
    if cv2.contourArea(quad.astype(np.float32)) < 0.2 * w * h:
        return None
    return quad


def _frame_in_gap(kinds: list[str], k: int) -> bool:
    """True when the frame of the picture lies between the ``k``-th sheet edge and the
    next one (round the sheet)."""
    sheet = [i for i, kind in enumerate(kinds) if kind == "sheet"]
    i, stop = (sheet[k] + 1) % len(kinds), sheet[(k + 1) % len(sheet)]
    while i != stop:
        if kinds[i] == "frame":
            return True
        i = (i + 1) % len(kinds)
    return False


def _ordered(quad: Any) -> Any:
    """Four points ordered top-left, top-right, bottom-right, bottom-left."""
    import numpy as np

    subtotal = quad.sum(axis=1)
    diff = np.diff(quad, axis=1).ravel()
    return np.array([quad[np.argmin(subtotal)], quad[np.argmin(diff)],
                     quad[np.argmax(subtotal)], quad[np.argmax(diff)]])


def _sheet(image: Any) -> tuple[Any, Any, float, tuple[int, int, int, int]]:
    """The sheet's corners in the shrunk picture (or None), the shrunk picture, its
    scale against the image, and the picture's box on the image."""
    grey_full = _grey(image)
    box = _content_box(grey_full)
    x0, y0, x1, y1 = box
    grey, f = _shrunk(grey_full[y0:y1, x0:x1], 1000)
    quad = _quad_from_edges(grey)
    if quad is not None and not _on_a_desk(grey, quad):
        quad = None  # a frame or a ruled table with paper around it, not the sheet
    if quad is None:
        quad = _quad_from_region(grey)
    return (None if quad is None else _ordered(quad)), grey, f, box


def _in_points(quad: Any, f: float, box: tuple[int, int, int, int], scale: float) -> list[Corner]:
    return [(float((x / f + box[0]) / scale), float((y / f + box[1]) / scale)) for x, y in quad]


def find_corners(image: Any, scale: float = 1.0) -> list[Corner] | None:
    """The four corners of a sheet photographed against a background, ordered
    top-left, top-right, bottom-right, bottom-left, in points (pixels / ``scale``);
    a corner may lie outside the picture when the photo cuts the sheet off.  None when
    no convincing sheet is found (a scan that fills the image).

    Two searches: the largest four-cornered outline among the edges (precise, needs the
    whole sheet in the picture), else straight lines fitted to the visible edges of the
    paper as a region (a corner cut off, a desk little darker than paper).  The white
    bars that placing a photo on paper adds are no part of the picture."""
    quad, _grey_shrunk, f, box = _sheet(image)
    return None if quad is None else _in_points(quad, f, box, scale)


def _on_a_desk(grey: Any, quad: Any) -> bool:
    """True when what lies just outside the quadrilateral (pixel corners of ``grey``,
    outside the picture or not) is clearly darker than the paper just inside its edge:
    a desk, a table top, a hand.  Just outside a frame or a ruled table lies paper, on a
    scan as on a photographed sheet, as bright as inside; unwarping to such a frame
    would cut the page or change its shape.  Only a narrow ring counts: further out, a
    desk around the sheet would make a table on it look like a sheet on a desk."""
    import cv2
    import numpy as np

    h, w = grey.shape
    inside = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(inside, np.round(quad).astype(np.int32), 255)
    edge = max(3, int(0.02 * min(h, w)))
    gap = max(1, edge // 3)  # the edge itself is blurred: left out on both sides

    def square(n: int) -> Any:
        return np.ones((2 * n + 1, 2 * n + 1), np.uint8)

    core = cv2.erode(inside, square(gap))
    band = cv2.subtract(core, cv2.erode(core, square(edge)))  # paper just inside the edge
    near = cv2.dilate(inside, square(gap))
    ring = cv2.subtract(cv2.dilate(near, square(edge)), near)  # what lies just outside
    if np.count_nonzero(ring) < 0.002 * h * w or not band.any():
        return False
    return float(np.median(grey[ring > 0])) < float(np.median(grey[band > 0])) - DESK_DARKER


DESK_DARKER = 15  # grey levels a desk is darker than the paper at least (measured on
# invented photos: a light grey table 34 to 37 below the paper, dark and wooden desks 147
# to 169; just outside the frame of a ruled table, on a scan, a digital page or a
# photographed sheet, the paper is brighter than inside, by 16 to 31)


def sheet_in_photo(image: Any, scale: float = 1.0) -> list[Corner] | None:
    """The corners of the sheet when ``image`` shows one lying on something darker than
    paper, as :func:`find_corners` gives them; None for a page that fills the image, and
    None when the quadrilateral has paper around it (a frame or a ruled table on a scan,
    which the edge search takes for a sheet).  This is what tells a photographed page
    from a scanned one, also inside a PDF.  A sheet on a desk as white as paper counts
    as a scan: it is not unwarped, which costs less than a page cut to a frame."""
    quad, grey, f, box = _sheet(image)
    if quad is None or not _on_a_desk(grey, quad):
        return None
    return _in_points(quad, f, box, scale)


def dark_borders(image: Any, width: float = 0.04, limit: int = 90) -> bool:
    """A dark frame around the page (scanner lid, photographed table edge), also when
    it runs at a slant: enough of the edge strip is dark."""
    import numpy as np

    grey, _ = _shrunk(_grey(image), 600)
    h, w = grey.shape
    r = max(2, int(min(h, w) * width))
    strip = [grey[:r, :], grey[-r:, :], grey[:, :r], grey[:, -r:]]
    return any(float(np.mean(s)) < limit or float(np.mean(s < 60)) > 0.3 for s in strip)


def colour_share(image: Any) -> float:
    """Share of clearly coloured pixels (stamps, highlighter, coloured print)."""
    import cv2
    import numpy as np

    if image.ndim != 3:
        return 0.0
    small, _ = _shrunk(image, 600)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    coloured = (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 60)
    return float(np.mean(coloured))


def noise_share(image: Any) -> float:
    """Share of tiny isolated dark specks among all dark components (grain, dust)."""
    import cv2

    grey, _ = _shrunk(_grey(image), 1000)
    _, bw = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if n <= 1:
        return 0.0
    surfaces = stats[1:, cv2.CC_STAT_AREA]
    return float((surfaces <= 2).sum() / len(surfaces))


def uneven_background(image: Any) -> bool:
    """True when the paper is not evenly white (photo, shadow, grey scan)."""
    import cv2
    import numpy as np

    grey, _ = _shrunk(_grey(image), 600)
    background = cv2.medianBlur(grey, 51)
    return bool(np.std(background) > 12 or np.median(background) < 215)


STRAIGHTEN_FROM = 0.3  # degrees of tilt the suggestion straightens (see suggest)
COLOUR_FROM = 0.003  # share of clearly coloured pixels from which a page keeps its colours


def suggest(image: Any, photo: bool | None = None, scale: float = 1.0) -> CleanupPlan:
    """Automatic suggestion for one page: straighten a visible tilt, unwarp a
    photographed sheet, even out an uneven background, keep the colours where the page
    has any (grey otherwise).  ``photo`` True takes the page for a photo (the sheet is
    looked for and unwarped), False for a scan, None tells by the page itself
    (:func:`sheet_in_photo`).  ``scale`` is pixels per point of ``image``."""
    a = CleanupPlan()
    if photo is None:
        corners = sheet_in_photo(image, scale)
    else:
        corners = find_corners(image, scale) if photo else None
    if corners is not None:
        a.corners, a.unwarp = corners, True
    basis = apply_plan(image, CleanupPlan(unwarp=a.unwarp, corners=a.corners), scale) \
        if a.unwarp else image
    a.angle = estimate_tilt(basis)
    # tables need straight rows and columns: on invented laboratory reports scanned at a
    # tilt of 0.35 degrees, 36 of 108 rows were cut right, at 0.5 to 1 degree 0 to 36;
    # straightened, 101 to 108, while the numbers read stayed within a few of 306 either
    # way (better at 1 degree, a little worse at 0.5); below 0.3 degrees all is well
    a.straighten = abs(a.angle) >= STRAIGHTEN_FROM
    a.background = bool(photo) or a.unwarp or uneven_background(basis)
    a.borders = dark_borders(basis)
    # where optdoc once took coloured ink away (more than 0.3 % of the page in colour), it
    # now keeps the colours; a page with less is stored in grey
    a.grey = colour_share(basis) <= COLOUR_FROM
    a.denoise = noise_share(basis) > 0.35
    return a


# The words of the description, in English and German (PseudonyMed writes its reports in
# German); placeholders are fields of the plan or the values the phrase functions add.
_WORDS: dict[str, dict[str, str]] = {
    "en": {
        "rotation": "rotated by {rotation}°", "unwarp": "unwarped",
        "straighten": "straightened ({angle:+.1f}°)", "borders": "borders cleaned",
        "denoise": "denoised", "contrast": "contrast raised", "sharpen": "sharpened",
        "background": "background evened", "grey": "in grey",
        "masks_white": "{n} region(s) erased", "masks_black": "{n} region(s) redacted",
        "unchanged": "unchanged", "decimal": ".",
    },
    "de": {
        "rotation": "um {rotation}° gedreht", "unwarp": "entzerrt",
        "straighten": "begradigt ({angle:+.1f}°)", "borders": "Ränder gesäubert",
        "denoise": "entrauscht", "contrast": "Kontrast angehoben", "sharpen": "geschärft",
        "background": "Hintergrund geglättet", "grey": "in Graustufen",
        "masks_white": "{n} Bereich(e) gelöscht", "masks_black": "{n} Bereich(e) geschwärzt",
        "unchanged": "unverändert", "decimal": ",",
    },
}


def _phrase_unwarped(a: CleanupPlan, w: dict[str, str]) -> str | None:
    """Unwarping counts only with corners to unwarp by."""
    return w["unwarp"] if a.corners else None


def _phrase_straightened(a: CleanupPlan, w: dict[str, str]) -> str | None:
    """The tilt with its sign and the language's decimal sign; None below the 0.05° that is
    applied."""
    if abs(a.angle) < 0.05:
        return None
    return w["straighten"].format(angle=a.angle).replace(".", w["decimal"])


def _phrase_masks(a: CleanupPlan, w: dict[str, str]) -> str:
    """The number of regions and whether they are erased or redacted."""
    key = "masks_white" if a.mask_colour == "white" else "masks_black"
    return w[key].format(n=len(a.masks))


Phrase = Callable[[CleanupPlan, dict[str, str]], str | None] | None

# one row per step, in the order the description lists them: the field that switches the
# step on, and its phrase function (None: the step's word, with the plan's fields filled in)
_PHRASES: tuple[tuple[str, Phrase], ...] = (
    ("rotation", None),
    ("unwarp", _phrase_unwarped),
    ("straighten", _phrase_straightened),
    ("borders", None),
    ("denoise", None),
    ("contrast", None),
    ("sharpen", None),
    ("background", None),
    ("masks", _phrase_masks),
)


def _phrase(a: CleanupPlan, switch: str, phrase: Phrase, w: dict[str, str]) -> str | None:
    """The wording of one row for ``a``: None while its switch is off, else the step's word
    with the plan's values filled in, or what the function makes of the plan."""
    if not getattr(a, switch):
        return None
    return phrase(a, w) if phrase is not None else w[switch].format(**vars(a))


def describe(a: CleanupPlan, language: str = "en") -> str:
    """What a page clean-up does, for reports and the interface, in English (``"en"``) or
    German (``"de"``)."""
    w = _WORDS.get(language, _WORDS["en"])
    parts = [t for t in (_phrase(a, switch, phrase, w) for switch, phrase in _PHRASES) if t]
    if parts and a.grey:
        parts.append(w["grey"])
    return ", ".join(parts) if parts else w["unchanged"]


# -- application ---------------------------------------------------------------------------------


# width / height of the paper sizes a sheet is snapped to when its measured proportions
# come within SNAP of one (portrait; landscape is the inverse)
PAPER_RATIOS = (2 ** -0.5, 8.5 / 11, 8.5 / 14)
SNAP = 0.03


def _side_aspect(q: Any) -> float:
    """Width / height from the longer of each pair of opposite sides: right for a sheet
    seen head-on, too wide or too narrow the more it is seen at a slant."""
    import numpy as np

    width = max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))
    height = max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))
    return float(width / height)


# a phone's main camera: 26 mm in 35 mm terms, over the 43.27 mm diagonal of 35 mm film,
# as a share of the picture's diagonal
PHONE_FOCAL = 26 / 43.27


def sheet_aspect(q: Any, centre: tuple[float, float]) -> float:
    """The true width / height of a rectangle seen at a slant, from its four corners
    (pixels, top-left, top-right, bottom-right, bottom-left) and the picture's centre,
    after Zhang and He ("Whiteboard scanning and image enhancement", 2007): with the
    camera's focal length, one view of a rectangle gives its proportions.  The focal
    length comes from the corners themselves where both pairs of edges converge enough
    to tell it; else a phone's (PHONE_FOCAL).  Within SNAP of a paper size, that size.

    Measured on simulated photos by phones of 24 to 28 mm, corners 3 to 8 pixels off,
    before snapping: median under 1 %, at most 5 % (from the sides alone, as before: up
    to 43 %).  With a twofold tele lens, where the corners do not tell the focal length,
    up to 15 %."""
    import numpy as np

    q = np.asarray(q, dtype=np.float64)
    m1, m2, m3, m4 = (np.array([x - centre[0], y - centre[1], 1.0])
                      for x, y in (q[3], q[2], q[0], q[1]))
    diagonal = float(np.hypot(*(2 * np.asarray(centre))))
    focal = PHONE_FOCAL * diagonal
    with np.errstate(divide="ignore", invalid="ignore"):
        k2 = np.dot(np.cross(m1, m4), m3) / np.dot(np.cross(m2, m4), m3)
        k3 = np.dot(np.cross(m1, m4), m2) / np.dot(np.cross(m3, m4), m2)
        n2, n3 = k2 * m2 - m1, k3 * m3 - m1
        f2 = -(n2[0] * n3[0] + n2[1] * n3[1]) / (n2[2] * n3[2])
        # how far each pair of edges converges: small for edges that stay parallel,
        # where the corners leave the focal length open
        converging = min(abs(n2[2]) / np.hypot(n2[0], n2[1]),
                         abs(n3[2]) / np.hypot(n3[0], n3[1])) * diagonal
        if np.isfinite(f2) and converging > 0.25 \
                and (0.25 * diagonal) ** 2 < f2 < (3 * diagonal) ** 2:
            focal = float(np.sqrt(f2))
        ratio2 = (n2[0] ** 2 + n2[1] ** 2 + focal ** 2 * n2[2] ** 2) \
            / (n3[0] ** 2 + n3[1] ** 2 + focal ** 2 * n3[2] ** 2)
    aspect = float(np.sqrt(ratio2)) if np.isfinite(ratio2) and ratio2 > 0 else _side_aspect(q)
    for paper in PAPER_RATIOS:
        for ratio in (paper, 1 / paper):
            if abs(aspect / ratio - 1) < SNAP:
                return ratio
    return aspect


def _unwarp(image: Any, corners: list[Corner], scale: float) -> Any:
    """The sheet within ``corners`` (points; ``scale`` pixels per point) as seen from
    straight above, in its true proportions (:func:`sheet_aspect`); what lies outside
    the picture (a corner cut off) is white."""
    import cv2
    import numpy as np

    source = np.array(corners, dtype=np.float64) * scale
    x0, y0, x1, y1 = _content_box(_grey(image))
    aspect = sheet_aspect(source, ((x0 + x1) / 2, (y0 + y1) / 2))
    height = int(max(np.linalg.norm(source[3] - source[0]), np.linalg.norm(source[2] - source[1])))
    width = int(round(height * aspect))
    if width < 10 or height < 10:
        return image
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                    dtype=np.float32)
    m = cv2.getPerspectiveTransform(source.astype(np.float32), target)
    white = (255,) * (1 if image.ndim == 2 else image.shape[2])
    return cv2.warpPerspective(image, m, (width, height), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=white)


def _rotate(image: Any, angle: float) -> Any:
    """Rotate by ``angle`` degrees counter-clockwise around the centre, canvas enlarged
    so that nothing is cut off, white border."""
    import cv2

    h, w = image.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    white = (255, 255, 255) if image.ndim == 3 else 255
    return cv2.warpAffine(image, m, (nw, nh), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=white)


def _clean_borders(image: Any, limit: int = 90, maximum: float = 0.15) -> Any:
    """Paint dark strips at the four edges white, as far as a row or column stays dark
    (at most 15 % of the side)."""
    import numpy as np

    grey = _grey(image)
    h, w = grey.shape
    out = image.copy()
    white = (255, 255, 255) if out.ndim == 3 else 255

    def depth(rows: Any, n: int) -> int:
        t = 0
        for r in rows:
            if float(np.mean(r)) < limit and t < n:
                t += 1
            else:
                break
        return t

    top = depth((grey[i, :] for i in range(h)), int(h * maximum))
    bottom = depth((grey[h - 1 - i, :] for i in range(h)), int(h * maximum))
    left = depth((grey[:, i] for i in range(w)), int(w * maximum))
    right = depth((grey[:, w - 1 - i] for i in range(w)), int(w * maximum))
    if top:
        out[:top + 2, :] = white
    if bottom:
        out[h - bottom - 2:, :] = white
    if left:
        out[:, :left + 2] = white
    if right:
        out[:, w - right - 2:] = white
    return out


def _denoise(image: Any, strength: int = 2) -> Any:
    """Median against isolated specks (dust, salt-and-pepper), then non-local means
    against grain; both keep the strokes of letters.  Strength 1 to 5."""
    import cv2

    strength = max(1, min(5, int(strength)))
    smooth = cv2.medianBlur(image, 3 if strength < 4 else 5)
    h = (3, 5, 8, 11, 15)[strength - 1]
    if smooth.ndim == 3:
        return cv2.fastNlMeansDenoisingColored(smooth, None, h, h, 7, 21)
    return cv2.fastNlMeansDenoising(smooth, None, h, 7, 21)


def _contrast(image: Any, strength: int = 2) -> Any:
    import cv2

    strength = max(1, min(5, int(strength)))
    clahe = cv2.createCLAHE(clipLimit=(1.0, 2.0, 3.0, 4.0, 6.0)[strength - 1],
                            tileGridSize=(8, 8))
    if image.ndim == 3:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return clahe.apply(image)


def _sharpen(image: Any, strength: int = 2) -> Any:
    import cv2

    strength = max(1, min(5, int(strength)))
    amount = (0.3, 0.6, 1.0, 1.5, 2.2)[strength - 1]
    blurred = cv2.GaussianBlur(image, (0, 0), 1.0)
    return cv2.addWeighted(image, 1.0 + amount, blurred, -amount, 0)


def _background(image: Any) -> Any:
    """Divide every colour channel by its blurred background: shadows, a yellowish light
    and grey paper become white, ink keeps its colour (a red stamp stays red)."""
    import cv2
    import numpy as np

    k = max(31, (min(image.shape[:2]) // 20) | 1)

    def evened(channel: Any) -> Any:
        after = np.maximum(cv2.medianBlur(channel, k), 1)
        norm = cv2.divide(channel.astype(np.float32), after.astype(np.float32), scale=255.0)
        return np.clip(norm, 0, 255).astype(np.uint8)

    if image.ndim == 2:
        return evened(image)
    return cv2.merge([evened(c) for c in cv2.split(image)])


Step = Callable[[Any, CleanupPlan, float], Any]


def _image_only(op: Callable[[Any], Any]) -> Step:
    """An operation that needs only the image, in the signature of a step."""
    return lambda image, a, scale: op(image)


def _with_strength(op: Callable[[Any, int], Any], switch: str) -> Step:
    """An operation on the image at the strength the plan holds in ``switch``."""
    return lambda image, a, scale: op(image, getattr(a, switch))


def geometry_only(a: CleanupPlan) -> CleanupPlan:
    """What of a plan moves the page (turning, unwarping, straightening), and nothing
    else: where everything on the page lies once it is prepared (its frame,
    :func:`frame`)."""
    return CleanupPlan(rotation=a.rotation, unwarp=a.unwarp,
                       corners=None if a.corners is None else list(a.corners),
                       straighten=a.straighten, angle=a.angle)


def turn_points(points: list[Corner], rotation: int, size: tuple[float, float]) -> list[Corner]:
    """Points on a page of ``size`` (width, height) where they lie once the page is
    turned clockwise by ``rotation`` (0, 90, 180, 270), as :func:`_step_rotation` turns
    it.  Corners are kept on the turned page; this moves them with a turn."""
    w, h = size
    turned: list[Corner] = []
    for x, y in points:
        if rotation == 90:
            x, y = h - y, x
        elif rotation == 180:
            x, y = w - x, h - y
        elif rotation == 270:
            x, y = y, w - x
        turned.append((float(x), float(y)))
    return turned


def _step_rotation(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Quarter turns clockwise, first of all, so that every later step sees an upright page."""
    import cv2

    codes = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    return cv2.rotate(image, codes[a.rotation]) if a.rotation in codes else image


def _step_unwarp(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Perspective correction with the four corners (given in points, hence ``scale``)."""
    return _unwarp(image, a.corners, scale) if a.corners and len(a.corners) == 4 else image


def _step_straighten(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Counter-clockwise by the tilt (from 0.05° on); a border tilted with the page is now
    straight and is cleaned once more."""
    if abs(a.angle) >= 0.05:
        image = _rotate(image, a.angle)
        return _clean_borders(image) if a.borders else image
    return image


def _step_sharpen(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Unsharp mask at the plan's strength."""
    return _sharpen(image, a.sharpen_strength)


def _step_background(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Even out the illumination, per colour channel."""
    return _background(image)


def _step_masks(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Fill the mask rectangles (result-page points times ``scale``) white or black, on a
    BGR copy so that the fill colour is well defined."""
    import cv2

    out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image.copy()
    colour = (255, 255, 255) if a.mask_colour == "white" else (0, 0, 0)
    for x0, y0, x1, y1 in a.masks:
        cv2.rectangle(out, (int(x0 * scale), int(y0 * scale)),
                      (int(x1 * scale), int(y1 * scale)), colour, thickness=-1)
    return out


# the steps in their fixed order: the field of the plan that switches a step on, and what
# then runs on the image; ``apply_plan`` is nothing but this sequence
_STEPS: tuple[tuple[str, Step], ...] = (
    ("rotation", _step_rotation),
    ("borders", _image_only(_clean_borders)),
    ("unwarp", _step_unwarp),
    ("straighten", _step_straighten),
    ("denoise", _with_strength(_denoise, "denoise_strength")),
    ("contrast", _with_strength(_contrast, "contrast_strength")),
    ("sharpen", _step_sharpen),
    ("background", _step_background),
    ("masks", _step_masks),
)


def apply_plan(image: Any, a: CleanupPlan, scale: float = 1.0) -> Any:
    """Apply the steps in their fixed order: rotate, clean borders, unwarp, straighten,
    denoise, contrast, sharpen, background, masks.  ``scale`` is pixels per point of
    ``image`` (corners) and of the result (masks)."""
    import numpy as np

    out = image
    for switch, step in _STEPS:
        if getattr(a, switch):
            out = step(out, a, scale)
    return np.ascontiguousarray(out)


JPEG_QUALITY = 92  # a page in colour: a photo or a colour scan came as JPEG already


def as_png(image: Any) -> bytes:
    """The image PNG-encoded (lossless, so the processed page is kept exactly)."""
    import cv2

    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise OptdocError("clean-up-failed")
    return bytes(buffer)


COLOUR_PAGES = ("jpeg", "png")  # how a page in colour is stored; the first is the default


def encoded(image: Any, colour_pages: str = "jpeg") -> bytes:
    """The prepared page as the PDF stores it: a grey page as PNG (lossless and small, a
    scan of print); a page in colour by default as JPEG at quality 92 with full colour
    resolution (4:4:4, so that a red stamp keeps its edges), or losslessly as PNG
    (``colour_pages`` "png"; some ten times the size).  The same image gives the same
    bytes with the same OpenCV.  (TIFF is no choice: a PDF holds no TIFF; a TIFF given to
    it is stored exactly as a PNG.)"""
    import cv2

    if image.ndim == 2 or colour_pages == "png":
        return as_png(image)
    ok, buffer = cv2.imencode(".jpg", image, [
        cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY,
        cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444])
    if not ok:
        raise OptdocError("clean-up-failed")
    return bytes(buffer)


def _process(page: pymupdf.Page, a: CleanupPlan, dpi: int,
             rendered: tuple[Any, float] | None = None) -> tuple[Any, float, float]:
    """Processed image of ``page`` (grey where the plan says so), its width in points and
    its pixels per point.  ``rendered`` gives the page's image and its pixels per point
    where they are at hand already (a picture's own pixels), instead of a rendering."""
    image, scale = rendered if rendered is not None else render(page, dpi)
    out = apply_plan(image, CleanupPlan(**{**a.__dict__, "masks": []}), scale)
    width = page.rect.width if a.rotation in (0, 180) else page.rect.height
    new_scale = out.shape[1] / width
    if a.masks:
        out = apply_plan(out, CleanupPlan(masks=a.masks), new_scale)
    if a.grey:
        out = _grey(out)
    return out, width, new_scale


def cleaned_image(page: pymupdf.Page, a: CleanupPlan, dpi: int = 300,
                  colour_pages: str = "jpeg") -> tuple[bytes, float, float]:
    """The page prepared by ``a`` as the PDF stores it (:func:`encoded`), and the width and
    height in points of the page that shows it: the width of the page (of its other side
    after a quarter turn), the height following the image."""
    out, width, new_scale = _process(page, a, dpi)
    return encoded(out, colour_pages), width, out.shape[0] / new_scale


def prepared_pixels(page: pymupdf.Page, a: CleanupPlan, image: Any, scale: float) -> Any:
    """A picture's own pixels (``image``, ``scale`` pixels to a point of ``page``)
    prepared by ``a``: what a picture that stays a picture is written from."""
    return _process(page, a, 0, (image, scale))[0]


def put_page_image(doc: pymupdf.Document, number: int, image: bytes, width: float,
                   height: float) -> None:
    """Replace page ``number`` of ``doc`` by a page of ``width`` × ``height`` points
    showing ``image`` (PNG or JPEG; a JPEG is stored as it is)."""
    new = doc.new_page(pno=number, width=width, height=height)
    new.insert_image(new.rect, stream=image)
    doc.delete_page(number + 1)


def preview_png(page: pymupdf.Page, a: CleanupPlan, dpi: int = 100) -> tuple[bytes, float]:
    """The processed page as PNG for the before/after view, masks included, and its
    pixels per point."""
    out, _width, scale = _process(page, a, dpi)
    return as_png(out), scale


def _np_to_pixmap(image: Any) -> pymupdf.Pixmap:
    import cv2

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if image.ndim == 3 else cv2.cvtColor(
        image, cv2.COLOR_GRAY2RGB)
    rgb = np_contig(rgb)
    return pymupdf.Pixmap(pymupdf.csRGB, rgb.shape[1], rgb.shape[0], rgb.tobytes(), False)


def np_contig(image: Any) -> Any:
    """The image as a C-contiguous array, which MuPDF's pixmap constructor requires."""
    import numpy as np

    return np.ascontiguousarray(image)


def estimate_orientation(image: Any, backend: Any = None) -> int:
    """Clockwise rotation in degrees that puts the page upright: 0 or 90 from the text
    lines (rows vary most when lines are horizontal); 0 against 180 only with an OCR
    backend, which reads both and keeps the one it is more confident about.

    An engine that turns upside-down lines round by itself (RapidOCR's line classifier,
    off by default in optdoc) reads both ways almost equally well and is asked without
    it: measured on the
    synthetic report at 100 dpi, confidence 83 upright against 75 upside down with the
    classifier, 89 against 16 without; Tesseract 83 against 24."""
    import cv2
    import numpy as np

    grey, _ = _shrunk(_grey(image), 800)
    _, bw = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    horizontal = float(np.var(bw.sum(axis=1, dtype=np.float64)))
    vertical = float(np.var(bw.sum(axis=0, dtype=np.float64)))
    # normalise by length: a page has more columns than rows or the other way round
    horizontal /= bw.shape[1] ** 2
    vertical /= bw.shape[0] ** 2
    quarter = 0 if horizontal >= vertical else 90
    if backend is None:
        return quarter
    upright = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE) if quarter == 90 else image
    small, f = _shrunk(upright, 1600)

    def value(candidate: Any) -> float:
        words = backend.recognise(_np_to_pixmap(candidate), 1.0)
        return sum(w.confidence for w in words if len(w.text.strip()) >= 3)

    turning = getattr(backend, "turn_lines", None)
    if turning is not None:
        backend.turn_lines = False
    try:
        upside_down = value(cv2.rotate(small, cv2.ROTATE_180)) > value(small) * 1.15
    finally:
        if turning is not None:
            backend.turn_lines = turning
    return (quarter + 180) % 360 if upside_down else quarter


