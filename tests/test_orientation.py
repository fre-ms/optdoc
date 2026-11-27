"""Which way up a page stands: the model decides only when it is sure, by the middle of
the page or of what is written on it; without the model everything is as before; with it
(``OPTDOC_MODELS=<folder>``, after ``optdoc models fetch page-orientation``) a page on
its head is set upright in the suggestion, the configuration says that the model took
part, and the result is made again without it."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pymupdf
import pytest

from optdoc import cleanup, orientation, output
from optdoc import models as catalogue
from optdoc.cli import main
from optdoc.errors import OptdocError
from optdoc.project import Project, load_config
from tests.synthetic import scan

pytestmark = pytest.mark.skipif(not cleanup.available(), reason="needs OpenCV")
MODELS = Path(os.environ["OPTDOC_MODELS"]) if os.environ.get("OPTDOC_MODELS") else None
needs_model = pytest.mark.skipif(
    catalogue.orientation(MODELS) is None,
    reason="needs the orientation model (OPTDOC_MODELS=<folder>, optdoc models fetch)")


def _turned_scan(report: Path, target: Path) -> Path:
    """A scan whose first page stands on its head and whose second lies on its side
    (turned clockwise by 90 degrees)."""
    import cv2
    import numpy as np

    upright = scan(report, target.with_name("upright.pdf"), rotation=1.0)
    doc = pymupdf.open()
    with pymupdf.open(upright) as source:
        for n in range(len(source)):
            pix = source[n].get_pixmap(dpi=150, alpha=False)
            image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
            image = cv2.rotate(image, cv2.ROTATE_180 if n == 0 else cv2.ROTATE_90_CLOCKWISE)
            done, png = cv2.imencode(".png", image)
            assert done
            rect = source[n].rect
            w, h = (rect.width, rect.height) if n == 0 else (rect.height, rect.width)
            page = doc.new_page(width=w, height=h)
            page.insert_image(page.rect, stream=bytes(png))
    doc.save(target)
    doc.close()
    return target


def test_the_model_decides_only_when_sure() -> None:
    sure, vague = [0.02, 0.03, 0.9, 0.05], [0.4, 0.3, 0.2, 0.1]
    assert orientation.decided(sure, None) == 180
    assert orientation.decided(vague, None) is None
    assert orientation.decided(vague, [0.01, 0.97, 0.01, 0.01]) == 90  # by what is written
    assert orientation.decided(vague, vague) is None
    assert orientation.decided([0.25] * 4, None) is None  # a blank page
    assert orientation.SURE == 0.8


def test_what_is_written_on_a_page() -> None:
    import numpy as np

    page = np.full((1200, 900, 3), 255, np.uint8)
    assert orientation.written(page) is None
    page[100:160, 80:700] = 0  # a band of writing at the top
    x0, y0, x1, y1 = orientation.written(page) or (0, 0, 0, 0)
    assert x0 <= 80 and x1 >= 690 and y0 <= 100 and 150 <= y1 <= 180


def test_without_the_model_everything_is_as_before(tmp_path: Path, report: Path,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    """A models folder without the model: the suggestion turns nothing, the configuration
    names no model; the commands list the model with where it comes from."""
    source = _turned_scan(report, tmp_path / "verdreht.pdf")
    empty = tmp_path / "models"
    empty.mkdir()
    project = Project.open(source)
    project.models = empty
    try:
        config = project.config()
    finally:
        project.close()
    assert [p["plan"]["rotation"] for p in config["pages"]] == [0, 0]
    assert all("models" not in p for p in config["pages"])
    assert main(["models", "list", "--models", str(empty)]) == 0
    listed = json.loads(capsys.readouterr().out)["models"]
    assert [m["name"] for m in listed] == ["page-orientation"]
    assert listed[0]["present"] is False and listed[0]["url"].startswith("https://")
    assert listed[0]["licence"] == "Apache-2.0" and len(listed[0]["sha256"]) == 64
    assert main(["about"]) == 0
    assert json.loads(capsys.readouterr().out)["models"][0]["present"] is None
    broken = {**config, "pages": [{**config["pages"][0], "models": "eins"}, config["pages"][1]]}
    with pytest.raises(OptdocError) as caught:
        Project.open(source, config=broken)
    assert caught.value.details == {"reason": "field"}


@needs_model
def test_pages_set_upright_by_the_model(tmp_path: Path, report: Path) -> None:
    """The page on its head is turned by 180 degrees, the page on its side by 270, in the
    suggestion; the configuration says the model took part; from it, without the model,
    the same PDF comes again; a person's plan is theirs and names no model."""
    source = _turned_scan(report, tmp_path / "verdreht.pdf")
    project = Project.open(source)
    project.models = MODELS
    try:
        assert project.orientation(0) == 180 and project.orientation(1) == 270
        prepared = project.build()
        try:
            first = output.write(prepared, tmp_path / "a")
        finally:
            prepared.close()
    finally:
        project.close()
    config = load_config(first["config"])
    assert [p["plan"]["rotation"] for p in config["pages"]] == [180, 270]
    assert [p["models"] for p in config["pages"]] == [["page-orientation"]] * 2
    with pymupdf.open(first["document"]) as doc:  # both pages upright: portrait
        assert all(page.rect.height > page.rect.width for page in doc)
    again = Project.open(source, config=config)  # no models folder: none is needed
    try:
        plan = again.plan(1)
        prepared = again.build()
        try:
            second = output.write(prepared, tmp_path / "b")
        finally:
            prepared.close()
        assert plan is not None
        # asking for a suggestion here (no model at hand) leaves the decided plans alone
        assert again.suggestion(0).rotation == 0
        assert again.config() == config
        plan.contrast = True
        again.set_plan(1, plan)
        assert "models" not in again.config()["pages"][1]
        again.set_plan(0, again.suggestion(0), by_person=False)  # the suggestion taken back
        assert "models" not in again.config()["pages"][0]
        assert again.config()["pages"][0]["plan"]["rotation"] == 0
    finally:
        again.close()
    for key in ("document", "config"):
        assert first[key].read_bytes() == second[key].read_bytes(), key
    with_model = Project.open(source, config=config)  # and with it: the suggestion again
    with_model.models = MODELS
    try:
        plan = with_model.plan(0)
        assert plan is not None
        plan.sharpen = True
        with_model.set_plan(0, plan)
        assert "models" not in with_model.config()["pages"][0]
        with_model.set_plan(0, with_model.suggestion(0), by_person=False)
        assert with_model.config()["pages"][0] == config["pages"][0]
    finally:
        with_model.close()


@needs_model
def test_an_upright_and_a_blank_page_stay(tmp_path: Path, report: Path) -> None:
    import numpy as np

    assert MODELS is not None
    model = catalogue.orientation(MODELS)
    assert model is not None
    with pymupdf.open(report) as doc:
        image, _scale = cleanup.render(doc[0], 110)
    assert orientation.upright(image, model) == 0
    assert orientation.upright(np.full((1200, 900, 3), 255, np.uint8), model) is None
