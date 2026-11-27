"""Open PDFs and pictures as a PyMuPDF document, every page upright.

A page turned by ``/Rotate`` (as medRDS binds a photo taken with the phone on its side)
is set upright without touching its content: the picture stays byte for byte, only the
page's matrix changes.  So the boxes in page points and the pages of the output all mean
the page as it is shown.

A picture is looked at as a page as well, to work on it; it stays a picture (what is
written is :mod:`optdoc.pictures`' business).  Its page is as the standard medRDS binds a
picture into a PDF (9.5, what typdoc does): upright as its EXIF orientation says, its long
side that of A4.  So optdoc sees the same page, and a plan means the same, whether it is
handed the picture itself or the PDF typdoc bound it into.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf

from optdoc.errors import OptdocError

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".pnm"}
HEIC_SUFFIXES = {".heic", ".heif"}
LONG_SIDE = 842.0  # points: the long side of A4, as medRDS 9.5 binds a picture


def is_picture(path: str | Path) -> bool:
    """True for a file whose type is a picture's (by its name)."""
    return Path(path).suffix.lower() in IMAGE_SUFFIXES | HEIC_SUFFIXES


def open_document(path: str | Path) -> pymupdf.Document:
    """Open a PDF, or a picture as pages to work on (one for each picture in the file):
    upright, the long side that of A4.

    HEIC and HEIF photos need pillow-heif (the extra "cleanup").  Raises
    :class:`~optdoc.errors.OptdocError`: "missing", "unsupported", "no-heic",
    "unreadable", "encrypted".
    """
    path = Path(path)
    extension = path.suffix.lower()
    if not path.is_file():
        raise OptdocError("missing")
    if extension not in IMAGE_SUFFIXES | HEIC_SUFFIXES | {".pdf"}:
        raise OptdocError("unsupported", suffix=extension or "(none)")
    try:
        if extension == ".pdf":
            return _upright(_pdf(path))
        if extension not in (".jpg", ".jpeg"):
            return _decoded(path)
        image = pymupdf.open(path)  # a JPEG is looked at as it is, upright by its EXIF
        try:
            doc = pymupdf.open()
            _add_pages(doc, image)
            return _finished(doc)
        finally:
            image.close()
    except OptdocError:
        raise
    except Exception as e:  # MuPDF and Pillow word their failures with the file's name
        raise OptdocError("unreadable") from e


def _pdf(path: Path) -> pymupdf.Document:
    """A PDF, refused when it needs a password or has no pages."""
    doc = pymupdf.open(path)
    if doc.needs_pass:
        doc.close()
        raise OptdocError("encrypted")
    if doc.page_count == 0:
        doc.close()
        raise OptdocError("unreadable")
    return doc


def _upright(doc: pymupdf.Document) -> pymupdf.Document:
    """Every page of ``doc`` set upright: ``/Rotate`` taken into the page's content, which
    looks and holds the same."""
    for page in doc.pages():
        if page.rotation:
            page.remove_rotation()
    return doc


def _add_pages(doc: pymupdf.Document, image: pymupdf.Document) -> None:
    """Add the pictures of an image document to ``doc`` as pages: each fills its page,
    whose long side is that of A4."""
    source = pymupdf.open("pdf", image.convert_to_pdf())
    try:
        for i, sheet in enumerate(source.pages()):
            scale = LONG_SIDE / max(sheet.rect.width, sheet.rect.height)
            page = doc.new_page(width=round(sheet.rect.width * scale, 2),
                                height=round(sheet.rect.height * scale, 2))
            page.show_pdf_page(page.rect, source, i)
    finally:
        source.close()


def _finished(doc: pymupdf.Document) -> pymupdf.Document:
    """The pages as a document of their own, independent of what they were made from."""
    result = pymupdf.open("pdf", doc.tobytes())
    doc.close()
    return result


def _decoded(path: Path) -> pymupdf.Document:
    """A picture that is no JPEG (PNG, TIFF, HEIC, WebP …), decoded by Pillow: every
    picture in the file a page, upright as its orientation says, what is transparent on
    white.  These are the pixels :mod:`optdoc.pictures` prepares, so the page and the
    picture always agree."""
    from PIL import Image, ImageOps

    if path.suffix.lower() in HEIC_SUFFIXES:
        try:
            import pillow_heif
        except ImportError as e:
            raise OptdocError("no-heic") from e
        pillow_heif.register_heif_opener()
    doc = pymupdf.open()
    with Image.open(path) as image:
        for n in range(getattr(image, "n_frames", 1)):
            image.seek(n)
            upright = ImageOps.exif_transpose(image)
            if upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info:
                rgba = upright.convert("RGBA")
                white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                upright = Image.alpha_composite(white, rgba)
            buffer = io.BytesIO()
            upright.convert("RGB").save(buffer, format="PNG", compress_level=1)
            between = pymupdf.open("png", buffer.getvalue())
            try:
                _add_pages(doc, between)
            finally:
                between.close()
    return _finished(doc)
