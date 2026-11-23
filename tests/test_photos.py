"""Photographed pages: told from scans by the page itself, inside a PDF too (photos bound
the way medRDS binds them), unwarped; turned pages read and written upright."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf
import pytest

from optdoc import cleanup, output
from optdoc import ocr as ocrlib
from optdoc.loading import open_document
from optdoc.reading import read
from tests.synthetic import bind, camera_photo, lab_report, photograph

pytestmark = pytest.mark.skipif(not cleanup.available(), reason="needs OpenCV (extra 'ocr')")
needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                   reason="no OCR engine installed")


def _image(page: pymupdf.Page) -> tuple:
    return cleanup.render(page, 150)


def test_frames_on_a_scan_are_no_sheet(tmp_path: Path) -> None:
    """On a scan, the frame of a ruled table looks like a sheet to an edge search; cut to
    it, the page would lose its head and foot.  So would a form whose frame holds all of
    it, with bare paper around.  Paper around the frame tells, and the corner search
    itself asks it (with ``--photo`` too)."""
    pdf, _ = lab_report(tmp_path, 1)
    form = pymupdf.open()
    page = form.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(50, 60, 545, 780), color=(0, 0, 0), width=2)
    page.insert_text((80, 120), "Formular: alles im Rahmen", fontsize=14)
    with pymupdf.open(pdf) as doc:
        pages = [_image(doc[0]), _image(form[0])]
    for image, scale in pages:
        assert cleanup.find_corners(image, scale) is None
        assert cleanup.sheet_in_photo(image, scale) is None
        assert not cleanup.suggest(image, None, scale).unwarp


@pytest.mark.parametrize("desk", [(55, 65, 80), (150, 150, 150), (200, 180, 150)])
def test_sheet_on_a_desk_is_found(tmp_path: Path, desk: tuple[int, int, int]) -> None:
    """A sheet photographed on a dark, a grey or a wooden desk is a photo."""
    pdf, _ = lab_report(tmp_path, 2)
    with open_document(photograph(pdf, tmp_path / "foto.jpg", desk=desk)) as doc:
        image, scale = _image(doc[0])
    corners = cleanup.sheet_in_photo(image, scale)
    assert corners is not None
    plan = cleanup.suggest(image, None, scale)
    assert plan.unwarp and plan.background


def test_photos_bound_into_a_pdf(tmp_path: Path) -> None:
    """Photos bound into a PDF (one taken with the phone on its side, so its page is
    turned by /Rotate) are opened upright with their JPEG untouched, and each is
    unwarped as a photo; ``--scan`` leaves them alone."""
    pdf, _ = lab_report(tmp_path, 1)
    side = photograph(pdf, tmp_path / "quer.jpg", orientation=6)
    straight = photograph(pdf, tmp_path / "gerade.jpg", orientation=1, seed=2)
    bound = bind([side, straight], tmp_path / "geheftet.pdf")
    with pymupdf.open(bound) as raw:
        assert raw[0].rotation == 90
    with open_document(bound) as doc:
        assert [p.rotation for p in doc] == [0, 0]
        assert doc[0].rect.height > doc[0].rect.width  # upright: portrait
        jpegs = {doc.xref_stream_raw(x) for x in range(1, doc.xref_length())
                 if doc.xref_is_image(x)}
        assert side.read_bytes() in jpegs and straight.read_bytes() in jpegs
        for page in doc:
            image, scale = _image(page)
            assert cleanup.suggest(image, None, scale).unwarp
            assert not cleanup.suggest(image, False, scale).unwarp


@needs_backend
def test_bound_photo_read_upright(tmp_path: Path) -> None:
    """The page turned by /Rotate is read upright and written upright; the boxes of the
    reading are where the PDF has its words, with and without clean-up."""
    pdf, truth = lab_report(tmp_path, 2)
    side = photograph(pdf, tmp_path / "quer.jpg", orientation=6)
    bound = bind([side], tmp_path / "geheftet.pdf")
    for clean_up in (True, False):
        reading = read(bound, clean_up=clean_up)
        try:
            assert reading.pages[0].ocr and bool(reading.plan) == clean_up
            text = reading.pages[0].text
            first = truth[0].split()[0]
            assert first in text.text
            a = text.text.index(first)
            box = text.rects(a, a + len(first))[0]
            paths = output.write(reading, tmp_path / f"out-{clean_up}")
        finally:
            reading.close()
        with pymupdf.open(paths["pdf"]) as out:
            assert out[0].rotation == 0
            found = out[0].search_for(first)
            assert any(abs(r.x0 - box.x0) < 1 and abs(r.y0 - box.y0) < 3 for r in found)


@needs_backend
def test_exif_turned_photo(tmp_path: Path) -> None:
    """A JPEG whose pixels lie on their side, with EXIF saying so, is read upright."""
    pdf, truth = lab_report(tmp_path, 3)
    reading = read(photograph(pdf, tmp_path / "foto.jpg", orientation=6))
    try:
        page = reading.doc[0]
        assert page.rect.height > page.rect.width and reading.plan[0].unwarp
        assert truth[0].split()[0] in reading.pages[0].text.text
    finally:
        reading.close()


# -- photographed at a slant ----------------------------------------------------------------------
def _unwarped_corners(found: list, true: Any, size: tuple[int, int]) -> Any:
    """Where the sheet's true corners land after unwarping with the corners found, as
    optdoc does it (true proportions): top-left, top-right, bottom-right, bottom-left."""
    import cv2
    import numpy as np

    q = np.array(found, dtype=np.float64)
    aspect = cleanup.sheet_aspect(q, (size[0] / 2, size[1] / 2))
    height = max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))
    target = np.float32([[0, 0], [height * aspect, 0], [height * aspect, height], [0, height]])
    m = cv2.getPerspectiveTransform(q.astype(np.float32), target)
    return cv2.perspectiveTransform(np.float32(true).reshape(-1, 1, 2), m).reshape(-1, 2)


def _square(points: Any) -> tuple[float, float]:
    """How far four points are from a rectangle with A4's proportions: the largest
    deviation of the sides from level and plumb, as a share of the height, and that of
    the proportions from A4's."""
    import numpy as np

    tl, tr, br, bl = points
    height = float(np.linalg.norm(bl - tl))
    deviations = [abs(tl[1] - tr[1]), abs(bl[1] - br[1]), abs(tl[0] - bl[0]), abs(tr[0] - br[0])]
    width = float(np.linalg.norm(tr - tl))
    return max(deviations) / height, abs(width / height / 2 ** -0.5 - 1)


