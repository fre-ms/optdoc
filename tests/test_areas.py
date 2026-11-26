"""The areas optdoc finds besides tables: barcodes (read as well), pictures, stamps and
handwriting, on invented letters born digital and scanned in colour; and none on a
laboratory report, whose values must all stay in the text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optdoc import areas, cleanup, output
from optdoc import ocr as ocrlib
from optdoc.project import Options, Project
from tests.synthetic import area_letter, colour_scan, lab_report, scan

pytestmark = [
    pytest.mark.skipif(not cleanup.available(), reason="needs OpenCV (extra 'ocr')"),
    pytest.mark.skipif(not areas.barcodes_available(), reason="needs zxing-cpp (extra 'barcodes')"),
]
needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                   reason="no OCR engine installed")


def _iou(a: list[float] | tuple, b: list[float] | tuple) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(0.0, w) * max(0.0, h)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _matched(found: list, truth: list[dict], kind: str) -> int:
    """How many of the truth's areas of a kind were found (overlap at least half)."""
    return sum(any(r.kind == kind and _iou(r.box, a["box"]) >= 0.5 for r in found)
               for a in truth if a["kind"] == kind)


def _check(found: list, truth: list[dict], stamps: bool = True) -> None:
    """Every picture and barcode (with what it says), the stamp, and at least one of
    the two handwritten areas; no picture where the truth has none."""
    assert _matched(found, truth, "image") == 2
    codes = [a for a in truth if a["kind"] == "barcode"]
    for code in codes:
        assert any(r.kind == "barcode" and r.content == code["content"]
                   and _iou(r.box, code["box"]) >= 0.5 for r in found), code["format"]
    if stamps:
        assert _matched(found, truth, "stamp") == 1
    assert _matched(found, truth, "handwriting") >= 1
    for r in found:
        if r.kind == "image":
            assert any(_iou(r.box, a["box"]) >= 0.5 for a in truth if a["kind"] == "image")


def test_areas_of_a_born_digital_letter(tmp_path: Path) -> None:
    """On the letter as it was made: the logo and the picture, every barcode with its
    content, the stamp, the signature or the note."""
    pdf, truth = area_letter(tmp_path, 1)
    project = Project.open(pdf, Options(reader="none"))
    try:
        _check(project.regions(0), truth)
    finally:
        project.close()


@needs_backend
def test_areas_of_a_letter_scanned_in_colour(tmp_path: Path) -> None:
    """Scanned in colour, turned and grainy, read by OCR: the same areas; the stamp is
    found although the clean-up takes its colour away before reading.  The reading
    names them, a barcode with what it says, and the words in pictures and barcodes are
    not in the text."""
    pdf, truth = area_letter(tmp_path, 2)
    source = colour_scan(pdf, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        found = project.regions(0)
        _check(found, truth)
        reading = project.build()
        try:
            paths = output.write(reading, tmp_path / "out")
        finally:
            reading.close()
    finally:
        project.close()
    page = json.loads(paths["reading"].read_text(encoding="utf-8"))["pages"][0]
    kinds = {r["kind"] for r in page["regions"]}
    assert {"image", "barcode", "stamp", "handwriting"} <= kinds
    contents = {r["content"] for r in page["regions"] if r["kind"] == "barcode"}
    assert contents == {a["content"] for a in truth if a["kind"] == "barcode"}
    assert "Sehr geehrte" in page["text"] and "Ramipril" in page["text"]


@needs_backend
def test_nothing_but_the_table_on_a_laboratory_report(tmp_path: Path) -> None:
    """A scanned laboratory report: its table, and no picture, stamp or handwriting that
    could take a value out of the text."""
    pdf, _ = lab_report(tmp_path, 3)
    project = Project.open(scan(pdf, tmp_path / "scan.pdf", noise=0.01, rotation=1.0))
    try:
        assert [r.kind for r in project.regions(0)] == ["table"]
    finally:
        project.close()


def test_areas_switched_off(tmp_path: Path) -> None:
    """Without the finding of areas, a letter has none (a person can still draw them)."""
    pdf, _truth = area_letter(tmp_path, 1)
    project = Project.open(pdf, Options(reader="none", areas=False))
    try:
        assert [r.kind for r in project.regions(0) if r.kind != "table"] == []
    finally:
        project.close()
