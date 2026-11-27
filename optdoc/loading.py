"""Open PDFs and pictures as a PyMuPDF document, every page upright.

A page turned by ``/Rotate`` (as medRDS binds a photo taken with the phone on its side)
is set upright without touching its content: the picture stays byte for byte, only the
page's matrix changes.  So the boxes in page points and the pages of the output all mean
the page as it is shown.

A picture is looked at as a page as well, to work on it; it stays a picture (what is
written is :mod:`optdoc.pictures`' business).  Its page is as the standard medRDS binds a
picture into a PDF (9.5, what typdoc does): upright as its EXIF orientation says, its long
side that of A4.  So optdoc sees the same page, and a plan means the same, whether it is
handed the picture itself or the PDF typdoc bound it into.  The page of a picture is the
same in every tool of docrepro: it is doccor's (:mod:`doccor.pictures`).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from doccor import pictures as view
from doccor.pictures import LONG_SIDE, is_picture

from optdoc.errors import OptdocError


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
    if extension != ".pdf" and not is_picture(path):
        raise OptdocError("unsupported", suffix=extension or "(none)")
    try:
        if extension == ".pdf":
            return _upright(_pdf(path))
        return view.pages(path)
    except OptdocError:
        raise
    except view.NoHeic as e:
        raise OptdocError("no-heic") from e
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


__all__ = ["LONG_SIDE", "is_picture", "open_document"]
