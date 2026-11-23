"""The command line: ``optdoc readers``, ``optdoc prepare`` and ``optdoc bench``.

Every command answers with exactly one JSON object on standard output, whether it
succeeds or fails, so that programs in any language can call optdoc as a helper (a
Tauri sidecar, for one).  ``docs/interface.md`` describes the answers; they carry the
version of that description as ``interface``.  A failure answers with its kind
(:mod:`optdoc.errors`) and its message in English and German, and ends with exit status
2.  No answer and no message quotes a document or its path, and ``bench`` names no file
at all.  ``prepare --progress`` writes a line of JSON per page to standard error.

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

from optdoc import __version__, cleanup, offline
from optdoc import ocr as ocrlib
from optdoc.errors import LANGUAGES, OptdocError

INTERFACE = 1  # the version of docs/interface.md the answers follow
STATUS_ERROR = 2
_said: TextIO = sys.stderr  # where optdoc's own lines on standard error go (see _own_stderr)


def _heic() -> bool:
    """True when HEIC photos can be opened (pillow-heif installed)."""
    return importlib.util.find_spec("pillow_heif") is not None


def _readers(args: argparse.Namespace) -> dict[str, Any]:
    """What this installation can do."""
    return {"version": __version__, "readers": ocrlib.available_backends(),
            "clean_up": cleanup.available(), "heic": _heic()}


def _plan(path: Path | None) -> dict[int, cleanup.CleanupPlan] | None:
    """A clean-up plan from JSON keyed by page number (from 1), as ``prepare`` writes it."""
    if path is None:
        return None
    if not path.is_file():
        raise OptdocError("missing")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        pages = {int(n) - 1: a for n, a in raw.items()}
    except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
        raise OptdocError("bad-plan", reason="json") from e
    return {n: cleanup.CleanupPlan.from_dict(a) for n, a in pages.items()}


def _progress(page: int, of: int) -> None:
    """One line of progress on standard error: the page about to be done, of how many."""
    _said.write(json.dumps({"page": page, "of": of}) + "\n")
    _said.flush()


def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Read the file and write the results; returns their paths and a summary."""
    from optdoc import output
    from optdoc.reading import read

    source: Path = args.file
    reading = read(source, reader=args.reader, languages=args.languages,
                   tables=not args.no_tables, paper=args.paper, plan=_plan(args.plan),
                   clean_up=not args.no_clean_up, with_structure=not args.no_structure,
                   photo=args.photo, progress=_progress if args.progress else None)
    try:
        paths = output.write(reading, args.out or source.with_name(f"{source.stem}.optdoc"))
        return {
            **{k: str(v) for k, v in paths.items()},
            "pages": len(reading.pages),
            "ocr_pages": [s.number + 1 for s in reading.pages if s.ocr],
            "pages_without_text": [n + 1 for n in reading.without_text],
            "cleaned_up": [n + 1 for n in sorted(reading.plan)],
            "reader": reading.reader,
        }
    finally:
        reading.close()


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


def _parser() -> argparse.ArgumentParser:
    """The argument parser."""
    p = _Parser(prog="optdoc", description="Make photographed and scanned documents legible.")
    p.add_argument("--version", action="version", version=f"optdoc {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("readers", help="list the OCR engines and abilities of this installation")
    pr = sub.add_parser("prepare", help="clean up a document, read it and write the results")
    pr.add_argument("file", type=Path, help="a PDF or an image (JPEG, PNG, TIFF, HEIC …)")
    pr.add_argument("--out", type=Path, help="folder for the results (default: <file>.optdoc/)")
    pr.add_argument("--reader", choices=["auto", "rapidocr", "tesseract", "none"],
                    default="auto", help="OCR engine")
    pr.add_argument("--languages", help="language packs: deu+eng for Tesseract, de for RapidOCR")
    pr.add_argument("--paper", default="a4",
                    help="paper an image is placed on: a4, a5, a3, letter, legal, or image")
    pr.add_argument("--plan", type=Path, help="clean-up plan (JSON), as written by prepare")
    kind = pr.add_mutually_exclusive_group()
    kind.add_argument("--photo", dest="photo", action="store_const", const=True,
                      help="take every page without text for a photo: find the sheet, unwarp it")
    kind.add_argument("--scan", dest="photo", action="store_const", const=False,
                      help="take every page for a scan: never unwarp")
    pr.add_argument("--no-clean-up", action="store_true", help="no automatic clean-up")
    pr.add_argument("--no-tables", action="store_true", help="no second pass for table grids")
    pr.add_argument("--no-structure", action="store_true", help="raw OCR lines, no Markdown")
    pr.add_argument("--progress", action="store_true",
                    help='a line {"page": n, "of": m} on standard error per page')
    be = sub.add_parser("bench", help="score readings against truth files (numbers only)")
    be.add_argument("folder", type=Path, help="documents with a <name>.truth.txt next to each")
    be.add_argument("--reader", action="append", choices=["rapidocr", "tesseract"],
                    help="engine to score; repeatable (default: every installed engine)")
    be.add_argument("--no-clean-up", action="store_true", help="no automatic clean-up")
    return p


COMMANDS: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "readers": _readers, "prepare": _prepare, "bench": _bench}


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
