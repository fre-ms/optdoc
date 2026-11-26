"""Invented documents for the tests: a two-page report and its scans.

Every name, number and address here is made up.
"""

from __future__ import annotations

import importlib.util
import io
import random
from pathlib import Path
from types import ModuleType
from typing import Any

import pymupdf

REPORT_TEXT: list[list[str]] = [
    [
        "Neurologische Gemeinschaftspraxis am Stadtpark",
        "Dr. med. Erika Beispiel · Fachärztin für Neurologie",
        "Praxis Dr. med. Wiebke Zander",
        "Lindenallee 4",
        "",
        "Betr.: Herrn Gotthard Flantz, geb. 21.07.1959",
        "Am Mühlgraben 12, 01591 Riesa",
        "Tel. 089 99998123, E-Mail gotthard.flantz@example.org",
        "Versicherten-Nr. Q123456782   Pat.-ID 48213   AZ 2026/171",
        "",
        "Sehr geehrte Frau Kollegin Zander,",
        "",
        "vielen Dank für die Überweisung von Herrn Flantz, der sich am 12.03.2026",
        "erstmals in unserer Sprechstunde vorstellte. Die Anamnese wurde gemeinsam mit",
        "der Ehefrau, Frau Hildegund Flantz, erhoben.",
        "",
        "Diagnosen: Leichte kognitive Störung (ICD-10 F06.7), arterielle Hypertonie.",
        "Medikation: Ramipril 5 mg 1-0-0, Atorvastatin 20 mg 0-0-1, max. 3 Tabletten.",
        "Befund: MMST 26/30, MoCA 22/30, Uhrentest unauffällig.",
    ],
    [
        "Fortsetzung Befund FLANTZ, GOTTHARD (*21.07.59)",
        "",
        "Die Beschwerden bestehen seit etwa einem Jahr. Geboren am 21. Juli 1959",
        "in Riesa. Flantz, Gotthard berichtet über Wortfindungsstörungen.",
        "Im Verlauf zeigt Herr G. Flantz",
        "eine stabile Befundlage. Kontrolle in 6 Monaten empfohlen.",
        "",
        "Mit freundlichen kollegialen Grüßen",
        "Dr. med. Erika Beispiel",
    ],
]


def _lab_reports() -> ModuleType:
    """The bench's generator of invented laboratory reports (``bench/lab_reports.py``)."""
    spec = importlib.util.spec_from_file_location(
        "lab_reports", Path(__file__).resolve().parents[1] / "bench" / "lab_reports.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def colour_scan(source: Path, target: Path, dpi: int = 200, rotation: float = 1.0,
                seed: int = 1) -> Path:
    """An image-only PDF of a page scanned in colour: turned a little, with grain and a
    few specks, stored as JPEG.  Needs OpenCV and NumPy."""
    import cv2
    import numpy as np

    with pymupdf.open(source) as d:
        pix = d[0].get_pixmap(dpi=dpi, alpha=False)
        width, height = d[0].rect.width, d[0].rect.height
    image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)[:, :, ::-1]
    turn = cv2.getRotationMatrix2D((pix.width / 2, pix.height / 2), rotation, 1.0)
    image = cv2.warpAffine(np.ascontiguousarray(image), turn, (pix.width, pix.height),
                           borderValue=(255, 255, 255))
    rng = np.random.default_rng(seed)
    image = np.clip(image.astype(np.float32) + rng.normal(0, 4, image.shape), 0, 255)
    image = image.astype(np.uint8)
    image[rng.random(image.shape[:2]) < 0.003] = 0
    ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=bytes(jpeg))
    doc.save(target)
    doc.close()
    return target


def lab_report(folder: Path, number: int = 1) -> tuple[Path, list[str]]:
    """The bench's invented laboratory report ``number`` (1: a ruled grid, 2: open columns,
    3: two blocks with a flag column) as a PDF, and its truth lines, one per result."""
    pdf = _lab_reports().make(folder, number)[number - 1]
    lines = pdf.with_name(pdf.stem + ".truth.txt").read_text(encoding="utf-8").splitlines()
    return pdf, [z for z in lines if z.strip() and not z.startswith("#")]


