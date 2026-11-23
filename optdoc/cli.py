"""The command line: ``optdoc readers``, ``optdoc prepare``, ``optdoc edit`` (the window)
and ``optdoc bench``.

Every command answers with exactly one JSON object on standard output, whether it
succeeds or fails, so that programs in any language can call optdoc as a helper (a
Tauri sidecar, for one).  ``docs/interface.md`` describes the answers; they carry the
version of that description as ``interface``.  A failure answers with its kind
(:mod:`optdoc.errors`) and its message in English and German, and ends with exit status
2.  No answer and no message quotes a document or its path, and ``bench`` names no file
at all.  ``--progress`` writes a line of JSON per page to standard error.  ``prepare`` and
``edit`` take a configuration (``--config``) and make the same result from it every time
(:mod:`optdoc.project`).

The command line never goes on the network (:mod:`optdoc.offline`).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import sys
import warnings
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, NoReturn, TextIO

from optdoc import __version__, cleanup, offline, tables
from optdoc import ocr as ocrlib
from optdoc.errors import LANGUAGES, OptdocError
from optdoc.project import SUFFIX, Options, Project, load_config

INTERFACE = 2  # the version of docs/interface.md the answers follow
STATUS_ERROR = 2
_said: TextIO = sys.stderr  # where optdoc's own lines on standard error go (see _own_stderr)


def _heic() -> bool:
    """True when HEIC photos can be opened (pillow-heif installed)."""
    return importlib.util.find_spec("pillow_heif") is not None


def _readers(args: argparse.Namespace) -> dict[str, Any]:
    """What this installation can do."""
    from optdoc import gui

    return {"version": __version__, "readers": ocrlib.available_backends(),
            "clean_up": cleanup.available(), "heic": _heic(), "tables": tables.available(),
            "window": gui.available()}


def _progress(page: int, of: int) -> None:
    """One line of progress on standard error: the page about to be done, of how many."""
    _said.write(json.dumps({"page": page, "of": of}) + "\n")
    _said.flush()


# the options that decide the result; with --config the configuration decides them
_SETTINGS = ("reader", "languages", "paper", "photo", "no_clean_up", "no_tables",
             "no_structure")


def _project(args: argparse.Namespace) -> Project:
    """The project on the file: from its configuration (``--config``, a JSON file or a
    PDF optdoc wrote), or fresh with the options given.  Both at once is a "usage"."""
    if args.config is not None:
        if any(getattr(args, name) is not None for name in _SETTINGS):
            raise OptdocError("usage")
        return Project.open(args.file, config=load_config(args.config))
    options = Options(reader=args.reader or "auto", languages=args.languages,
                      tables=not args.no_tables, paper=args.paper or "a4", photo=args.photo,
                      clean_up=not args.no_clean_up, structure=not args.no_structure)
    return Project.open(args.file, options)


def _out(args: argparse.Namespace) -> Path:
    """The folder for the results: ``--out``, else ``<file>.optdoc`` beside the file."""
    return args.out or args.file.with_name(f"{args.file.stem}.optdoc")


def _results(project: Project, args: argparse.Namespace) -> dict[str, Any]:
    """Make the result of a project, write it, and sum it up."""
    from optdoc import output

    reading = project.build(_progress if args.progress else None)
    try:
        paths = output.write(reading, _out(args), cells=not args.no_cells)
        return {
            **{k: str(v) for k, v in paths.items()},
            "pages": len(reading.pages),
            "ocr_pages": [s.number + 1 for s in reading.pages if s.ocr],
            "pages_without_text": [n + 1 for n in reading.without_text],
            "cleaned_up": [n + 1 for n in sorted(reading.plan)],
            "corrected": [n + 1 for n in project.corrected],
            "reader": reading.reader,
            "tables": (None if reading.tables is None
                       else sum(len(t) for t in reading.tables.values())),
        }
    finally:
        reading.close()


def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Read the file (or make it again from its configuration) and write the results."""
    project = _project(args)
    try:
        return _results(project, args)
    finally:
        project.close()


def _edit(args: argparse.Namespace) -> dict[str, Any]:
    """Open the window on the file; write the results when the person applies, the
    configuration alone when they will continue later, nothing when they cancel."""
    from optdoc import gui

    if not gui.available():
        raise OptdocError("no-gui")
    from optdoc.gui.app import edit

    project = _project(args)
    try:
        outcome = edit(project, language=args.language, self_test=args.self_test)
        if outcome == "cancelled":
            raise OptdocError("cancelled")
        if outcome == "saved":
            saved = project.save(_out(args) / f"{args.file.stem}{SUFFIX}")
            return {"config": str(saved), "finished": False}
        return {**_results(project, args), "finished": True}
    finally:
        project.close()


def _bench(args: argparse.Namespace) -> dict[str, Any]:
    """Score the documents of a bench folder; numbers only."""
    from optdoc.bench import bench, documents_in

    if not args.folder.is_dir():
        raise OptdocError("missing")
    result = bench(args.folder, args.reader, clean_up=not args.no_clean_up).as_dict()
    return {"documents_found": len(documents_in(args.folder)), **result}


