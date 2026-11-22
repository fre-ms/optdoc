"""Open PDFs and images as a PyMuPDF document."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".pnm"}
HEIC_SUFFIXES = {".heic", ".heif"}

# page sizes in points for photos and images; "image" keeps the page as large as the image
PAPER_SIZES: dict[str, tuple[float, float] | None] = {
    "a4": (595.276, 841.89),
    "a5": (419.528, 595.276),
    "a3": (841.89, 1190.551),
    "letter": (612.0, 792.0),
    "legal": (612.0, 1008.0),
    "image": None,
}


def paper_size(name: str | None) -> tuple[float, float] | None:
    """Width and height in points (portrait) of a paper size name, None for "image"."""
    key = (name or "a4").lower().replace("-", "").replace(" ", "")
    key = {"usletter": "letter", "uslegal": "legal", "image": "image"}.get(key,
                                                                                 key)
    if key not in PAPER_SIZES:
        raise ValueError(f"unknown paper size: {name!r} ({', '.join(PAPER_SIZES)})")
    return PAPER_SIZES[key]


def open_document(path: str | Path, paper: str | None = "a4") -> pymupdf.Document:
    """Open a PDF, or an image as a PDF: each image page goes on a sheet of the chosen
    paper size (portrait or landscape following the image, scaled to fit, centred),
    with ``paper="image"`` on a page exactly as large as the image.

    HEIC/HEIF photos need the optional ``ocr`` extra (pillow-heif).
    """
    path = Path(path)
    extension = path.suffix.lower()
    if extension == ".pdf":
        return pymupdf.open(path)
    if extension in IMAGE_SUFFIXES:
        image = pymupdf.open(path)
        try:
            return _on_paper(image, paper)
        finally:
            image.close()
    if extension in HEIC_SUFFIXES:
        return _heic(path, paper)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _on_paper(image: pymupdf.Document, paper: str | None) -> pymupdf.Document:
    """The pages of an image document as a PDF on the chosen paper.  The image keeps
    its bytes and its EXIF orientation (the image document already applied it); it is
    placed as a form on the sheet, which the redaction of image pixels reaches."""
    format_ = paper_size(paper)
    source = pymupdf.open("pdf", image.convert_to_pdf())
    if format_ is None:
        return source
    doc = pymupdf.open()
    for i, sheet in enumerate(source):
        width, height = format_
        if sheet.rect.width > sheet.rect.height:
            width, height = height, width
        page = doc.new_page(width=width, height=height)
        page.show_pdf_page(page.rect, source, i)
    result = pymupdf.open("pdf", doc.tobytes())  # independent of the source
    doc.close()
    source.close()
    return result


def _heic(path: Path, paper: str | None = "a4") -> pymupdf.Document:
    """HEIC/HEIF photos: decode with pillow-heif (extra 'ocr'), honour the EXIF orientation."""
    try:
        import pillow_heif
        from PIL import Image, ImageOps
    except ImportError as e:
        raise NotImplementedError(
            "HEIC/HEIF photos need the extra 'ocr' (pillow-heif): uv sync --extra ocr"
        ) from e
    pillow_heif.register_heif_opener()
    with Image.open(path) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        buffer = io.BytesIO()
        rgb.save(buffer, format="PNG")
    between = pymupdf.open("png", buffer.getvalue())
    try:
        return _on_paper(between, paper)
    finally:
        between.close()