def make_report(path: Path) -> Path:
    """The report as a PDF with a text layer."""
    doc = pymupdf.open()
    for lines in REPORT_TEXT:
        page = doc.new_page()
        y = 72.0
        for line in lines:
            page.insert_text((56, y), line, fontsize=10.5, fontname="helv")
            y += 14.5
    doc.save(path, garbage=0)
    doc.close()
    return path


def rasterise(doc: pymupdf.Document, dpi: int = 200) -> pymupdf.Document:
    """A new document whose pages are plain images of the given one."""
    new = pymupdf.open()
    for page in doc:
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        sheet = new.new_page(width=page.rect.width, height=page.rect.height)
        sheet.insert_image(sheet.rect, pixmap=pix)
    return new


def photograph(source: Path, target: Path, page: int = 0, dpi: int = 150,
               orientation: int = 1, desk: tuple[int, int, int] = (55, 65, 80),
               seed: int = 1) -> Path:
    """A phone photo of a printed page, as JPEG: the page lies on a dark desk, seen at a
    slant (each corner moved by up to 4 % of the side), lit unevenly.  ``orientation`` is
    the EXIF orientation: 6 stores the pixels turned a quarter anticlockwise and asks the
    viewer to turn them back, as a phone held upright does; 3 stores them upside down.
    Needs OpenCV, NumPy and Pillow (the ``ocr`` extra)."""
    import cv2
    import numpy as np
    from PIL import Image

    with pymupdf.open(source) as d:
        pix = d[page].get_pixmap(dpi=dpi, alpha=False)
    sheet = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    h, w = sheet.shape[:2]
    margin = int(0.12 * max(h, w))
    rng = random.Random(seed)
    jitter = [(rng.uniform(0, 0.04) * w, rng.uniform(0, 0.04) * h) for _ in range(4)]
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    signs = ((1, 1), (-1, 1), (-1, -1), (1, -1))
    placed = np.float32([[x + margin + sx * dx, y + margin + sy * dy]
                         for (x, y), (sx, sy), (dx, dy) in zip(corners, signs, jitter,
                                                               strict=True)])
    size = (w + 2 * margin, h + 2 * margin)
    photo = np.empty((size[1], size[0], 3), dtype=np.uint8)
    photo[:] = desk
    m = cv2.getPerspectiveTransform(corners, placed)
    cv2.warpPerspective(sheet, m, size, dst=photo, borderMode=cv2.BORDER_TRANSPARENT)
    yy, xx = np.mgrid[0:size[1], 0:size[0]]
    light = 1.0 - 0.25 * (xx / size[0]) * (yy / size[1])  # darker towards one corner
    photo = np.clip(photo * light[:, :, None], 0, 255).astype(np.uint8)
    image = Image.fromarray(photo)
    stored = {1: image, 3: image.rotate(180), 6: image.rotate(90, expand=True),
              8: image.rotate(-90, expand=True)}[orientation]
    exif = Image.Exif()
    exif[0x0112] = orientation
    stored.save(target, format="JPEG", quality=88, exif=exif)
    return target


_TURN = {1: 0, 3: 180, 6: 90, 8: 270}  # EXIF orientation -> /Rotate, as medRDS binds pictures


def bind(photos: list[Path], target: Path) -> Path:
    """Photos bound into one PDF the way medRDS ``bindPictures`` does it: each JPEG is the
    image of its page byte for byte, the page as large as the stored pixels (long side
    842 pt) and turned by ``/Rotate`` as the photo's EXIF orientation says."""
    from PIL import Image

    doc = pymupdf.open()
    for photo in photos:
        with Image.open(photo) as image:
            width, height = image.size
            orientation = image.getexif().get(0x0112, 1)
        scale = 842 / max(width, height)
        page = doc.new_page(width=width * scale, height=height * scale)
        page.insert_image(page.rect, stream=photo.read_bytes())
        page.set_rotation(_TURN[orientation])
    doc.save(target)
    doc.close()
    return target