class _Parser(argparse.ArgumentParser):
    """An argument parser whose complaints become an answer of kind "usage": the usage
    line goes to standard error, the arguments themselves are never repeated (one of
    them is the path of a document)."""

    def error(self, message: str) -> NoReturn:
        """Show the usage and fail with kind "usage"."""
        self.print_usage(_said)
        raise OptdocError("usage")


def _document_options(pr: argparse.ArgumentParser) -> None:
    """The options of prepare and edit.  The settings default to None, so that the use of
    one beside ``--config`` can be told."""
    pr.add_argument("file", type=Path, help="a PDF or an image (JPEG, PNG, TIFF, HEIC …)")
    pr.add_argument("--out", type=Path, help="folder for the results (default: <file>.optdoc/)")
    pr.add_argument("--config", type=Path,
                    help="configuration to start from: <name>.optdoc.json, or a PDF optdoc wrote")
    pr.add_argument("--reader", choices=["auto", "rapidocr", "tesseract", "none"],
                    help="OCR engine (default: auto)")
    pr.add_argument("--languages", help="language packs: deu+eng for Tesseract, de for RapidOCR")
    pr.add_argument("--paper",
                    help="paper an image is placed on: a4 (default), a5, a3, letter, legal, image")
    kind = pr.add_mutually_exclusive_group()
    kind.add_argument("--photo", dest="photo", action="store_const", const=True,
                      help="take every page without text for a photo: find the sheet, unwarp it")
    kind.add_argument("--scan", dest="photo", action="store_const", const=False,
                      help="take every page for a scan: never unwarp")
    pr.add_argument("--no-clean-up", action="store_const", const=True,
                    help="no automatic clean-up")
    pr.add_argument("--no-tables", action="store_const", const=True,
                    help="no second pass for table grids (Tesseract)")
    pr.add_argument("--no-structure", action="store_const", const=True,
                    help="raw OCR lines, no Markdown")
    pr.add_argument("--no-cells", action="store_true",
                    help="no tables with their cells in the reading (extra 'tables')")
    pr.add_argument("--progress", action="store_true",
                    help='a line {"page": n, "of": m} on standard error per page')


def _parser() -> argparse.ArgumentParser:
    """The argument parser."""
    p = _Parser(prog="optdoc", description="Make photographed and scanned documents legible.")
    p.add_argument("--version", action="version", version=f"optdoc {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("readers", help="list the OCR engines and abilities of this installation")
    pr = sub.add_parser("prepare", help="clean up a document, read it and write the results")
    _document_options(pr)
    ed = sub.add_parser("edit", help="open the window: clean up by eye, correct the text")
    _document_options(ed)
    ed.add_argument("--language", choices=["de", "en"],
                    help="language of the window (default: the system's)")
    ed.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    be = sub.add_parser("bench", help="score readings against truth files (numbers only)")
    be.add_argument("folder", type=Path, help="documents with a <name>.truth.txt next to each")
    be.add_argument("--reader", action="append", choices=["rapidocr", "tesseract"],
                    help="engine to score; repeatable (default: every installed engine)")
    be.add_argument("--no-clean-up", action="store_true", help="no automatic clean-up")
    return p


COMMANDS: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "readers": _readers, "prepare": _prepare, "edit": _edit, "bench": _bench}


def _failure(error: OptdocError) -> dict[str, Any]:
    """The answer for a failure: its kind, its details, its message in every language."""
    return {"error": error.kind, "details": error.details,
            "message": {language: error.message(language) for language in LANGUAGES}}


def _quiet() -> None:
    """Keep standard error for the progress lines: no warnings of the libraries, and no
    messages of MuPDF, which may name the file it failed on."""
    import pymupdf

    warnings.simplefilter("ignore")
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)


@contextlib.contextmanager
def _own_stderr() -> Iterator[TextIO]:
    """Standard error for optdoc's own lines only.  Libraries write to it below Python, where
    no setting reaches them (ONNX Runtime warned about PCI buses on Linux, in colour); for
    the time of a command the descriptor points at the null device, and optdoc's lines go
    through a copy of the real one, which is put back afterwards."""
    sys.stderr.flush()
    try:
        kept = os.dup(2)
    except OSError:  # no standard error to begin with
        yield sys.stderr
        return
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 2)
    os.close(null)
    stream = os.fdopen(os.dup(kept), "w", encoding="utf-8", errors="replace")
    try:
        yield stream
    finally:
        stream.close()
        sys.stderr.flush()
        os.dup2(kept, 2)
        os.close(kept)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status."""
    global _said
    offline.no_telemetry()
    offline.forbid_network()
    _quiet()
    try:
        with _own_stderr() as _said:
            try:
                args = _parser().parse_args(argv)
                answer, status = COMMANDS[args.command](args), 0
            except OptdocError as error:
                answer, status = _failure(error), STATUS_ERROR
            except Exception as error:  # a fault of optdoc: its message might quote a document
                answer = _failure(OptdocError("internal", error=type(error).__name__))
                status = STATUS_ERROR
    finally:  # --help and --version leave by SystemExit
        _said = sys.stderr
    head = {"interface": INTERFACE, "made_with": f"optdoc {__version__}"}
    json.dump({**head, **answer}, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return status
