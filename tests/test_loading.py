"""Images are opened on a sheet of paper: size, orientation, centring, "bild"."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from optdoc.errors import OptdocError
from optdoc.loading import PAPER_SIZES, open_document, paper_size


def _image(path: Path, width: int, height: int) -> Path:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pix.clear_with(255)
    pix.save(path)
    return path


def test_paper_size_names() -> None:
    assert paper_size("A4") == PAPER_SIZES["a4"] and paper_size(None) == PAPER_SIZES["a4"]
    assert paper_size("US Letter") == PAPER_SIZES["letter"] and paper_size("image") is None
    with pytest.raises(OptdocError, match="paper size") as caught:
        paper_size("b5")
    assert caught.value.kind == "paper" and caught.value.details == {"name": "b5"}


def test_image_on_paper(tmp_path: Path) -> None:
    landscape = _image(tmp_path / "quer.png", 1000, 500)
    portrait = _image(tmp_path / "hoch.png", 500, 1000)
    with open_document(landscape) as doc:  # A4 landscape, image fitted and centred
        page = doc[0]
        assert (round(page.rect.width), round(page.rect.height)) == (842, 595)
        bbox = pymupdf.Rect(page.get_image_info()[0]["bbox"])
        assert abs(bbox.width - 842) < 1 and abs(bbox.height - 421) < 1
        assert abs(bbox.y0 - (595 - 421) / 2) < 1
    with open_document(portrait, "letter") as doc:
        assert (round(doc[0].rect.width), round(doc[0].rect.height)) == (612, 792)
    # as large as the image
    with open_document(portrait, "image") as doc, pymupdf.open(portrait) as raw:
        assert doc[0].rect == raw[0].rect and doc[0].rect.height == 2 * doc[0].rect.width
    with pytest.raises(OptdocError):
        open_document(portrait, "b5")
