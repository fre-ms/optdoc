"""Invented documents for the tests: a two-page report and its scans.

Every name, number and address here is made up.
"""

from __future__ import annotations

import io
import random
from pathlib import Path

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
