"""Open PDFs and images as a PyMuPDF document, every page upright.

A page turned by ``/Rotate`` (as medRDS binds a photo taken with the phone on its side)
is set upright without touching its content: the picture stays byte for byte, only the
page's matrix changes.  So the words of a reading, the boxes in page points and the
pages of the output PDF all mean the page as it is shown.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf

from optdoc.errors import OptdocError

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
        raise OptdocError("paper", name=str(name))
    return PAPER_SIZES[key]


def open_document(path: str | Path, paper: str | None = "a4") -> pymupdf.Document:
    """Open a PDF, or an image as a PDF: each image page goes on a sheet of the chosen
    paper size (portrait or landscape following the image, scaled to fit, centred),
    with ``paper="image"`` on a page exactly as large as the image.

    HEIC/HEIF photos need the optional ``ocr`` extra (pillow-heif).  Raises
    :class:`~optdoc.errors.OptdocError`: "missing", "unsupported", "no-heic",
    "unreadable", "encrypted", "paper".
    """
    path = Path(path)
    extension = path.suffix.lower()
    if not path.is_file():
        raise OptdocError("missing")
    if extension not in IMAGE_SUFFIXES | HEIC_SUFFIXES | {".pdf"}:
        raise OptdocError("unsupported", suffix=extension or "(none)")
    paper_size(paper)  # an unknown name fails before the work
    try:
        if extension == ".pdf":
            return _upright(_pdf(path))
        if extension in HEIC_SUFFIXES:
            return _heic(path, paper)
        image = pymupdf.open(path)
        try:
            return _on_paper(image, paper)
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


def _on_paper(image: pymupdf.Document, paper: str | None) -> pymupdf.Document:
    """The pages of an image document as a PDF on the chosen paper.  The image keeps
    its bytes and its EXIF orientation (the image document already applied it); it is
    placed as a form on the sheet, which the redaction of image pixels reaches."""
    format_ = paper_size(paper)
    source = pymupdf.open("pdf", image.convert_to_pdf())
    if format_ is None:
        return source
    doc = pymupdf.open()
    for i, sheet in enumerate(source.pages()):
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
        raise OptdocError("no-heic") from e
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