@pytest.mark.parametrize("case", [
    {"pitch": 30, "yaw": 10, "roll": 4},  # strongly slanted, on a dark desk
    {"pitch": 25, "yaw": -6, "roll": 2, "fill": 0.88},  # a corner runs out of the photo
    {"pitch": 20, "yaw": 5, "roll": -3, "desk": "light"},  # on a light grey table
    {"pitch": 20, "yaw": 6, "roll": 3, "fill": 1.02},  # the foot of the sheet is cut off
], ids=["slanted", "corner-cut", "light-table", "edge-cut"])
def test_sheet_photographed_at_a_slant(tmp_path: Path, case: dict) -> None:
    """A sheet photographed at a slant comes out square and in A4's proportions: the
    true corners map to a rectangle, level and plumb within 1 %, also where the photo
    cut a corner off or the whole foot of the sheet (that edge is reconstructed), and on
    a table only a little darker than paper; the proportions within 1 % (snapped to A4),
    within 3 % for a sheet whose edge was reconstructed (only part of it is seen, so it
    is not snapped).  Before: the proportions from the sides alone were off by up to
    43 %, and a corner outside the photo meant no sheet, or the table taken for it."""
    import numpy as np

    pdf, _ = lab_report(tmp_path, 1)
    image, true = camera_photo(pdf, **case)
    found = cleanup.sheet_in_photo(image, 1.0)
    assert found is not None
    level, proportions = _square(_unwarped_corners(found, true, (image.shape[1], image.shape[0])))
    assert level < 0.01
    assert proportions < (0.03 if case.get("fill", 0.8) > 1 else 0.01)
    inside = [(x, y) for x, y in true if 0 <= x < image.shape[1] and 0 <= y < image.shape[0]]
    for x, y in inside:  # every corner in the photo is found, within a few pixels
        assert min(np.hypot(x - c[0], y - c[1]) for c in found) < 0.005 * np.hypot(*image.shape[:2])


def test_proportions_of_a_rectangle_seen_at_a_slant() -> None:
    """Zhang and He's proportions: exact for a rectangle of any shape seen by a phone's
    camera, also nearly head-on, where the focal length cannot be told from the corners
    and a phone's is taken; from the sides alone, as before, far off."""
    import math

    import numpy as np

    w, h = 1200, 1600
    focal = 26 / 43.27 * math.hypot(w, h)
    for ratio, pitch, yaw in ((1.5, 25, 12), (0.5, 35, 0), (1.0, 2, 1), (0.8, 18, -9)):
        p, y = math.radians(pitch), math.radians(yaw)
        about_y = [[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]]
        about_x = [[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]]
        turn = np.array(about_y) @ np.array(about_x)
        half = np.array([100 * ratio, 100])
        rect = np.array([[-half[0], -half[1], 0], [half[0], -half[1], 0],
                         [half[0], half[1], 0], [-half[0], half[1], 0]])
        points = (turn @ rect.T).T + [0, 0, 500]
        q = np.c_[focal * points[:, 0] / points[:, 2] + w / 2,
                  focal * points[:, 1] / points[:, 2] + h / 2]
        assert cleanup.sheet_aspect(q, (w / 2, h / 2)) == pytest.approx(ratio, rel=0.005)
        if pitch > 20:
            assert abs(cleanup._side_aspect(q) / ratio - 1) > 0.05
