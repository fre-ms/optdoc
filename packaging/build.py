"""Build optdoc as one executable file and try it out.

    uv sync --extra ocr --extra tables --extra gui --group build
    uv run python packaging/build.py [--identity "Developer ID Application: …"] [--no-check]

writes ``dist/optdoc-<target>`` (the name Tauri expects of a sidecar, ``<target>`` being
the Rust target triple of this computer: ``aarch64-apple-darwin`` on a Mac with Apple
silicon), ``dist/optdoc-<target>.sha256`` and ``dist/optdoc-<target>.licences.json`` (the
packages inside and their licences).  With ``--onedir`` a folder ``optdoc-<target>-onedir``
instead, with the program ``optdoc`` in it.  Then it runs the program the way an
application will: ``readers``; ``prepare`` on an invented photographed laboratory report
with the temporary, home and cache folders pointed at empty folders, which must stay
empty; a failure, which must answer with its kind; on macOS once more with the network
closed by the system (``sandbox-exec``), where that is allowed.  It ends with a summary
in JSON: file, size, checksum, timings, checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # the invented documents of the tests

NO_NETWORK = "(version 1)(allow default)(deny network*)"


def target_triple() -> str:
    """The Rust target triple of this computer, which Tauri appends to a sidecar's name."""
    rustc = shutil.which("rustc")
    if rustc:
        out = subprocess.run([rustc, "-vV"], capture_output=True, text=True, check=False).stdout
        for line in out.splitlines():
            if line.startswith("host: "):
                return line.removeprefix("host: ").strip()
    machine = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64",
               "aarch64": "aarch64"}[platform.machine().lower()]
    system = {"darwin": "apple-darwin", "linux": "unknown-linux-gnu",
              "win32": "pc-windows-msvc"}[sys.platform]
    return f"{machine}-{system}"


def build(name: str, identity: str | None, onedir: bool = False) -> Path:
    """Run PyInstaller on the specification; returns the program.  PyInstaller loads ONNX
    Runtime to collect it, which would start its telemetry (see optdoc.offline)."""
    env = {**os.environ, "OPTDOC_BINARY_NAME": name, "ORT_DISABLE_TELEMETRY": "1"}
    if identity:
        env["OPTDOC_CODESIGN_IDENTITY"] = identity
    if onedir:
        env["OPTDOC_ONEDIR"] = "1"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
                    str(ROOT / "packaging" / "optdoc.spec")], check=True, env=env, cwd=ROOT)
    suffix = ".exe" if sys.platform == "win32" else ""
    if onedir:
        return ROOT / "dist" / name / f"optdoc{suffix}"
    return ROOT / "dist" / f"{name}{suffix}"


def licences() -> list[dict[str, str]]:
    """The Python distributions the program carries (optdoc with the extras "ocr",
    "tables" and "gui" and what they need), each with its version and licence as its
    metadata states it."""
    from importlib import metadata

    from packaging.requirements import Requirement

    found: dict[str, dict[str, str]] = {}
    queue = [("optdoc", {"ocr", "tables", "gui"})]
    while queue:
        name, extras = queue.pop()
        key = name.lower().replace("_", "-")
        if key in found:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        meta = dist.metadata
        licence = (meta.get("License-Expression") or next(
            (c.split(" :: ")[-1] for c in meta.get_all("Classifier") or []
             if c.startswith("License ::")), None) or (meta.get("License") or "").split("\n")[0])
        found[key] = {"name": meta["Name"], "version": dist.version, "licence": licence}
        for text in dist.requires or []:
            requirement = Requirement(text)
            markers = [{"extra": e} for e in extras] or [{"extra": ""}]
            if requirement.marker is None or any(requirement.marker.evaluate(m) for m in markers):
                queue.append((requirement.name, set(requirement.extras)))
    return sorted(found.values(), key=lambda d: d["name"].lower())


def _run(argv: list[str], env: dict[str, str] | None = None) -> tuple[int, dict, str, float]:
    """Run the program; its status, its answer, its standard error and the seconds taken."""
    start = time.monotonic()
    run = subprocess.run(argv, capture_output=True, text=True, check=False, env=env,
                         timeout=900)
    seconds = round(time.monotonic() - start, 2)
    return run.returncode, json.loads(run.stdout), run.stderr, seconds


