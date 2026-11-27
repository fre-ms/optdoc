"""The command line as a program sees it: one JSON answer on standard output, success or
failure, the failures by kind and in two languages, never a path; progress on standard
error; nothing written outside the folder given; no network."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest
from doccor import offline

from optdoc import __version__, cleanup
from optdoc.cli import INTERFACE, main
from optdoc.errors import KINDS
from optdoc.project import Project
from tests.synthetic import scan

needs_opencv = pytest.mark.skipif(not cleanup.available(), reason="needs OpenCV")
HEAD = {"interface", "made_with"}
# a file name as medorello's records have them: a patient's name in the path
PATIENT = "Mustermann,Erika_1964-08-12_K7Q4MX"


def _answer(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict, str]:
    """Run the command line in this process; its status, its answer and its standard error."""
    status = main(argv)
    captured = capsys.readouterr()
    return status, json.loads(captured.out), captured.err


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    """``python -m optdoc`` with ``argv``."""
    return subprocess.run([sys.executable, "-m", "optdoc", *argv], capture_output=True,
                          text=True, check=False, **kwargs)


def _clean_environment(tmp_path: Path) -> tuple[dict[str, str], dict[str, Path]]:
    """An environment whose temporary, home and cache folders are new and empty."""
    elsewhere = {name: tmp_path / name for name in ("tmp", "home", "cache")}
    for folder in elsewhere.values():
        folder.mkdir()
    env = {**os.environ, "TMPDIR": str(elsewhere["tmp"]), "TEMP": str(elsewhere["tmp"]),
           "TMP": str(elsewhere["tmp"]), "HOME": str(elsewhere["home"]),
           "USERPROFILE": str(elsewhere["home"]), "XDG_CACHE_HOME": str(elsewhere["cache"]),
           "PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen"}
    return env, elsewhere


def test_about(capsys: pytest.CaptureFixture[str]) -> None:
    """What an installation can do."""
    status, answer, _ = _answer(capsys, ["about"])
    assert status == 0
    assert set(answer) == HEAD | {"version", "clean_up", "heic", "window", "upside_down",
                                  "models"}
    assert answer["interface"] == INTERFACE and answer["version"] == __version__
    assert answer["made_with"] == f"optdoc {__version__}"
    assert [m["name"] for m in answer["models"]] == ["page-orientation"]


def _encrypted(path: Path) -> Path:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "geheim")
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="kennwort",
             owner_pw="kennwort")
    doc.close()
    return path


def _config(folder: Path, name: str, content: str) -> Path:
    path = folder / f"{PATIENT}-{name}.optdoc.json"
    path.write_text(content, encoding="utf-8")
    return path


def test_failures_by_kind_without_paths(tmp_path: Path, report: Path,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    """Every failure answers with a fixed kind, its details and its message in English and
    German, ends with status 2, and repeats neither the path nor the name of the file,
    neither in the answer nor on standard error."""
    folder = tmp_path / PATIENT
    folder.mkdir()
    damaged = folder / f"{PATIENT}.pdf"
    damaged.write_bytes(b"%PDF-1.7\nnot really\n")
    text = folder / f"{PATIENT}.txt"
    text.write_text("Befund", encoding="utf-8")
    good = folder / f"{PATIENT}-gut.pdf"
    good.write_bytes(report.read_bytes())
    cases = {
        "missing": ["run", str(folder / "fehlt.pdf")],
        "unsupported": ["run", str(text)],
        "unreadable": ["run", str(damaged)],
        "encrypted": ["run", str(_encrypted(folder / f"{PATIENT}-zu.pdf"))],
        "paper": ["run", str(good), "--paper", "b5"],
        "usage": ["run", str(good), "--unknown", str(folder)],
        "usage:verb": ["prepare", str(good)],
        "same-as-source": ["run", str(good), "--out", str(folder)],
    }
    fine = Project.open(good)
    config = fine.config()
    fine.close()
    configs = {"json": "{kaputt", "format": "[1, 2]",
               "page": json.dumps({**config, "pages": config["pages"][:1]}),
               "field": json.dumps({**config, "options": {"paper": 5}})}
    for reason, content in configs.items():
        cases[f"bad-config:{reason}"] = ["run", str(good), "--out", str(tmp_path / "o"),
                                         "--config", str(_config(folder, reason, content))]
    other = json.dumps({**config, "input": {**config["input"], "sha256": "0" * 64}})
    cases["config-mismatch"] = ["run", str(good), "--out", str(tmp_path / "o"),
                                "--config", str(_config(folder, "fremd", other))]
    cases["usage:both"] = ["run", str(good), "--scan", "--config",
                           str(_config(folder, "beides", json.dumps(config)))]
    for expected, argv in cases.items():
        status, answer, err = _answer(capsys, argv)
        kind = expected.split(":")[0]
        assert status == 2, expected
        assert answer["error"] == kind and set(answer) == HEAD | {"error", "details",
                                                                  "message"}, expected
        assert set(answer["message"]) == {"en", "de"}, expected
        if kind == "bad-config":
            assert answer["details"] == {"reason": expected.split(":")[1]}
        said = json.dumps(answer, ensure_ascii=False) + err
        assert PATIENT not in said and str(tmp_path) not in said, (expected, said)
    assert not (tmp_path / "o").exists()  # a refused configuration writes nothing


def test_answer_names_the_results(tmp_path: Path, report: Path,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    """A born-digital document: the answer names both files and the pages; nothing was
    prepared."""
    status, answer, err = _answer(capsys, ["run", str(report), "--out", str(tmp_path / "out")])
    assert status == 0 and err == ""
    assert set(answer) == HEAD | {"document", "config", "pages", "cleaned_up", "unwarped",
                                  "decided"}
    assert answer["pages"] == 2 and answer["cleaned_up"] == [] == answer["decided"]
    assert all(Path(answer[k]).parent == tmp_path / "out" for k in ("document", "config"))


def test_standard_error_is_optdocs_own() -> None:
    """While a command runs, what libraries write to standard error below Python and what
    Python code prints there goes nowhere; optdoc's own lines get through, and afterwards
    standard error is as before."""
    code = ("import os, sys\n"
            "from doccor.cli import own_stderr\n"
            "with own_stderr() as said:\n"
            "    os.write(2, b'native noise\\n')\n"
            "    print('python noise', file=sys.stderr)\n"
            "    said.write('optdoc\\n')\n"
            "os.write(2, b'after\\n')\n")
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True)
    assert run.stderr == "optdoc\nafter\n"


def test_every_kind_is_worded_alike() -> None:
    """Both languages of a kind fill in the same details."""
    from string import Formatter

    for kind, wording in KINDS.items():
        fields = [{f for _, f, _, _ in Formatter().parse(wording[language]) if f}
                  for language in ("en", "de")]
        assert fields[0] == fields[1], kind


def test_network_is_closed() -> None:
    """Once the command line has started, nothing in the process reaches the network."""
    main(["about"])
    assert offline.network_forbidden()
    before = offline.attempts
    with pytest.raises(offline.NetworkForbidden):
        socket.create_connection(("192.0.2.1", 80), timeout=1)
    with pytest.raises(offline.NetworkForbidden):
        socket.getaddrinfo("example.org", 443)
    assert offline.attempts == before + 2


@needs_opencv
def test_run_on_the_command_line(tmp_path: Path, report: Path) -> None:
    """``python -m optdoc run`` writes the results and answers in JSON; with
    ``--progress`` standard error holds one line per page and nothing else; from the
    configuration it wrote, the same files come again, byte for byte.  Nothing lands
    outside the folder given: not in the temporary folder, not in the home folder, not
    next to the source."""
    (tmp_path / "in").mkdir()
    source = scan(report, tmp_path / "in" / "scan.pdf", rotation=2.0)
    env, elsewhere = _clean_environment(tmp_path)
    target = tmp_path / "ergebnis"
    run = _run(["run", str(source), "--out", str(target), "--progress"], env=env)
    assert run.returncode == 0, run.stdout
    answer = json.loads(run.stdout)
    assert answer["pages"] == 2 and answer["cleaned_up"] == [1, 2]
    progress = [json.loads(z) for z in run.stderr.splitlines()]
    assert progress == [{"page": 1, "of": 2}, {"page": 2, "of": 2}]
    assert sorted(p.name for p in target.iterdir()) == ["scan.optdoc.json", "scan.pdf"]
    assert [p.name for p in (tmp_path / "in").iterdir()] == ["scan.pdf"]
    for name, folder in elsewhere.items():
        assert not any(folder.rglob("*")), name
    second = _run(["run", str(source), "--out", str(tmp_path / "zwei"), "--config",
                   answer["config"]])
    again = json.loads(second.stdout)
    for key in ("document", "config"):
        assert Path(again[key]).read_bytes() == Path(answer[key]).read_bytes(), key


@needs_opencv
@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="needs PySide6")
def test_edit_goes_through_and_leaves_nothing_behind(tmp_path: Path, report: Path) -> None:
    """``edit --self-test`` opens the window without a screen, applies, and answers like
    ``run``, with the same files byte for byte; the window leaves nothing in the
    temporary, home or cache folder."""
    source = scan(report, tmp_path / "scan.pdf", rotation=1.0)
    env, elsewhere = _clean_environment(tmp_path)
    run = _run(["edit", str(source), "--out", str(tmp_path / "e"), "--self-test",
                "--language", "de"], env=env)
    assert run.returncode == 0, run.stdout
    answer = json.loads(run.stdout)
    assert answer["finished"] is True and answer["cleaned_up"] == [1, 2]
    for name, folder in elsewhere.items():
        assert not any(folder.rglob("*")), (name, list(folder.rglob("*")))
    prepared = json.loads(_run(["run", str(source), "--out", str(tmp_path / "p")]).stdout)
    for key in ("document", "config"):
        assert Path(answer[key]).read_bytes() == Path(prepared[key]).read_bytes(), key
