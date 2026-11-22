"""The results of a reading: searchable PDF, reading as JSON, Markdown, plan; the
command line."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

from optdoc import ocr as ocrlib
from optdoc import output
from optdoc.cli import main
from optdoc.reading import read
from tests.synthetic import scan

needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                     reason="kein OCR-Backend installiert")


@needs_backend
def test_scan_becomes_searchable(tmp_path: Path, report: Path) -> None:
    """The scan comes back with an invisible text layer on the printed words, the
    reading names every word with its box, the plan can be given back."""
    source = scan(report, tmp_path / "scan.pdf", rotation=2.0)
    reading = read(source)
    try:
        paths = output.write(reading, tmp_path / "out")
        ocr_page_text = reading.pages[0].text
    finally:
        reading.close()
    with pymupdf.open(paths["pdf"]) as d:
        assert "Ramipril" in d[0].get_text() and "Kontrolle" in d[1].get_text()
        found = d[0].search_for("Diagnosen")
        assert d.metadata["producer"].startswith("optdoc ")
    a = ocr_page_text.text.index("Diagnosen")
    bounds = ocr_page_text.rects(a, a + len("Diagnosen"))[0]
    assert any(abs(r.x0 - bounds.x0) < 3 and r.y0 < bounds.y1 and r.y1 > bounds.y0
               for r in found), (found, bounds)
    reading_json = json.loads(paths["reading"].read_text(encoding="utf-8"))
    assert reading_json["format"] == "optdoc-reading" and reading_json["version"] == 1
    json_page = reading_json["pages"][0]
    assert json_page["source"] == "ocr" and json_page["page"] == 1
    word = next(w for w in json_page["words"] if w["text"] == "Diagnosen:")
    assert len(word["box"]) == 4 and 0 < word["confidence"] <= 1
    assert json_page["text"][word["start"]:word["end"]] == "Diagnosen:"
    assert "## Page 2" in paths["markdown"].read_text(encoding="utf-8")
    plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
    assert plan["1"]["straighten"] is True
    assert reading_json["plan"] == plan


def test_text_layer_stays_as_it_is(tmp_path: Path, report: Path) -> None:
    reading = read(report)
    try:
        paths = output.write(reading, tmp_path / "out")
    finally:
        reading.close()
    data = json.loads(paths["reading"].read_text(encoding="utf-8"))
    assert [s["source"] for s in data["pages"]] == ["text", "text"]
    assert all("confidence" not in w for w in data["pages"][0]["words"])
    with pymupdf.open(paths["pdf"]) as d:
        assert d[0].get_text().count("Ramipril") == 1  # nothing laid over a text layer


def test_source_is_never_overwritten(tmp_path: Path, report: Path) -> None:
    reading = read(report)
    try:
        with pytest.raises(ValueError, match="overwrite"):
            output.write(reading, report.parent)
    finally:
        reading.close()


def test_readers(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["readers"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert set(answer) == {"version", "readers", "clean_up", "heic"}
    assert set(answer["readers"]) <= {"rapidocr", "tesseract"}


def test_prepare_reports_errors_without_content(tmp_path: Path,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["prepare", str(tmp_path / "fehlt.pdf")]) == 2
    assert "no such file" in capsys.readouterr().err


@needs_backend
def test_prepare_on_the_command_line(tmp_path: Path, report: Path) -> None:
    """``python -m optdoc prepare`` writes the results and answers in JSON; the plan it
    wrote can be handed back."""
    source = scan(report, tmp_path / "scan.pdf", rotation=2.0)
    target = tmp_path / "ergebnis"
    run = subprocess.run([sys.executable, "-m", "optdoc", "prepare", str(source), "--out",
                           str(target)], capture_output=True, text=True, check=True)
    answer = json.loads(run.stdout)
    assert answer["pages"] == 2 and answer["ocr_pages"] == [1, 2]
    assert answer["cleaned_up"] == [1, 2] and Path(answer["pdf"]).is_file()
    second = subprocess.run([sys.executable, "-m", "optdoc", "prepare", str(source), "--out",
                              str(tmp_path / "zwei"), "--plan", answer["plan"], "--no-structure"],
                             capture_output=True, text=True, check=True)
    assert json.loads(second.stdout)["cleaned_up"] == [1, 2]
