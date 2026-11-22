"""Image clean-up: tilt estimate, sheet detection, upscaling, background, masks."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from optdoc import cleanup

pytestmark = pytest.mark.skipif(not cleanup.available(), reason="OpenCV/NumPy fehlen (Extra ocr)")


def _page(report: Path) -> pymupdf.Page:
    doc = pymupdf.open(report)
    return doc[0]


def test_tilt_is_estimated(report: Path) -> None:
    import cv2

    image, _ = cleanup.render(_page(report), 150)
    assert abs(cleanup.estimate_tilt(image)) < 0.3  # straight page
    for expected in (2.0, -3.5):
        h, w = image.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), -expected, 1.0)  # clockwise = downhill
        tilted = cv2.warpAffine(image, m, (w, h), borderMode=cv2.BORDER_CONSTANT,
                                borderValue=(255, 255, 255))
        estimated = cleanup.estimate_tilt(tilted)
        assert abs(estimated - expected) <= 0.35, (expected, estimated)
        assert cleanup.suggest(tilted).straighten  # 2° and 3.5° are worth straightening
        straight = cleanup.apply_plan(tilted, cleanup.CleanupPlan(straighten=True, angle=estimated))
        assert abs(cleanup.estimate_tilt(straight)) < 0.35


def test_sheet_in_photo_is_found(report: Path) -> None:
    import cv2
    import numpy as np

    image, _ = cleanup.render(_page(report), 100)
    h, w = image.shape[:2]
    # a dark table with the page photographed at an angle
    photo = np.full((h + 300, w + 300, 3), (60, 70, 80), dtype=np.uint8)
    target = np.array([[180, 120], [w + 90, 170], [w + 150, h + 200], [120, h + 240]],
                    dtype=np.float32)
    m = cv2.getPerspectiveTransform(np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32),
                                    target)
    distorted = cv2.warpPerspective(image, m, (w + 300, h + 300), dst=photo,
                                   borderMode=cv2.BORDER_TRANSPARENT)
    corners = cleanup.find_corners(distorted)  # skala 1: corners in pixels
    assert corners is not None and len(corners) == 4
    for (x, y), (sx, sy) in zip(corners, target, strict=True):
        assert abs(x - sx) < 12 and abs(y - sy) < 12, (corners, target)
    unwarped = cleanup.apply_plan(distorted, cleanup.CleanupPlan(unwarp=True, corners=corners))
    assert abs(unwarped.shape[1] / unwarped.shape[0] - w / h) < 0.08
    assert abs(cleanup.estimate_tilt(unwarped)) < 0.6
    assert cleanup.find_corners(image) is None  # a page that fills the image needs nothing
    v = cleanup.suggest(distorted, photo=True)
    assert v.unwarp and v.background and v.corners is not None
    assert "entzerrt" in cleanup.describe(v, "de") and "Hintergrund" in cleanup.describe(v, "de")


def test_upscale_background_masks(report: Path) -> None:
    import numpy as np

    image, scale = cleanup.render(_page(report), 72)
    h, w = image.shape[:2]
    large = cleanup.apply_plan(image, cleanup.CleanupPlan(upscale=2))
    assert large.shape[0] == 2 * h and large.shape[1] == 2 * w
    shadow = image.astype(np.int16) - np.linspace(0, 90, w, dtype=np.int16)[None, :, None]
    shadow = np.clip(shadow, 0, 255).astype(np.uint8)
    assert cleanup.uneven_background(shadow) and not cleanup.uneven_background(image)
    clean = cleanup.apply_plan(shadow, cleanup.CleanupPlan(background=True))
    assert clean.ndim == 2 and np.median(clean[:, -40:]) > 240  # the shadow is gone
    sw = cleanup.apply_plan(image, cleanup.CleanupPlan(black_white=True))
    assert set(np.unique(sw)) <= {0, 255}
    masked = cleanup.apply_plan(image, cleanup.CleanupPlan(masks=[(10, 10, 60, 30)]), scale)
    assert masked[15:25, 15:55].min() == 255  # the clean-up erases (white)
    redacted = cleanup.apply_plan(image, cleanup.CleanupPlan(masks=[(10, 10, 60, 30)],
                                                     mask_colour="black"), scale)
    assert redacted[15:25, 15:55].max() == 0 and redacted[100:, 100:].max() == 255
    v = cleanup.suggest(image, resolution=120)
    assert v.upscale == 2 and not v.unwarp and not v.straighten
    assert v.as_dict()["upscale"] == 2
    assert cleanup.suggest(image, resolution=300).upscale == 1
    assert cleanup.describe(cleanup.CleanupPlan(), "de") == "unverändert"


def test_replace_page(report: Path, tmp_path: Path) -> None:
    doc = pymupdf.open(report)
    width = doc[0].rect.width
    scale = cleanup.replace_page(doc, 0, cleanup.CleanupPlan(straighten=True, angle=1.0,
                                                        masks=[(56, 60, 300, 90)]), dpi=100)
    assert scale > 0 and len(doc) == 2 and abs(doc[0].rect.width - width) < 0.01
    assert doc[0].get_images() and not doc[0].get_text("text").strip()  # an image page now
    pix = doc[0].get_pixmap(clip=pymupdf.Rect(60, 65, 290, 85), colorspace=pymupdf.csGRAY)
    assert min(pix.samples) > 240  # the erased region is white on the new page
    png, scale_v = cleanup.preview_png(doc[1], cleanup.CleanupPlan(rotation=90), dpi=50)
    assert png.startswith(b"\x89PNG") and scale_v > 0
    large, scale_g = cleanup.preview_png(doc[1], cleanup.CleanupPlan(upscale=4), dpi=100)
    assert scale_g > scale_v  # shown enlarged, rendered at a lower dpi to stay bounded
    doc.close()


def test_further_steps(report: Path) -> None:
    import cv2
    import numpy as np

    image, scale = cleanup.render(_page(report), 100)
    h, w = image.shape[:2]
    # dark scanner border
    framed = image.copy()
    framed[:, :25] = 20
    framed[-30:, :] = 30
    assert cleanup.dark_borders(framed) and not cleanup.dark_borders(image)
    clean = cleanup.apply_plan(framed, cleanup.CleanupPlan(borders=True))
    assert clean[:, :20].min() == 255 and clean[-20:, :].min() == 255
    assert clean[100:200, 100:300].min() < 50  # the text is still there
    # a red stamp and a blue signature vanish, black print stays
    stamped = image.copy()
    cv2.rectangle(stamped, (400, 600), (700, 700), (40, 40, 220), thickness=-1)
    cv2.line(stamped, (100, 900), (600, 960), (200, 60, 30), 8)
    assert cleanup.colour_share(stamped) > 0.003 > cleanup.colour_share(image)
    without = cleanup.apply_plan(stamped, cleanup.CleanupPlan(remove_colour=True))
    assert without.ndim == 2 and without[620:680, 450:650].min() == 255
    assert without[100:200, 100:300].min() < 50
    # salt-and-pepper grain
    rng = np.random.default_rng(1)
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    grainy = grey.copy()
    mask = rng.random(grey.shape) < 0.02
    grainy[mask] = 0
    assert cleanup.noise_share(grainy) > 0.35 > cleanup.noise_share(grey)
    denoised = cleanup.apply_plan(grainy, cleanup.CleanupPlan(denoise=True))
    assert cleanup.noise_share(denoised) < cleanup.noise_share(grainy) / 2
    # contrast and sharpening keep size and type
    for a in (cleanup.CleanupPlan(contrast=True), cleanup.CleanupPlan(sharpen=True)):
        out = cleanup.apply_plan(image, a)
        assert out.shape[:2] == (h, w) and out.dtype == np.uint8
    # ruled lines vanish, letters survive
    ruled = image.copy()
    cv2.line(ruled, (50, 500), (w - 50, 500), (0, 0, 0), 3)
    cv2.line(ruled, (300, 50), (300, h - 50), (0, 0, 0), 3)
    without_lines = cleanup.apply_plan(ruled, cleanup.CleanupPlan(remove_lines=True))
    assert without_lines[497:504, 400:800].min() == 255
    assert without_lines[100:200, 100:300].min() < 50
    # erasing masks are white in the clean-up, black in redaction
    white = cleanup.apply_plan(image, cleanup.CleanupPlan(masks=[(10, 10, 60, 30)]), scale)
    assert white[15:25, 15:55].min() == 255
    black = cleanup.apply_plan(image, cleanup.CleanupPlan(masks=[(10, 10, 60, 30)],
                                                 mask_colour="black"), scale)
    assert black[15:25, 15:55].max() == 0
    assert "gelöscht" in cleanup.describe(cleanup.CleanupPlan(masks=[(0, 0, 1, 1)]), "de")


def test_letter_mode_and_factors(report: Path) -> None:
    import numpy as np

    image, _ = cleanup.render(_page(report), 72)
    h, w = image.shape[:2]
    for factor in (2, 3, 4):
        large = cleanup.apply_plan(image, cleanup.CleanupPlan(upscale=factor, letter_mode=True))
        assert large.shape == (factor * h, factor * w) and large.dtype == np.uint8
        # letter mode: grey image, white paper, dark sharpened strokes
        assert large.ndim == 2 and np.median(large) == 255 and large.min() < 40
    fine = cleanup.letter_finish(image, factor=1)
    assert fine.shape == (h, w) and np.median(fine) == 255
    v = cleanup.suggest(image, resolution=100)
    assert v.upscale == 2 and not v.letter_mode  # letter mode is never suggested
    assert "Buchstabenmodus" in cleanup.describe(cleanup.CleanupPlan(letter_mode=True), "de")


def test_orientation(report: Path) -> None:
    import cv2

    image, _ = cleanup.render(_page(report), 100)
    assert cleanup.estimate_orientation(image) == 0
    landscape = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    assert cleanup.estimate_orientation(landscape) == 90
    upright = cleanup.apply_plan(landscape, cleanup.CleanupPlan(rotation=90))
    assert upright.shape[:2] == image.shape[:2]
    from optdoc import ocr as ocrlib

    if ocrlib.available_backends():
        backend = ocrlib.backend("auto")
        flipped = cv2.rotate(image, cv2.ROTATE_180)
        assert cleanup.estimate_orientation(flipped, backend) == 180
        assert cleanup.estimate_orientation(image, backend) == 0


def test_tilt_despite_dark_border(report: Path) -> None:
    """A dark border that is tilted along with the page must not fool the estimate;
    cleaning runs before and after straightening."""
    import cv2

    image, _ = cleanup.render(_page(report), 100)
    h, w = image.shape[:2]
    image[:, :20] = 25  # scanner border, then the whole thing is tilted
    m = cv2.getRotationMatrix2D((w / 2, h / 2), -2.5, 1.0)
    tilted = cv2.warpAffine(image, m, (w, h), borderValue=(255, 255, 255))
    assert abs(cleanup.estimate_tilt(tilted) - 2.5) <= 0.4
    assert cleanup.dark_borders(tilted)
    plan = cleanup.CleanupPlan(straighten=True, angle=2.5, borders=True)
    straight = cleanup.apply_plan(tilted, plan)
    assert straight[h // 2 - 100:h // 2 + 100, :12].min() == 255  # the wedge is gone


def test_description_and_active() -> None:
    """Every step has its phrase, in the listed order; a plan is active once a step would run."""
    A = cleanup.CleanupPlan
    assert not A().active and not A(upscale=1).active
    for plan in (A(rotation=90), A(upscale=2), A(masks=[(0, 0, 1, 1)]), A(straighten=True),
                 A(unwarp=True), A(letter_mode=True), A(borders=True), A(remove_colour=True),
                 A(denoise=True), A(contrast=True), A(sharpen=True), A(background=True),
                 A(remove_lines=True), A(black_white=True)):
        assert plan.active, plan
    assert cleanup.describe(A(rotation=90), "de") == "um 90° gedreht"
    assert cleanup.describe(A(rotation=90)) == "rotated by 90°"
    assert cleanup.describe(A(straighten=True, angle=2.04)) == "straightened (+2.0°)"
    assert cleanup.describe(A()) == "unchanged" == cleanup.describe(A(), "xx")
    assert cleanup.describe(A(straighten=True, angle=2.04), "de") == "begradigt (+2,0°)"
    assert cleanup.describe(A(straighten=True, angle=0.01), "de") == "unverändert"
    assert cleanup.describe(A(unwarp=True), "de") == "unverändert"  # no corners, nothing to unwarp
    high = A(upscale=3, letter_mode=True)
    assert cleanup.describe(high, "de") == "3× hochskaliert (Buchstabenmodus)"
    black = A(masks=[(0, 0, 1, 1)], mask_colour="black")
    assert cleanup.describe(black, "de") == "1 Bereich(e) geschwärzt"
    everything = A(rotation=180, straighten=True, angle=-1.5, borders=True, remove_colour=True,
              denoise=True, contrast=True, sharpen=True, background=True,
              remove_lines=True, black_white=True, masks=[(0, 0, 1, 1), (2, 2, 3, 3)])
    assert cleanup.describe(everything, "de") == (
        "um 180° gedreht, begradigt (-1,5°), Ränder gesäubert, farbige Tinte entfernt, entrauscht, "
        "Kontrast angehoben, geschärft, Hintergrund geglättet, Linien entfernt, Schwarz-Weiß, "
        "2 Bereich(e) gelöscht")