def check(program: Path) -> dict[str, object]:
    """Try the program out; raises AssertionError at the first thing that is wrong."""
    from tests.synthetic import lab_report, photograph

    timings: dict[str, float] = {}
    checks: dict[str, str] = {}
    status, answer, _, timings["readers"] = _run([str(program), "readers"])
    assert status == 0 and "rapidocr" in answer["readers"], answer
    assert answer["clean_up"] and answer["heic"] and answer["tables"] and answer["window"], \
        answer
    assert answer["interface"] >= 2, answer
    checks["readers"] = f"{answer['made_with']}, readers {answer['readers']}"
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        pdf, _ = lab_report(work / "in", 1)
        photo = photograph(pdf, work / "in" / "foto.jpg")
        empty = {name: work / name for name in ("tmp", "home", "cache")}
        for path in empty.values():
            path.mkdir()
        env = {**os.environ, "TMPDIR": str(empty["tmp"]), "TEMP": str(empty["tmp"]),
               "TMP": str(empty["tmp"]), "HOME": str(empty["home"]),
               "USERPROFILE": str(empty["home"]), "XDG_CACHE_HOME": str(empty["cache"])}
        status, answer, err, timings["prepare"] = _run(
            [str(program), "prepare", str(photo), "--out", str(work / "out"), "--progress"],
            env)
        assert status == 0 and answer["ocr_pages"] == [1] and answer["cleaned_up"] == [1], \
            answer
        assert answer["tables"] and answer["tables"] >= 1, answer
        assert [json.loads(z) for z in err.splitlines()] == [{"page": 1, "of": 1}], err
        assert sorted(p.name for p in (work / "out").iterdir()) == [
            "foto.md", "foto.optdoc.json", "foto.pdf", "foto.reading.json"]
        left = [str(p.relative_to(work)) for f in empty.values() for p in f.rglob("*")]
        assert not left, left
        checks["prepare"] = ("photo read, its table found, four files, nothing left in tmp, "
                             "home or cache")
        status, again, _, timings["prepare --config"] = _run(
            [str(program), "prepare", str(photo), "--out", str(work / "again"), "--config",
             answer["config"]], env)
        assert status == 0, again
        for key in ("pdf", "reading", "markdown", "config"):
            assert Path(again[key]).read_bytes() == Path(answer[key]).read_bytes(), key
        checks["reproduced"] = "the same four files again from the configuration, byte for byte"
        status, edited, _, timings["edit --self-test"] = _run(
            [str(program), "edit", str(photo), "--out", str(work / "edited"), "--self-test"],
            {**env, "QT_QPA_PLATFORM": "offscreen"})
        assert status == 0 and edited["finished"], edited
        assert Path(edited["pdf"]).read_bytes() == Path(answer["pdf"]).read_bytes()
        left = [str(p.relative_to(work)) for f in empty.values() for p in f.rglob("*")]
        assert not left, left
        checks["window"] = "opened without a screen, applied, the same PDF, nothing left behind"
        status, answer, _, _ = _run([str(program), "prepare", str(work / "fehlt.jpg")])
        assert status == 2 and answer["error"] == "missing", answer
        checks["failure"] = "answers with its kind"
        checks["network"] = _check_offline(program, photo, work / "offline")
        checks["network, window"] = _check_offline(program, photo, work / "offline-edit",
                                                   window=True)
    return {"timings_s": timings, "checks": checks}


def _check_offline(program: Path, photo: Path, out: Path, window: bool = False) -> str:
    """``prepare`` (or the window's self-test) once more with the network closed by the
    system (macOS only)."""
    sandbox = shutil.which("sandbox-exec")
    if sys.platform != "darwin" or sandbox is None:
        return "not checked by the system (no sandbox-exec)"
    command = ["edit", str(photo), "--out", str(out), "--self-test"] if window else [
        "prepare", str(photo), "--out", str(out)]
    run = subprocess.run([sandbox, "-p", NO_NETWORK, str(program), *command],
                         capture_output=True, text=True, check=False, timeout=900,
                         env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    if run.returncode != 0 and not run.stdout.strip():
        return f"not checked by the system (sandbox-exec refused: {run.stderr.strip()[:80]})"
    answer = json.loads(run.stdout)
    assert run.returncode == 0 and answer["ocr_pages"] == [1], answer
    return "read with the network closed by sandbox-exec"


def main() -> int:
    """Build, check, sum up."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--identity", help="macOS signing identity (Developer ID)")
    parser.add_argument("--onedir", action="store_true",
                        help="a folder instead of one file: starts faster (docs/sidecar.md)")
    parser.add_argument("--no-check", action="store_true", help="build only")
    args = parser.parse_args()
    triple = target_triple()
    program = build(f"optdoc-{triple}" + ("-onedir" if args.onedir else ""), args.identity,
                    args.onedir)
    digest = hashlib.sha256(program.read_bytes()).hexdigest()
    program.with_name(program.name + ".sha256").write_text(f"{digest}  {program.name}\n",
                                                          encoding="utf-8")
    carried = program.parent / f"optdoc-{triple}.licences.json"
    carried.write_text(json.dumps({
        "python": licences(),
        "note": "Native libraries inside these packages carry their own licences: OpenCV "
                "brings FFmpeg (LGPL), pillow-heif brings libheif and libde265 (LGPL) and x265 "
                "(GPL 2.0 or later), pypdfium2 brings pdfium (Apache 2.0 and BSD), PySide6 "
                "brings Qt (LGPL 3.0); see each package's licence files.",
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    files = [p for p in program.parent.rglob("*") if p.is_file()] if args.onedir else [program]
    summary: dict[str, object] = {
        "program": str(program.relative_to(ROOT)), "target": triple,
        "size_mb": round(sum(p.stat().st_size for p in files) / 1e6, 1), "sha256": digest,
        "signed": args.identity or "ad hoc" if sys.platform == "darwin" else None,
    }
    if not args.no_check:
        summary.update(check(program))
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
