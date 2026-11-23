"""The project and its configuration: the same file and configuration give the same
result byte for byte; work is resumed where it stopped; a correction reaches the text
layer and is marked as a person's; a configuration of another file, or a broken one, is
refused."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from optdoc import cleanup, output
from optdoc import ocr as ocrlib
from optdoc.errors import OptdocError
from optdoc.project import SUFFIX, Options, Project, load_config
from tests.synthetic import scan

needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                   reason="no OCR engine installed")
FILES = ("pdf", "reading", "markdown", "config")


def _write(project: Project, folder: Path) -> dict[str, bytes]:
    """The result of a project, written, as bytes per file."""
    reading = project.build()
    try:
        paths = output.write(reading, folder)
    finally:
        reading.close()
    return {k: paths[k].read_bytes() for k in FILES}


@needs_backend
def test_same_file_and_configuration_same_result(tmp_path: Path, report: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """A scan read once, then made again from its configuration file and from the PDF
    that carries it: every file the same, byte for byte, and OCR does not run again."""
    source = scan(report, tmp_path / "scan.pdf", rotation=2.0)
    project = Project.open(source)
    try:
        first = _write(project, tmp_path / "a")
    finally:
        project.close()
    config = json.loads(first["config"])
    assert config["format"] == "optdoc-config" and config["pages"][0]["ocr"] is True
    assert config["pages"][0]["plan"]["straighten"] is True and config["pages"][0]["words"]

    def refuse(*_args: object, **_kwargs: object) -> list[ocrlib.OCRWord]:
        raise AssertionError("OCR must not run when the words are stored")

    monkeypatch.setattr(ocrlib, "recognise_words", refuse)
    for given in (tmp_path / "a" / f"scan{SUFFIX}", tmp_path / "a" / "scan.pdf"):
        again = Project.open(source, config=load_config(given))
        try:
            assert _write(again, tmp_path / given.suffix.strip(".")) == first
        finally:
            again.close()


@needs_backend
def test_resume_and_correct(tmp_path: Path, report: Path) -> None:
    """Work saved half-way comes back as it was: a plan changed by hand, a correction.
    The correction is in the text layer and in the reading, marked as a person's."""
    source = scan(report, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        plan = project.plan(0) or cleanup.CleanupPlan()
        plan.contrast = True
        project.set_plan(0, plan)
        text = project.text(0)
        assert "Ramipril" in text
        project.set_correction(0, text.replace("Ramipril", "Ramiprill"))
        saved = project.save(tmp_path / f"scan{SUFFIX}")
        assert project.text(1) and project.pages[1].correction is None
    finally:
        project.close()
    again = Project.open(source, config=load_config(saved))
    try:
        assert again.plan(0) is not None and again.plan(0).contrast
        assert again.pages[0].correction is not None and "Ramiprill" in again.text(0)
        assert again.corrected == [0]
        reading = again.build()
        try:
            paths = output.write(reading, tmp_path / "out")
        finally:
            reading.close()
    finally:
        again.close()
    with pymupdf.open(paths["pdf"]) as doc:
        assert "Ramiprill" in doc[0].get_text() and doc[0].search_for("Ramiprill")
    words = json.loads(paths["reading"].read_text(encoding="utf-8"))["pages"][0]["words"]
    by = {w["text"].strip(","): w["by"] for w in words}
    assert by["Ramiprill"] == "person" and by["Diagnosen:"] == "ocr"


@needs_backend
def test_a_new_plan_reads_the_page_again(tmp_path: Path, report: Path) -> None:
    """Changing the clean-up drops what OCR read; the correction stays."""
    source = scan(report, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        project.set_correction(0, project.text(0) + "\nNachtrag")
        assert not project.needs_reading(0)
        plan = project.plan(0) or cleanup.CleanupPlan()
        plan.sharpen = not plan.sharpen
        project.set_plan(0, plan)
        assert project.needs_reading(0) and project.pages[0].correction is not None
        assert project.text(0).endswith("Nachtrag")
        same = project.plan(0)
        project.set_plan(0, same)  # the same plan again: nothing to read
        assert not project.needs_reading(0)
    finally:
        project.close()


def test_text_layer_pages(tmp_path: Path, report: Path) -> None:
    """A born-digital PDF: no plan, no OCR, nothing to correct."""
    project = Project.open(report, Options(reader="none"))
    try:
        config = project.config()
        assert [p["plan"] for p in config["pages"]] == [None, None]
        project.read_all()
        assert [p.ocr for p in project.pages] == [False, False]
        assert "Ramipril" in project.text(0)
        with pytest.raises(OptdocError) as caught:
            project.set_correction(0, "anders")
        assert caught.value.kind == "not-ocr"
    finally:
        project.close()


def test_refused_configurations(tmp_path: Path, report: Path) -> None:
    """Another file's configuration, and broken ones, each by its kind."""
    project = Project.open(report, Options(reader="none"))
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
        "field": {**config, "pages": [{**config["pages"][0], "ocr": "ja"},
                                      config["pages"][1]]},
    }
    for reason, broken in cases.items():
        with pytest.raises(OptdocError) as caught:
            Project.open(report, config=broken)
        assert (caught.value.kind, caught.value.details) == ("bad-config", {"reason": reason})
    for content, reason in (("[1]", "format"), ("{kaputt", "json"),
                            (json.dumps({**config, "version": 99}), "format")):
        path = tmp_path / "x.optdoc.json"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(OptdocError) as caught:
            load_config(path)
        assert caught.value.details == {"reason": reason}
    with pytest.raises(OptdocError) as caught:
        load_config(report)  # a PDF without a configuration
    assert caught.value.details == {"reason": "format"}
