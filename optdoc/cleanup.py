"""Image clean-up before OCR: straighten, unwarp, upscale, even out the background.

Scans arrive tilted, photos are taken at an angle under uneven light, and both
are often small.  Every step here is optional, has an automatic suggestion
and is meant to be checked by eye before the page is read.  The
steps work on a rendered page (an image); the processed image replaces the
page, so that OCR, redaction and the output all see the same corrected page.
Needs OpenCV and NumPy (they come with the ``ocr`` extra); without them only
masks are available.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pymupdf

Corner = tuple[float, float]
Rectangle = tuple[float, float, float, float]


def available() -> bool:
    """True when OpenCV and NumPy can be imported (they come with the ``ocr`` extra)."""
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass
class CleanupPlan:
    """What to do with one page.  Angles in degrees; corners in points of the source
    page (after ``rotation``), masks as ``(x0, y0, x1, y1)`` in points of the result
    page (see :func:`replace_page`)."""

    rotation: int = 0  # 0, 90, 180, 270 clockwise, applied first
    straighten: bool = False  # rotate by -angle
    angle: float = 0.0  # estimated tilt, positive = text runs downhill to the right
    unwarp: bool = False  # perspective correction with ``corners``
    corners: list[Corner] | None = None  # four corners of the page in the (rotated) image
    upscale: int = 1  # 1 to 4: OCR reads the page at that multiple of the resolution
    letter_mode: bool = False  # letter-aware upscaling: Lanczos enlargement, sharpened strokes
    borders: bool = False  # dark scanner borders -> white
    remove_colour: bool = False  # coloured ink (stamps, highlighter) -> white
    denoise: bool = False  # median plus non-local means against specks and grain
    denoise_strength: int = 2  # 1 (gentle) to 5 (strong)
    contrast: bool = False  # CLAHE on faint copies
    contrast_strength: int = 2  # 1 to 5
    sharpen: bool = False  # unsharp mask
    sharpen_strength: int = 2  # 1 to 5
    background: bool = False  # even out illumination, white paper
    remove_lines: bool = False  # long ruled and table lines -> white
    black_white: bool = False  # binarise after that
    masks: list[Rectangle] = field(default_factory=list)  # regions to wipe, result page points
    mask_colour: str = "white"  # "white" erases (clean-up step), "black" redacts

    @property
    def active(self) -> bool:
        """True when at least one step would run, so that the page would change."""
        # the factor's resting value 1 is truthy but changes nothing
        return self.upscale > 1 or any(
            getattr(self, switch) for switch, _ in _STEPS if switch != "upscale")

    def as_dict(self) -> dict[str, Any]:
        """The plan for the report: every switch and strength, the masks only counted."""
        return {"rotation": self.rotation, "straighten": self.straighten,
                "angle": round(self.angle, 2), "unwarp": self.unwarp,
                "upscale": self.upscale, "letter_mode": self.letter_mode,
                "borders": self.borders, "remove_colour": self.remove_colour,
                "denoise": self.denoise, "denoise_strength": self.denoise_strength,
                "contrast": self.contrast, "contrast_strength": self.contrast_strength,
                "sharpen": self.sharpen, "sharpen_strength": self.sharpen_strength,
                "background": self.background,
                "remove_lines": self.remove_lines, "black_white": self.black_white,
                "masks": len(self.masks), "mask_colour": self.mask_colour}

    def full_dict(self) -> dict[str, Any]:
        """Every field, masks and corners included (the working state)."""
        d = {k: v for k, v in self.__dict__.items() if k not in ("corners", "masks")}
        d["corners"] = [list(e) for e in self.corners] if self.corners is not None else None
        d["masks"] = [list(m) for m in self.masks]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CleanupPlan:
        """The plan from a :meth:`full_dict` dictionary; keys that are no field are ignored."""
        kept = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if kept.get("corners") is not None:
            kept["corners"] = [tuple(e) for e in kept["corners"]]
        kept["masks"] = [tuple(m) for m in kept.get("masks", [])]
        return cls(**kept)


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


def find_corners(image: Any, scale: float = 1.0) -> list[Corner] | None:
    """The four corners of a sheet photographed against a background, ordered
    top-left, top-right, bottom-right, bottom-left, in points (pixels / ``scale``);
    None when no convincing quadrilateral is found (a scan that fills the image)."""
    import cv2
    import numpy as np

    grey_full = _grey(image)
    grey, f = _shrunk(grey_full, 1000)
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
        return None  # nothing, or the whole image: no correction needed
    best /= f * scale
    subtotal = best.sum(axis=1)
    diff = np.diff(best, axis=1).ravel()
    ordered = [best[np.argmin(subtotal)], best[np.argmin(diff)], best[np.argmax(subtotal)],
                best[np.argmax(diff)]]
    return [(float(x), float(y)) for x, y in ordered]


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


def native_dpi(page: pymupdf.Page) -> float | None:
    """Resolution of the largest image on the page, or None without images."""
    best: float | None = None
    for info in page.get_image_info():
        bbox = pymupdf.Rect(info["bbox"]) & page.rect
        if bbox.width < 20 or bbox.height < 20:
            continue
        dpi = info["width"] / (bbox.width / 72.0)
        if best is None or dpi > best:
            best = dpi
    return best


def suggest(image: Any, photo: bool = False, scale: float = 1.0,
              resolution: float | None = None) -> CleanupPlan:
    """Automatic suggestion for one page: straighten a visible tilt, unwarp a
    photographed sheet, upscale low-resolution images, even out an uneven background.
    ``scale`` is pixels per point of ``image``, ``resolution`` the native dpi."""
    a = CleanupPlan()
    if photo:
        corners = find_corners(image, scale)
        if corners is not None:
            a.corners, a.unwarp = corners, True
    basis = apply_plan(image, CleanupPlan(unwarp=a.unwarp, corners=a.corners), scale) \
        if a.unwarp else image
    a.angle = estimate_tilt(basis)
    # OCR engines tolerate a slight tilt, and rotating a noisy scan costs a little;
    # straighten only what the eye notices
    a.straighten = abs(a.angle) >= 1.2
    a.upscale = 2 if resolution is not None and resolution < 150 else 1
    a.letter_mode = False  # measured: no gain over plain enlargement, so an explicit choice
    a.background = photo or uneven_background(basis)
    a.borders = dark_borders(basis)
    a.remove_colour = colour_share(basis) > 0.003
    a.denoise = noise_share(basis) > 0.35
    return a


# The words of the description, in English and German (PseudonyMed writes its reports in
# German); placeholders are fields of the plan or the values the phrase functions add.
_WORDS: dict[str, dict[str, str]] = {
    "en": {
        "rotation": "rotated by {rotation}°", "unwarp": "unwarped",
        "straighten": "straightened ({angle:+.1f}°)", "upscale": "upscaled {upscale}×",
        "letter_mode": "letter mode", "borders": "borders cleaned",
        "remove_colour": "coloured ink removed", "denoise": "denoised",
        "contrast": "contrast raised", "sharpen": "sharpened", "background": "background evened",
        "remove_lines": "lines removed", "black_white": "black and white",
        "masks_white": "{n} region(s) erased", "masks_black": "{n} region(s) redacted",
        "unchanged": "unchanged", "decimal": ".",
    },
    "de": {
        "rotation": "um {rotation}° gedreht", "unwarp": "entzerrt",
        "straighten": "begradigt ({angle:+.1f}°)", "upscale": "{upscale}× hochskaliert",
        "letter_mode": "Buchstabenmodus", "borders": "Ränder gesäubert",
        "remove_colour": "farbige Tinte entfernt", "denoise": "entrauscht",
        "contrast": "Kontrast angehoben", "sharpen": "geschärft",
        "background": "Hintergrund geglättet", "remove_lines": "Linien entfernt",
        "black_white": "Schwarz-Weiß",
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


def _phrase_upscaled(a: CleanupPlan, w: dict[str, str]) -> str | None:
    """The factor, with the letter mode in brackets; nothing at factor 1."""
    if a.upscale <= 1:
        return None
    return w["upscale"].format(upscale=a.upscale) + (
        f" ({w['letter_mode']})" if a.letter_mode else "")


def _phrase_letter_mode(a: CleanupPlan, w: dict[str, str]) -> str | None:
    """The letter mode on its own, unless the upscaling phrase has mentioned it already."""
    return w["letter_mode"] if a.upscale <= 1 else None


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
    ("upscale", _phrase_upscaled),
    ("letter_mode", _phrase_letter_mode),
    ("borders", None),
    ("remove_colour", None),
    ("denoise", None),
    ("contrast", None),
    ("sharpen", None),
    ("background", None),
    ("remove_lines", None),
    ("black_white", None),
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
    return ", ".join(parts) if parts else w["unchanged"]


# -- application ---------------------------------------------------------------------------------


def _unwarp(image: Any, corners: list[Corner], scale: float) -> Any:
    import cv2
    import numpy as np

    source = np.array(corners, dtype=np.float32) * scale
    (ol, orr, ur, ul) = source
    width = int(max(np.linalg.norm(orr - ol), np.linalg.norm(ur - ul)))
    height = int(max(np.linalg.norm(ul - ol), np.linalg.norm(ur - orr)))
    if width < 10 or height < 10:
        return image
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                    dtype=np.float32)
    m = cv2.getPerspectiveTransform(source, target)
    return cv2.warpPerspective(image, m, (width, height), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


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


def _remove_colour(image: Any) -> Any:
    """Coloured ink (stamps, highlighter, signatures in blue) becomes white; black and
    grey print stays.  Returns a grey image."""
    import cv2
    import numpy as np

    if image.ndim != 3:
        return image
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    coloured = (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 60)
    coloured = cv2.dilate(coloured.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1) > 0
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    grey[coloured] = 255
    return grey


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


def letter_finish(grey: Any, factor: int = 2) -> Any:
    """Letter-aware finish for an upscaled (or large) rendering: grey, strokes sharpened.

    Measured on synthetic scans (RapidOCR): a hard local threshold (Sauvola) after the
    enlargement looked crisp but wrecked the recognition (down to 0.0 on a noisy
    150-dpi scan), whereas Lanczos enlargement plus unsharp masking in grey scale
    matched or beat the plain enlargement.  The recogniser wants grey, not binary.
    """
    return _sharpen(_grey(grey), 2)


def _upscale(image: Any, factor: int, letter_mode: bool) -> Any:
    import cv2

    if letter_mode:
        grey = _grey(image)
        large = cv2.resize(grey, None, fx=factor, fy=factor, interpolation=cv2.INTER_LANCZOS4)
        return letter_finish(large, factor)
    return cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)


def _remove_lines(image: Any) -> Any:
    """Long horizontal and vertical lines (forms, tables, underlines) become white;
    letters are far shorter than the kernels and survive."""
    import cv2
    import numpy as np

    grey = _grey(image)
    h, w = grey.shape
    _, bw = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    horizontal = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(30, w // 25), 1)))
    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(30, h // 25))))
    rules = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((3, 3), np.uint8))
    out = image.copy()
    out[rules > 0] = (255, 255, 255) if out.ndim == 3 else 255
    return out


def grid_areas(image: Any) -> list[tuple[int, int, int, int]]:
    """Pixel boxes of table grids: connected long horizontal and vertical rules that
    together span at least 15 % of the width and 2 % of the height.  Tesseract's page
    segmentation treats such a grid as graphics and drops the cells; the OCR reads the
    boxes again without their lines (:class:`~optdoc.ocr.TesseractBackend`)."""
    import cv2

    grey = _grey(image)
    h, w = grey.shape
    _, bw = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    horizontal = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(20, w // 25), 1)))
    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(20, h // 40))))
    rules = cv2.dilate(cv2.bitwise_or(horizontal, vertical), cv2.getStructuringElement(
        cv2.MORPH_RECT, (5, 5)))
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(rules, connectivity=8)
    areas: list[tuple[int, int, int, int]] = []
    for i in range(1, n):
        x, y, bb, bh, _area = (int(v) for v in stats[i])
        if bb < w * 0.15 or bh < h * 0.02:
            continue
        if not cv2.countNonZero(horizontal[y:y + bh, x:x + bb]) or \
                not cv2.countNonZero(vertical[y:y + bh, x:x + bb]):
            continue  # a lone rule or a bar, not a grid
        areas.append((x, y, x + bb, y + bh))
    return areas


def without_lines(image: Any) -> Any:
    """Public wrapper: the image with long rules removed (see :func:`_remove_lines`)."""
    return _remove_lines(image)


def _background(image: Any) -> Any:
    """Divide by the blurred background: shadows and grey paper become white, ink stays."""
    import cv2
    import numpy as np

    grey = _grey(image)
    k = max(31, (min(grey.shape) // 20) | 1)
    after = cv2.medianBlur(grey, k)
    after = np.maximum(after, 1)
    norm = cv2.divide(grey.astype(np.float32), after.astype(np.float32), scale=255.0)
    return np.clip(norm, 0, 255).astype(np.uint8)


Step = Callable[[Any, CleanupPlan, float], Any]


def _image_only(op: Callable[[Any], Any]) -> Step:
    """An operation that needs only the image, in the signature of a step."""
    return lambda image, a, scale: op(image)


def _with_strength(op: Callable[[Any, int], Any], switch: str) -> Step:
    """An operation on the image at the strength the plan holds in ``switch``."""
    return lambda image, a, scale: op(image, getattr(a, switch))


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


def _step_upscale(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Enlarge by the factor, letter-aware in letter mode; factor 1 changes nothing."""
    return _upscale(image, a.upscale, a.letter_mode) if a.upscale > 1 else image


