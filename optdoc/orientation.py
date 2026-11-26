"""Which way up a page stands, told by a model where one is there.

optdoc's rules tell portrait from landscape by the lines of the text
(:func:`optdoc.cleanup.estimate_orientation`), but not a page that stands on its head:
that takes reading it, which is ocrdoc's step.  A small model tells all four turns at a
glance: PaddleOCR's document orientation classifier (PP-LCNet_x1_0_doc_ori, Apache-2.0,
6.8 MB), an optional download (:mod:`optdoc.models`).  OpenCV runs it; optdoc needs
nothing more for it.

Measured on invented pages (``bench/orientation_bench.py``: twelve laboratory reports and
a two-page letter, each page turned four ways), how often the turn that puts the page
upright was named:

==============================  =====  ==========  =============  =========
pages                           of     lines only  lines and OCR  the model
==============================  =====  ==========  =============  =========
as made                         56     28          56             56
worn scans (askew, grainy)      56     28          56             55
photographed at a slant         48     24          not measured   44
scanned at 60 dpi               48     24          not measured   48
one to three lines of text      20     10          not measured   20
seconds per page                       0.002       2.1            0.009
==============================  =====  ==========  =============  =========

The lines alone cannot tell a page on its head, so they are right for half the turns.
Where the model was not right it was not sure and left the page as it was (one worn scan,
four photos, the blank page): **it turned no page of the bench wrongly.**

The model looks at a square from the middle of the page, as it was trained.  A page with a
few lines at its top shows it nothing there (the middle alone decided 4 of those 20, with
every turn equally likely for the rest); so where the middle says little, the model is
shown the middle of what is written instead.  It decides only when it is sure
(:data:`SURE`), and a blank page is left as it is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SURE = 0.8  # the least probability at which the model's answer counts
_MEAN = (0.485, 0.456, 0.406)
_STD = (0.229, 0.224, 0.225)
_nets: dict[str, Any] = {}


def _net(path: Path) -> Any:
    """The model, loaded once."""
    import cv2

    key = str(path)
    if key not in _nets:
        _nets[key] = cv2.dnn.readNetFromONNX(key)
    return _nets[key]


def written(image: Any) -> tuple[int, int, int, int] | None:
    """The box of what is written on the page (pixels): where it is clearly darker than
    the paper; None for a page with nothing on it."""
    import cv2
    import numpy as np

    grey = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(grey, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    ink = (small < float(np.median(small)) - 60).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    ys, xs = np.nonzero(ink)
    if len(xs) < 20:
        return None
    x0, x1 = (int(np.percentile(xs, p)) * 4 for p in (1, 99))
    y0, y1 = (int(np.percentile(ys, p)) * 4 for p in (1, 99))
    margin = 8
    return (max(0, x0 - margin), max(0, y0 - margin),
            min(image.shape[1], x1 + margin), min(image.shape[0], y1 + margin))


def _middle_of_writing(image: Any) -> Any | None:
    """The part of the page to show the model where the page's middle is empty: what is
    written, and of a band of it (a few lines) the square around its middle."""
    box = written(image)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    if min(width, height) < 0.5 * max(width, height):
        half = max(min(width, height), 96) // 2
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        x0, x1 = max(0, cx - half), min(image.shape[1], cx + half)
        y0, y1 = max(0, cy - half), min(image.shape[0], cy + half)
    return image[y0:y1, x0:x1]


def probabilities(image: Any, model: Path) -> list[float]:
    """How likely the page (a BGR image) is turned clockwise by 0, 90, 180 and 270
    degrees, as the model sees its middle: the short side to 256 pixels, the square of
    224 from the centre, as the model was trained."""
    import cv2
    import numpy as np

    rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB) if image.ndim == 2 else image[:, :, ::-1]
    h, w = rgb.shape[:2]
    f = 256 / min(h, w)
    small = cv2.resize(rgb, (max(224, round(w * f)), max(224, round(h * f))),
                       interpolation=cv2.INTER_LINEAR)
    y, x = (small.shape[0] - 224) // 2, (small.shape[1] - 224) // 2
    crop = (small[y:y + 224, x:x + 224].astype(np.float32) / 255.0
            - np.array(_MEAN, np.float32)) / np.array(_STD, np.float32)
    net = _net(model)
    net.setInput(np.ascontiguousarray(crop.transpose(2, 0, 1)[None]))
    return [float(v) for v in net.forward()[0]]


def decided(page: list[float], writing: list[float] | None) -> int | None:
    """The turn the model is sure of (0, 90, 180 or 270 clockwise): by the middle of the
    page where that is sure, else by the middle of what is written; None where neither
    is."""
    for seen in (page, writing):
        if seen is not None and max(seen) >= SURE:
            return seen.index(max(seen)) * 90
    return None


def turned(image: Any, model: Path) -> int | None:
    """How far the page stands turned clockwise (0, 90, 180, 270), where the model is sure;
    None where it is not (a blank page, a page it cannot tell)."""
    page = probabilities(image, model)
    if max(page) >= SURE:
        return decided(page, None)
    part = _middle_of_writing(image)
    return decided(page, None if part is None else probabilities(part, model))


def upright(image: Any, model: Path) -> int | None:
    """The clockwise turn that puts the page upright, where the model is sure; None where
    it is not."""
    stands = turned(image, model)
    return None if stands is None else (360 - stands) % 360
