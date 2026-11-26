"""Invented letters for the test bench of areas: text, and around it a logo, a picture,
a stamp, handwriting (a signature, a note) and barcodes, each where the truth file says.

    uv run python bench/area_letters.py <folder> [count] [seed]

writes ``letter-01.pdf`` … and next to each ``letter-01.areas.json``: a list of the
areas drawn, each ``{"kind", "box": [left, top, right, bottom]}`` in points from the
top left of the page, a barcode also with its ``format`` and ``content``.  Everything
here is made up: the practice, the patient, the codes.  Needs NumPy, OpenCV and
zxing-cpp (the extras "ocr" and "barcodes").
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import pymupdf

WIDTH, HEIGHT = 595, 842
TEXT = [
    "Sehr geehrte Frau Kollegin,",
    "",
    "wir berichten über Herrn Gotthard Beispiel, geb. 21.07.1959, der sich am 12.03.2026",
    "in unserer Sprechstunde vorstellte. Die Beschwerden bestehen seit etwa einem Jahr.",
    "Diagnosen: Leichte kognitive Störung, arterielle Hypertonie.",
    "Medikation: Ramipril 5 mg 1-0-0, Atorvastatin 20 mg 0-0-1.",
    "Befund: MMST 26/30, MoCA 22/30, Uhrentest unauffällig.",
    "Kontrolle in sechs Monaten empfohlen.",
    "",
    "Mit freundlichen kollegialen Grüßen",
]


def _placed(page: pymupdf.Page, rect: pymupdf.Rect, png: bytes) -> pymupdf.Rect:
    """Put an image into ``rect`` (keeping its proportions, centred) and return the
    rectangle it covers."""
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    h, w = image.shape[:2]
    f = min(rect.width / w, rect.height / h)
    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    placed = pymupdf.Rect(cx - w * f / 2, cy - h * f / 2, cx + w * f / 2, cy + h * f / 2)
    page.insert_image(placed, stream=png)
    if image.ndim == 3 and image.shape[2] == 4:  # only what is drawn, not the clear margin
        ys, xs = np.nonzero(image[:, :, 3])
        return pymupdf.Rect(placed.x0 + xs.min() * f, placed.y0 + ys.min() * f,
                            placed.x0 + (xs.max() + 1) * f, placed.y0 + (ys.max() + 1) * f)
    return placed


def _png(image) -> bytes:  # type: ignore[no-untyped-def]
    import cv2

    ok, data = cv2.imencode(".png", image)
    assert ok
    return bytes(data)


def _logo(rng: random.Random, size: int = 240) -> bytes:
    """A logo: coloured shapes on transparent ground."""
    import cv2
    import numpy as np

    image = np.zeros((size, size, 4), np.uint8)
    colours = [(180, 90, 20), (40, 140, 220), (60, 170, 60), (30, 30, 200)]
    rng.shuffle(colours)
    cv2.circle(image, (size // 3, size // 2), size // 4, (*colours[0], 255), -1)
    cv2.rectangle(image, (size // 2, size // 5), (size - 20, size * 4 // 5), (*colours[1], 255), -1)
    for k in range(3):
        y = size // 4 + k * size // 6
        cv2.line(image, (size // 2 + 15, y), (size - 35, y), (255, 255, 255, 255), 9)
    return _png(image)


def _picture(rng: random.Random, w: int = 420, h: int = 300) -> bytes:
    """A photo-like picture: soft colour clouds with grain."""
    import cv2
    import numpy as np

    g = np.random.default_rng(rng.randrange(1 << 30))
    noise = g.normal(0, 1, (h // 10, w // 10, 3)).astype(np.float32)
    image = cv2.resize(noise, (w, h), interpolation=cv2.INTER_CUBIC)
    image = cv2.GaussianBlur(image, (0, 0), 6)
    image = (image - image.min()) / (image.max() - image.min() + 1e-6)
    image = 40 + 180 * image + g.normal(0, 6, image.shape)
    return _png(np.clip(image, 0, 255).astype(np.uint8))


def _barcode(fmt: str, content: str, scale: int = 6) -> bytes:
    """A barcode image of ``content`` (zxing-cpp writes it)."""
    import numpy as np
    import zxingcpp

    barcode = zxingcpp.create_barcode(content, getattr(zxingcpp.BarcodeFormat, fmt))
    # without quiet zones: the paper around it is one, and the truth box holds the code alone
    image = np.array(zxingcpp.write_barcode_to_image(barcode, scale=scale, add_hrt=False,
                                                     add_quiet_zones=False))
    return _png(image)


def _ean13(rng: random.Random) -> str:
    """An invented EAN-13 with its check digit (prefix 200-299: for use within a store)."""
    digits = [2, rng.randint(0, 9), rng.randint(0, 9)] + [rng.randint(0, 9) for _ in range(9)]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits))
    return "".join(map(str, digits)) + str((10 - total % 10) % 10)


def _codes(rng: random.Random, number: int) -> list[tuple[str, str]]:
    """Invented contents for every format that letters and labels carry."""
    return [
        ("QRCode", f"https://befunde.example/abruf/{rng.randrange(10**8):08d}"),
        ("DataMatrix", f'<MP v="026" U="{rng.randrange(16**8):08X}"><P g="Gotthard" f="Beispiel"'
                       f' b="19590721"/><S><M p="{rng.randrange(10**7):07d}" m="1"/></S></MP>'),
        ("Code128", f"LAB-2026-{4700 + number:04d}"),
        ("EAN13", _ean13(rng)),
        ("PDF417", f"Probe {rng.randrange(10**6):06d} / Beispiel, Gotthard"),
    ]


def _stamp(page: pymupdf.Page, rng: random.Random, box: pymupdf.Rect) -> pymupdf.Rect:
    """A coloured practice stamp, slightly turned and see-through, over ``box``; returns
    the box it covers."""
    colour = rng.choice([(0.15, 0.25, 0.75), (0.45, 0.2, 0.65), (0.8, 0.1, 0.15)])
    angle = rng.uniform(-8, 8)
    centre = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    turn = pymupdf.Matrix(angle)
    lines = ["Praxis Dr. med. Erika Beispiel", "Fachärztin für Neurologie",
             "Musterweg 1 · 00000 Beispielstadt", "Tel. 089 99998111"]
    w, h = box.width, box.height
    corners = [pymupdf.Point(centre[0] + dx, centre[1] + dy)
               for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
    turned = [(p - centre) * turn + centre for p in corners]
    shape = page.new_shape()
    shape.draw_polyline([*turned, turned[0]])
    shape.finish(color=colour, width=1.6, stroke_opacity=0.85, closePath=True)
    shape.commit()
    for k, text in enumerate(lines):
        size = 9 if k == 0 else 7.5
        at = pymupdf.Point(box.x0 + 8, box.y0 + 16 + k * 12)
        page.insert_text(at, text, fontsize=size, fontname="helv", color=colour,
                         fill_opacity=0.85, morph=(pymupdf.Point(*centre), turn))
    xs, ys = [p.x for p in turned], [p.y for p in turned]
    return pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))


def _handwriting(page: pymupdf.Page, rng: random.Random, box: pymupdf.Rect) -> pymupdf.Rect:
    """Cursive-like writing in pen ink within ``box``: words of looped letters, small and
    tall ones, slanted, on a slightly wavy base line; returns the box of the ink."""
    colour = rng.choice([(0.05, 0.1, 0.45), (0.1, 0.1, 0.1)])
    width = rng.uniform(0.9, 1.4)
    slant = rng.uniform(0.15, 0.35)
    small = box.height * rng.uniform(0.22, 0.3)
    base = box.y0 + box.height * 0.68
    x = box.x0 + 3
    xs: list[float] = []
    ys: list[float] = []
    while x < box.x1 - 25:
        points = []
        for _letter in range(rng.randint(3, 7)):
            tall = rng.random() < 0.3
            h = small * (2.2 if tall else 1.0) * rng.uniform(0.85, 1.15)
            w = small * rng.uniform(0.7, 1.1)
            for k in range(21):  # one loop: up to the left, over, down to the right
                theta = 2 * math.pi * k / 20
                px = x + w * theta / (2 * math.pi) - 0.35 * w * math.sin(theta)
                py = base - h * (1 - math.cos(theta)) / 2 + 0.4 * rng.uniform(-1, 1)
                points.append(pymupdf.Point(px + slant * (base - py), py))
            x += w
        shape = page.new_shape()
        shape.draw_polyline(points)
        shape.finish(color=colour, width=width, lineCap=1, lineJoin=1, closePath=False)
        shape.commit()
        xs += [pt.x for pt in points]
        ys += [pt.y for pt in points]
        x += rng.uniform(6, 12)  # the gap between words
        base += rng.uniform(-1.2, 1.2)
    return pymupdf.Rect(min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)


def make(folder: Path, count: int = 6, seed: int = 1) -> list[Path]:
    """Write ``count`` letters with their area files; returns the PDFs."""
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    made = []
    for number in range(1, count + 1):
        doc = pymupdf.open()
        page = doc.new_page(width=WIDTH, height=HEIGHT)
        areas: list[dict] = []
        y = 58
        for text, size in (("Neurologische Sprechstunde am Stadtpark", 13),
                           ("Dr. med. Erika Beispiel · Musterweg 1 · 00000 Beispielstadt", 8.5)):
            page.insert_text((56, y), text, fontsize=size, fontname="helv")
            y += size + 7
        logo = _placed(page, pymupdf.Rect(470, 34, 540, 104), _logo(rng))
        areas.append({"kind": "image", "box": list(logo)})
        y = 150
        for line in ("Frau Dr. med. Wiebke Zander", "Lindenallee 4", "00000 Beispielstadt"):
            page.insert_text((56, y), line, fontsize=10, fontname="helv")
            y += 14
        y = 230
        for line in TEXT:
            if line:
                page.insert_text((56, y), line, fontsize=10, fontname="helv")
            y += 15
        codes = _codes(rng, number)
        rng.shuffle(codes)
        # the right column beside the address: a two-dimensional code
        fmt, content = next(c for c in codes if c[0] in ("QRCode", "DataMatrix"))
        side = 64 if fmt == "DataMatrix" else 70
        square = _placed(page, pymupdf.Rect(470, 140, 470 + side, 140 + side),
                         _barcode(fmt, content))
        areas.append({"kind": "barcode", "box": list(square), "format": fmt, "content": content})
        # the foot: signature, stamp, a picture, more codes
        top = y + 10
        sign = _handwriting(page, rng, pymupdf.Rect(60, top, 230, top + 40))
        areas.append({"kind": "handwriting", "box": list(sign)})
        stamp = _stamp(page, rng, pymupdf.Rect(250, top - 5, 440, top + 55))
        areas.append({"kind": "stamp", "box": list(stamp)})
        picture = _placed(page, pymupdf.Rect(56, top + 80, 236, top + 80 + rng.uniform(100, 130)),
                          _picture(rng))
        areas.append({"kind": "image", "box": list(picture)})
        x = 260
        for fmt, content in (c for c in codes if c[0] not in ("QRCode", "DataMatrix")
                             or c[1] != content):
            if fmt in ("QRCode", "DataMatrix"):
                w = h = 62
            elif fmt == "PDF417":
                w, h = 150, 45
            else:
                w, h = 130, 40
            if x + w > WIDTH - 50:
                break
            box = _placed(page, pymupdf.Rect(x, top + 85, x + w, top + 85 + h),
                          _barcode(fmt, content))
            areas.append({"kind": "barcode", "box": list(box), "format": fmt, "content": content})
            x += w + 18
        note = pymupdf.Rect(300, top + 160, 520, top + 190)
        areas.append({"kind": "handwriting", "box": list(_handwriting(page, rng, note))})
        stem = f"letter-{number:02d}"
        pdf = folder / f"{stem}.pdf"
        doc.save(pdf)
        doc.close()
        for a in areas:
            a["box"] = [round(v, 1) for v in a["box"]]
        (folder / f"{stem}.areas.json").write_text(json.dumps(areas, ensure_ascii=False, indent=1)
                                                   + "\n", encoding="utf-8")
        made.append(pdf)
    return made


if __name__ == "__main__":
    target = Path(sys.argv[1])
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    for path in make(target, count, seed):
        print(path.name)
