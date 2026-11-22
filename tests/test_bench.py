"""The test bench: invented laboratory reports scored against their truth files, and
nothing of a document or a file name in the answer."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pymupdf
import pytest

from optdoc import ocr as ocrlib
from optdoc.bench import bench, numbers_of, score_text, truth_lines
from optdoc.cli import main
from tests.synthetic import rasterise

_SPEC = importlib.util.spec_from_file_location(
    "lab_reports", Path(__file__).resolve().parents[1] / "bench" / "lab_reports.py")
lab_reports = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lab_reports)


def test_numbers_and_scores() -> None:
    assert numbers_of("Kalium 5,8 mmol/l 3,5 - 5,1 H") == ["5.8", "3.5", "5.1"]
    assert numbers_of("CRP < 0,5 mg/l") == ["0.5"] and numbers_of("TSH <0,05") == ["<0.05"]
    truth = ["Kalium 5,8 mmol/l 3,5 - 5,1 H", "Natrium 140 mmol/l 135 - 145"]
    score = score_text(truth, ["Natrium 140 mmol/I 135 - 145", "Kalium 3,8 mmol/l 3,5 - 5,1 H"])
    d = score.as_dict()
    assert d["lines"] == 2 and d["numbers"] == 6 and d["numbers_right"] == 5
    assert d["rows_all_numbers_right"] == 1 and d["lines_exact"] == 0


def test_reports_and_truth(tmp_path: Path) -> None:
    pdfs = lab_reports.make(tmp_path, 3, seed=2)
    assert [p.name for p in pdfs] == ["lab-01.pdf", "lab-02.pdf", "lab-03.pdf"]
    lines = truth_lines(tmp_path / "lab-01.truth.txt")
    assert len(lines) == 18 and all(not z.startswith("#") for z in lines)
    result = bench(tmp_path, readers=ocrlib.available_backends() or ["none"]).as_dict()
    # a text layer is read as it is: every number of every row right
    for entry in result["documents"]:
        assert entry["numbers_right_share"] == 1.0, entry


@pytest.mark.skipif(not ocrlib.available_backends(), reason="kein OCR-Backend installiert")
def test_bench_on_scans_says_numbers_only(tmp_path: Path,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    """Scans of the reports, under names that must not come back: the bench answers
    with figures, no file name, no word of the reports."""
    source = tmp_path / "made"
    lab_reports.make(source, 3, seed=3)
    bench_folder = tmp_path / "bench"
    bench_folder.mkdir()
    for i, pdf in enumerate(sorted(source.glob("*.pdf")), 1):
        name = f"Musterfrau_Erika_{i}"
        with pymupdf.open(pdf) as doc:
            scan = rasterise(doc, dpi=200)
            scan.save(bench_folder / f"{name}.pdf")
            scan.close()
        (bench_folder / f"{name}.truth.txt").write_text(
            (source / f"{pdf.stem}.truth.txt").read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["bench", str(bench_folder)]) == 0
    out = capsys.readouterr().out
    answer = json.loads(out)
    assert answer["documents_found"] == 3
    for word in ("Musterfrau", "Erika", "Kalium", "Natrium", "Labor", "mmol"):
        assert word not in out, word
    for reader, total in answer["totals"].items():
        assert total["numbers_right_share"] >= 0.8, (reader, total)
    assert main(["bench", str(tmp_path / "missing")]) == 2
    assert "missing" not in capsys.readouterr().err


def test_bench_script_runs(tmp_path: Path) -> None:
    import subprocess

    script = Path(__file__).resolve().parents[1] / "bench" / "lab_reports.py"
    run = subprocess.run([sys.executable, str(script), str(tmp_path), "1"], capture_output=True,
                         text=True, check=True)
    assert run.stdout.strip().endswith("lab-01.pdf") and (tmp_path / "lab-01.truth.txt").is_file()
