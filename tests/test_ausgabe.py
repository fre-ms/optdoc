"""The results of a reading: searchable PDF, reading as JSON, Markdown, plan; the
command line."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

from optdoc import ausgabe
from optdoc import ocr as ocrmodul
from optdoc.cli import main
from optdoc.lesen import lies
from tests.synthetisch import scan

braucht_backend = pytest.mark.skipif(not ocrmodul.verfuegbare_backends(),
                                     reason="kein OCR-Backend installiert")


@braucht_backend
def test_scan_wird_durchsuchbar(tmp_path: Path, befund: Path) -> None:
    """The scan comes back with an invisible text layer on the printed words, the
    reading names every word with its box, the plan can be given back."""
    quelle = scan(befund, tmp_path / "scan.pdf", drehung=2.0)
    lesung = lies(quelle)
    try:
        pfade = ausgabe.schreibe(lesung, tmp_path / "aus")
        ocr_seite = lesung.seiten[0].text
    finally:
        lesung.schliessen()
    with pymupdf.open(pfade["pdf"]) as d:
        assert "Ramipril" in d[0].get_text() and "Kontrolle" in d[1].get_text()
        gefunden = d[0].search_for("Diagnosen")
        assert d.metadata["producer"].startswith("optdoc ")
    a = ocr_seite.text.index("Diagnosen")
    kasten = ocr_seite.rects(a, a + len("Diagnosen"))[0]
    assert any(abs(r.x0 - kasten.x0) < 3 and r.y0 < kasten.y1 and r.y1 > kasten.y0
               for r in gefunden), (gefunden, kasten)
    lesung_json = json.loads(pfade["reading"].read_text(encoding="utf-8"))
    assert lesung_json["format"] == "optdoc-reading" and lesung_json["version"] == 1
    seite = lesung_json["pages"][0]
    assert seite["source"] == "ocr" and seite["page"] == 1
    wort = next(w for w in seite["words"] if w["text"] == "Diagnosen:")
    assert len(wort["box"]) == 4 and 0 < wort["confidence"] <= 1
    assert seite["text"][wort["start"]:wort["end"]] == "Diagnosen:"
    assert "## Page 2" in pfade["markdown"].read_text(encoding="utf-8")
    plan = json.loads(pfade["plan"].read_text(encoding="utf-8"))
    assert plan["1"]["begradigen"] is True
    assert lesung_json["plan"] == plan


def test_textebene_bleibt_wie_sie_ist(tmp_path: Path, befund: Path) -> None:
    lesung = lies(befund)
    try:
        pfade = ausgabe.schreibe(lesung, tmp_path / "aus")
    finally:
        lesung.schliessen()
    daten = json.loads(pfade["reading"].read_text(encoding="utf-8"))
    assert [s["source"] for s in daten["pages"]] == ["text", "text"]
    assert all("confidence" not in w for w in daten["pages"][0]["words"])
    with pymupdf.open(pfade["pdf"]) as d:
        assert d[0].get_text().count("Ramipril") == 1  # nothing laid over a text layer


def test_quelle_wird_nie_ueberschrieben(tmp_path: Path, befund: Path) -> None:
    lesung = lies(befund)
    try:
        with pytest.raises(ValueError, match="overwrite"):
            ausgabe.schreibe(lesung, befund.parent)
    finally:
        lesung.schliessen()


def test_readers(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["readers"]) == 0
    antwort = json.loads(capsys.readouterr().out)
    assert set(antwort) == {"version", "readers", "clean_up", "heic"}
    assert set(antwort["readers"]) <= {"rapidocr", "tesseract"}


def test_prepare_meldet_fehler_ohne_inhalt(tmp_path: Path,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["prepare", str(tmp_path / "fehlt.pdf")]) == 2
    assert "no such file" in capsys.readouterr().err


@braucht_backend
def test_prepare_auf_der_kommandozeile(tmp_path: Path, befund: Path) -> None:
    """``python -m optdoc prepare`` writes the results and answers in JSON; the plan it
    wrote can be handed back."""
    quelle = scan(befund, tmp_path / "scan.pdf", drehung=2.0)
    ziel = tmp_path / "ergebnis"
    lauf = subprocess.run([sys.executable, "-m", "optdoc", "prepare", str(quelle), "--out",
                           str(ziel)], capture_output=True, text=True, check=True)
    antwort = json.loads(lauf.stdout)
    assert antwort["pages"] == 2 and antwort["ocr_pages"] == [1, 2]
    assert antwort["cleaned_up"] == [1, 2] and Path(antwort["pdf"]).is_file()
    zweiter = subprocess.run([sys.executable, "-m", "optdoc", "prepare", str(quelle), "--out",
                              str(tmp_path / "zwei"), "--plan", antwort["plan"], "--no-structure"],
                             capture_output=True, text=True, check=True)
    assert json.loads(zweiter.stdout)["cleaned_up"] == [1, 2]
