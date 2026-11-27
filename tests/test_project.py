"""The preparation and its configuration document: the same input and document give the
same PDF byte for byte; work is resumed where it stopped; every page has a frame that
only what moves the page changes; a page keeps its colours where it has any; a document
of another file, or a broken one, is refused."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from optdoc import cleanup, output
from optdoc.errors import OptdocError
from optdoc.project import EMBEDDED, SUFFIX, Options, Project, load_config
from tests.synthetic import colour_scan, make_report, scan

needs_opencv = pytest.mark.skipif(not cleanup.available(), reason="needs OpenCV")


def _write(project: Project, folder: Path) -> dict[str, bytes]:
    """The result of a project, written, as bytes per file."""
    prepared = project.build()
    try:
        paths = output.write(prepared, folder)
    finally:
        prepared.close()
    return {k: paths[k].read_bytes() for k in ("document", "config")}


@needs_opencv
def test_same_input_and_document_same_result(tmp_path: Path, report: Path) -> None:
    """A tilted scan prepared once, then again from its configuration document and from
    the PDF that carries it: both files the same, byte for byte."""
    source = scan(report, tmp_path / "scan.pdf", rotation=2.0)
    project = Project.open(source)
    try:
        first = _write(project, tmp_path / "a")
    finally:
        project.close()
    config = json.loads(first["config"])
    assert config["format"] == "optdoc-config" and config["version"] == 3
    assert config["options"] == {"photo": None, "clean_up": True, "colour_pages": "jpeg"}
    page = config["pages"][0]
    assert page["plan"]["straighten"] is True and page["by"] == "auto"
    assert len(page["frame"]) == 16 and config["input"]["pages"][0]["width"] > 590
    for given in (tmp_path / "a" / f"scan{SUFFIX}", tmp_path / "a" / "scan.pdf"):
        again = Project.open(source, config=load_config(given))
        try:
            assert _write(again, tmp_path / given.suffix.strip(".")) == first
        finally:
            again.close()
    with pymupdf.open(tmp_path / "a" / "scan.pdf") as doc:
        assert doc.embfile_names() == [EMBEDDED]
        assert doc.metadata["producer"].startswith("optdoc ")
        assert not doc[0].get_text().strip()  # no text layer: reading is ocrdoc's


@needs_opencv
def test_resume_where_a_person_stopped(tmp_path: Path, report: Path) -> None:
    """A plan a person changed comes back as theirs; the pages they did not touch keep
    optdoc's suggestion."""
    source = scan(report, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        plan = project.plan(0) or cleanup.CleanupPlan()
        plan.contrast = True
        project.set_plan(0, plan)
        saved = project.save(tmp_path / f"scan{SUFFIX}")
    finally:
        project.close()
    again = Project.open(source, config=load_config(saved))
    try:
        assert again.plan(0) is not None and again.plan(0).contrast
        assert again.decided_by_person == [0]
        assert json.loads(saved.read_text())["pages"][1]["by"] == "auto"
    finally:
        again.close()


@needs_opencv
def test_frames(tmp_path: Path, report: Path) -> None:
    """The frame of a page: the same while only its light, contrast, colour or masks
    change, another once it is turned, straightened or unwarped otherwise.  A born-digital
    page has the frame of its size alone, as has a page whose plan does nothing."""
    source = scan(report, tmp_path / "scan.pdf", rotation=2.0)
    project = Project.open(source)
    try:
        plan = project.plan(0)
        assert plan is not None and plan.straighten
        first = project.frame(0)
        for change in ({"contrast": True}, {"background": not plan.background},
                       {"grey": not plan.grey}, {"masks": [(10.0, 10.0, 50.0, 50.0)]}):
            project.set_plan(0, cleanup.CleanupPlan(**{**plan.__dict__, **change}))
            assert project.frame(0) == first, change
        for change in ({"rotation": 90}, {"angle": plan.angle + 0.5}, {"straighten": False}):
            project.set_plan(0, cleanup.CleanupPlan(**{**plan.__dict__, **change}))
            assert project.frame(0) != first, change
        project.set_plan(0, None)
        bare = project.frame(0)
        project.set_plan(0, cleanup.CleanupPlan(contrast=True))
        assert project.frame(0) == bare  # only lit: where the page as it came lies
    finally:
        project.close()
    digital = Project.open(report)
    try:
        assert digital.plan(0) is None and digital.frame(0) == digital.frame(1)
    finally:
        digital.close()


@needs_opencv
def test_colours_where_the_page_has_them(tmp_path: Path) -> None:
    """A letter with a red stamp and a blue signature, scanned in colour, keeps its
    colours (a JPEG page by default, a PNG page when chosen); a scan of black print is
    stored in grey (a PNG page) either way."""
    pdf = make_report(tmp_path / "brief.pdf")
    with pymupdf.open(pdf) as doc:
        page = doc[0]
        page.draw_rect(pymupdf.Rect(330, 600, 520, 680), color=(0.8, 0.1, 0.1), width=3)
        page.insert_text((345, 645), "EINGEGANGEN", fontsize=16, color=(0.8, 0.1, 0.1))
        page.draw_bezier((90, 720), (140, 690), (190, 750), (260, 710), color=(0.1, 0.2, 0.8),
                         width=2)
        doc.save(tmp_path / "gestempelt.pdf")
    coloured = colour_scan(tmp_path / "gestempelt.pdf", tmp_path / "farbe.pdf")
    plain = scan(pdf, tmp_path / "grau.pdf", rotation=1.0)
    expected = {(coloured, "jpeg"): ("jpeg", 3), (coloured, "png"): ("png", 3),
                (plain, "jpeg"): ("png", 1), (plain, "png"): ("png", 1)}
    for (source, colour_pages), stored in expected.items():
        project = Project.open(source, Options(colour_pages=colour_pages))
        try:
            plan = project.plan(0)
            assert plan is not None and plan.active and plan.grey == (source == plain)
            prepared = project.build()
            try:
                xref = prepared.doc[0].get_images()[0][0]
                kind = prepared.doc.extract_image(xref)
                assert (kind["ext"], kind["colorspace"]) == stored, (source.name, colour_pages)
                assert prepared.config["options"]["colour_pages"] == colour_pages
            finally:
                prepared.close()
        finally:
            project.close()
    with pytest.raises(OptdocError):
        Options.from_dict({"colour_pages": "tiff"})  # a PDF holds no TIFF


def test_born_digital_pages_stay(report: Path) -> None:
    """A born-digital PDF: no plan, the pages as they came, their text included."""
    project = Project.open(report)
    try:
        assert [project.plan(n) for n in range(2)] == [None, None]
        prepared = project.build()
        try:
            assert prepared.cleaned_up == [] and "Ramipril" in prepared.doc[0].get_text()
        finally:
            prepared.close()
    finally:
        project.close()


def test_refused_configurations(tmp_path: Path, report: Path) -> None:
    """Another file's configuration, and broken ones, each by its kind."""
    project = Project.open(report)
    try:
        config = project.config()
    finally:
        project.close()
    other = tmp_path / "other.pdf"
    with pymupdf.open(report) as doc:
        doc[0].insert_text((72, 700), "geändert")
        doc.save(other)
    with pytest.raises(OptdocError) as caught:
        Project.open(other, config=config)
    assert caught.value.kind == "config-mismatch"
    cases = {
        "page": {**config, "pages": config["pages"][:1]},
        "field": {**config, "pages": [{**config["pages"][0], "by": "jemand"},
                                      config["pages"][1]]},
    }
    for reason, broken in cases.items():
        with pytest.raises(OptdocError) as caught:
            Project.open(report, config=broken)
        assert (caught.value.kind, caught.value.details) == ("bad-config", {"reason": reason})
    for content, reason in (("[1]", "format"), ("{kaputt", "json"),
                            (json.dumps({**config, "version": 1}), "format"),
                            (json.dumps({**config, "version": 2}), "format"),  # with paper
                            (json.dumps({**config, "format": "ocrdoc-config"}), "format")):
        path = tmp_path / "x.optdoc.json"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(OptdocError) as caught:
            load_config(path)
        assert caught.value.details == {"reason": reason}
    with pytest.raises(OptdocError) as caught:
        load_config(report)  # a PDF without a configuration
    assert caught.value.details == {"reason": "format"}
    assert Options.from_dict({"colour_pages": "png"}).colour_pages == "png"
    assert Options.from_dict({"paper": "a5"}) == Options()  # no setting any more: ignored


@needs_opencv
def test_the_same_pages_as_another_file(tmp_path: Path, report: Path) -> None:
    """A picture and a PDF that shows it page for page (as typdoc binds it): a caller that
    knows they are the same document takes a document of the one for the other.  What a
    person planned stays; optdoc's own plans are suggested anew; a page of another size,
    or no word of the caller, is another file."""
    import cv2
    from doccor import pictures as view

    from tests.synthetic import camera_photo

    photo = tmp_path / "foto.png"
    cv2.imwrite(str(photo), camera_photo(report, pitch=14, fill=0.85, size=(900, 1200))[0])
    bound = tmp_path / "foto.pdf"
    pages = view.pages(photo)
    pages.save(bound)
    pages.close()
    project = Project.open(photo)
    try:
        suggested = project.plan(0)
        assert suggested is not None and suggested.unwarp
        mine = cleanup.CleanupPlan.from_dict({**suggested.full_dict(), "contrast": True,
                                              "contrast_strength": 4})
        project.set_plan(0, mine)
        config = project.config()
    finally:
        project.close()
    with pytest.raises(OptdocError) as caught:
        Project.open(bound, config=config)
    assert caught.value.kind == "config-mismatch"
    taken = Project.open(bound, config=config, same_document=True)
    try:
        assert taken.rebased and taken.decided_by_person == [0]
        assert taken.plan(0).full_dict() == mine.full_dict()
        assert taken.frame(0) == config["pages"][0]["frame"]  # the same page, the same frame
        assert taken.config()["input"]["suffix"] == ".pdf"
    finally:
        taken.close()
    auto = Project.open(photo)
    try:
        auto_config = auto.config()
    finally:
        auto.close()
    again = Project.open(bound, config=auto_config, same_document=True)
    try:  # optdoc's own plan is made anew on this file, and comes out the same
        assert again.rebased and again.decided_by_person == []
        assert again.plan(0).full_dict() == suggested.full_dict()
    finally:
        again.close()
    other = tmp_path / "anders.pdf"
    with pymupdf.open() as doc:
        doc.new_page(width=595, height=842)
        doc.save(other)
    with pytest.raises(OptdocError) as caught:
        Project.open(other, config=config, same_document=True)
    assert caught.value.kind == "config-mismatch"
