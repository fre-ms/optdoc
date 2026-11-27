"""A picture is looked at as a page: upright as its EXIF orientation says, its long side
that of A4 (as medRDS binds a picture into a PDF), one page for each picture in the file."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest

from optdoc.errors import OptdocError
from optdoc.loading import LONG_SIDE, is_picture, open_document


def _picture(path: Path, width: int, height: int, **options: object) -> Path:
    from PIL import Image

    Image.new("RGB", (width, height), (255, 255, 255)).save(path, **options)
    return path


def test_a_picture_as_a_page(tmp_path: Path) -> None:
    landscape = _picture(tmp_path / "quer.png", 1000, 500)
    portrait = _picture(tmp_path / "hoch.jpg", 420, 594)
    with open_document(landscape) as doc:  # the picture fills its page
        page = doc[0]
        assert (round(page.rect.width, 2), round(page.rect.height, 2)) == (LONG_SIDE, 421.0)
        bbox = pymupdf.Rect(page.get_image_info()[0]["bbox"])
        assert abs(bbox.width - 842) < 0.1 and abs(bbox.height - 421) < 0.1
    with open_document(portrait) as doc:  # the page typdoc binds this picture into
        assert (round(doc[0].rect.width, 2), round(doc[0].rect.height, 2)) == (595.35, 842.0)
    assert is_picture(portrait) and is_picture("FOTO.HEIC") and not is_picture("scan.pdf")


def test_a_picture_held_turned_stands_upright(tmp_path: Path) -> None:
    """A camera writes the pixels as its sensor lay and says how it was held: the page is
    as the picture is meant to be seen."""
    from PIL import Image

    exif = Image.Exif()
    exif[0x0112] = 6  # held turned: the picture is a portrait
    turned = _picture(tmp_path / "gedreht.jpg", 600, 400, exif=exif.tobytes())
    with open_document(turned) as doc:
        assert round(doc[0].rect.height, 2) == LONG_SIDE and doc[0].rect.width < LONG_SIDE
    buffer = io.BytesIO()
    Image.new("RGB", (600, 400), (255, 255, 255)).save(buffer, format="PNG")
    plain = tmp_path / "liegend.png"
    plain.write_bytes(buffer.getvalue())
    with open_document(plain) as doc:
        assert round(doc[0].rect.width, 2) == LONG_SIDE


def test_every_picture_of_a_file_is_a_page(tmp_path: Path) -> None:
    from PIL import Image

    pages = tmp_path / "zwei.tiff"
    Image.new("RGB", (400, 600), (255, 255, 255)).save(
        pages, save_all=True, append_images=[Image.new("RGB", (600, 400), (255, 255, 255))])
    with open_document(pages) as doc:
        assert [(round(p.rect.width, 2), round(p.rect.height, 2)) for p in doc] == [
            (561.33, 842.0), (842.0, 561.33)]


def test_what_cannot_be_opened(tmp_path: Path) -> None:
    word = tmp_path / "brief.docx"
    word.write_bytes(b"PK")
    text = tmp_path / "text.png"
    text.write_bytes(b"kein Bild")
    for path, kind in ((tmp_path / "fehlt.jpg", "missing"), (word, "unsupported"),
                       (text, "unreadable")):
        with pytest.raises(OptdocError) as caught:
            open_document(path)
        assert caught.value.kind == kind