def scan(report: Path, target: Path, dpi: int = 200, noise: float = 0.0,
         rotation: float = 0.0) -> Path:
    """Image-only PDF of a document, optionally with salt-and-pepper noise and a tilt
    (PIL rotates counter-clockwise, so the right ``angle`` is ``-rotation``)."""
    with pymupdf.open(report) as d:
        images = rasterise(d, dpi=dpi)
    if noise or rotation:
        from PIL import Image

        new = pymupdf.open()
        rng = random.Random(1)
        for page in images:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
            px = image.load()
            if noise:
                for _ in range(int(noise * image.width * image.height)):
                    xy = rng.randrange(image.width), rng.randrange(image.height)
                    px[xy] = rng.choice((0, 255))
            if rotation:
                image = image.rotate(rotation, expand=False, fillcolor=255)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            sheet = new.new_page(width=page.rect.width, height=page.rect.height)
            sheet.insert_image(sheet.rect, stream=buffer.getvalue())
        images.close()
        images = new
    images.save(target)
    images.close()
    return target


def camera_photo(source: Path, pitch: float, yaw: float = 0.0, roll: float = 0.0,
                 fill: float = 0.8, desk: str = "dark", shift: tuple[float, float] = (0, 0),
                 size: tuple[int, int] = (1200, 1600), dpi: int = 110) -> tuple[Any, Any]:
    """A phone photo of the first page of ``source`` as a BGR image, taken by a pinhole
    camera with a phone's focal length (26 mm in 35 mm terms, principal point in the
    middle) turned by ``pitch``, ``yaw`` and ``roll`` degrees, at a distance where the
    sheet's height is ``fill`` of the photo's (above 1 the sheet runs out of it);
    ``shift`` moves the sheet off the camera's axis (millimetres).  ``desk`` is "dark"
    or "light" (a light grey table).  Returns the image and the true corners of the
    sheet in its pixels (top-left, top-right, bottom-right, bottom-left), which may lie
    outside it.  Needs OpenCV and NumPy."""
    import math

    import cv2
    import numpy as np

    w, h = size
    focal = 26 / 43.27 * math.hypot(w, h)
    p, y, r = (math.radians(v) for v in (pitch, yaw, roll))
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]])
    turn = rz @ ry @ rx
    sheet_mm = np.array([[-105, -148.5, 0], [105, -148.5, 0], [105, 148.5, 0], [-105, 148.5, 0]])

    def project(distance: float) -> Any:
        points = (turn @ sheet_mm.T).T + [shift[0], shift[1], distance]
        return np.c_[focal * points[:, 0] / points[:, 2] + w / 2,
                     focal * points[:, 1] / points[:, 2] + h / 2]

    distance = 400.0
    for _ in range(30):
        corners = project(distance)
        distance *= (corners[:, 1].max() - corners[:, 1].min()) / (fill * h)
    corners = project(distance)
    with pymupdf.open(source) as d:
        pix = d[0].get_pixmap(dpi=dpi, alpha=False)
    page = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)[:, :, ::-1]
    m = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [pix.width, 0], [pix.width, pix.height], [0, pix.height]]),
        np.float32(corners))
    photo = np.full((h, w, 3), (55, 65, 80) if desk == "dark" else (212, 214, 218), np.float32)
    warped = cv2.warpPerspective(np.ascontiguousarray(page).astype(np.float32), m, (w, h),
                                 flags=cv2.INTER_AREA, borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(-1, -1, -1))
    on_sheet = warped[:, :, 0] >= 0
    photo[on_sheet] = warped[on_sheet]
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 1.0 - 0.2 * np.hypot(xx, yy) / math.hypot(w, h)  # darker towards one corner
    photo = cv2.GaussianBlur(photo * 0.96 * light[:, :, None], (0, 0), 0.8)
    photo = np.clip(photo + rng.normal(0, 3.0, photo.shape), 0, 255).astype(np.uint8)
    return photo, corners