def _step_letter_mode(image: Any, a: CleanupPlan, scale: float) -> Any:
    """The letter-mode finish without enlargement, unless the upscaling applied it already."""
    return letter_finish(image, 1) if a.upscale <= 1 else image


def _step_sharpen(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Unsharp mask, unless the letter mode has sharpened already."""
    return image if a.letter_mode else _sharpen(image, a.sharpen_strength)


def _step_background(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Even out the illumination; not in letter mode, which keeps its grey as it is."""
    return image if a.letter_mode else _background(image)


def _step_black_white(image: Any, a: CleanupPlan, scale: float) -> Any:
    """Adaptive threshold to pure black and white; never in letter mode (measured: worse OCR)."""
    import cv2

    return image if a.letter_mode else cv2.adaptiveThreshold(
        _grey(image), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


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
    ("remove_colour", _image_only(_remove_colour)),
    ("denoise", _with_strength(_denoise, "denoise_strength")),
    ("contrast", _with_strength(_contrast, "contrast_strength")),
    ("upscale", _step_upscale),
    ("letter_mode", _step_letter_mode),
    ("sharpen", _step_sharpen),
    ("background", _step_background),
    ("remove_lines", _image_only(_remove_lines)),
    ("black_white", _step_black_white),
    ("masks", _step_masks),
)


def apply_plan(image: Any, a: CleanupPlan, scale: float = 1.0) -> Any:
    """Apply the steps in their fixed order: rotate, clean borders, unwarp, straighten,
    drop colour, denoise, contrast, upscale (letter mode), sharpen, background, lines,
    black-and-white, masks.  ``scale`` is pixels per point of ``image`` (corners) and
    of the result (masks)."""
    import numpy as np

    out = image
    for switch, step in _STEPS:
        if getattr(a, switch):
            out = step(out, a, scale)
    return np.ascontiguousarray(out)


def as_png(image: Any) -> bytes:
    """The image PNG-encoded (lossless, so the processed page is kept exactly)."""
    import cv2

    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG encoding failed")
    return bytes(buffer)


def _process(page: pymupdf.Page, a: CleanupPlan, dpi: int,
                with_upscaling: bool = True) -> tuple[Any, float, float]:
    """Processed image of ``page``, its width in points and its pixels per point."""
    image, scale = render(page, dpi)
    steps = CleanupPlan(**{**a.__dict__, "masks": [],
                               "upscale": a.upscale if with_upscaling else 1})
    out = apply_plan(image, steps, scale)
    width = page.rect.width if a.rotation in (0, 180) else page.rect.height
    new_scale = out.shape[1] / width
    if a.masks:
        out = apply_plan(out, CleanupPlan(masks=a.masks), new_scale)
    return out, width, new_scale


def replace_pages(docs: list[pymupdf.Document], number: int, a: CleanupPlan,
                    dpi: int = 300) -> float:
    """Replace page ``number`` in every document of ``docs`` (copies of the same file)
    by its processed image, rendered once from the first.  The page keeps its width
    in points; the height follows the image.  Returns the pixels per point of the
    new page."""
    # upscaling is not baked into the page (no information gained, the file would bloat);
    # the pipeline renders such pages for OCR at the higher resolution instead
    out, width, new_scale = _process(docs[0][number], a, dpi, with_upscaling=False)
    png = as_png(out)
    height = out.shape[0] / new_scale
    for doc in docs:
        new = doc.new_page(pno=number, width=width, height=height)
        new.insert_image(new.rect, stream=png)
        doc.delete_page(number + 1)
    return new_scale


def replace_page(doc: pymupdf.Document, number: int, a: CleanupPlan, dpi: int = 300) -> float:
    """:func:`replace_pages` for a single document."""
    return replace_pages([doc], number, a, dpi)


def preview_png(page: pymupdf.Page, a: CleanupPlan, dpi: int = 100,
                 max_pixel: int = 3000) -> tuple[bytes, float]:
    """The processed page as PNG for the before/after view, masks included, and its
    pixels per point.  Upscaling is shown: the rendering resolution is lowered so that
    the enlarged image stays below ``max_pixel`` on its long side; the view scales it
    back to the size of the original, so zooming in reveals the gain."""
    f = max(1, a.upscale)
    if f > 1:
        long = max(page.rect.width, page.rect.height) / 72.0  # inches
        dpi = max(36, min(dpi, int(max_pixel / (f * long))))
    out, _width, scale = _process(page, a, dpi, with_upscaling=True)
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


