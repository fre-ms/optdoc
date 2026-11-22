"""The command line: ``optdoc readers`` and ``optdoc prepare``.

Both answer in JSON on standard output, so that programs in any language can call
optdoc as a helper.  Errors go to standard error and end with exit status 2; they
never quote the document.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from optdoc import __version__, cleanup
from optdoc import ocr as ocrlib

_READERS = {"auto": "auto", "rapidocr": "rapidocr", "tesseract": "tesseract", "none": "none"}


def _heic() -> bool:
    """True when HEIC photos can be opened (pillow-heif installed)."""
    try:
        import pillow_heif  # noqa: F401
    except ImportError:
        return False
    return True


def _readers() -> dict[str, object]:
    """What this installation can do."""
    return {"version": __version__, "readers": ocrlib.available_backends(),
            "clean_up": cleanup.available(), "heic": _heic()}


def _plan(path: Path | None) -> dict[int, cleanup.CleanupPlan] | None:
    """A clean-up plan from JSON keyed by page number (from 1), as ``prepare`` writes it."""
    if path is None:
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(n) - 1: cleanup.CleanupPlan.from_dict(a) for n, a in raw.items()}


def _prepare(args: argparse.Namespace) -> dict[str, object]:
    """Read the file and write the results; returns their paths and a summary."""
    from optdoc import output
    from optdoc.reading import read

    source: Path = args.file
    if not source.is_file():
        raise FileNotFoundError(f"no such file: {source}")
    folder = args.out or source.with_name(f"{source.stem}.optdoc")
    paper = None if args.paper.lower() in ("image", "image") else args.paper
    reading = read(source, reader=_READERS[args.reader], languages=args.languages,
                  tables=not args.no_tables, paper=paper, plan=_plan(args.plan),
                  clean_up=not args.no_clean_up, with_structure=not args.no_structure)
    try:
        paths = output.write(reading, folder)
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


def _parser() -> argparse.ArgumentParser:
    """The argument parser."""
    p = argparse.ArgumentParser(
        prog="optdoc", description="Make photographed and scanned documents legible.")
    p.add_argument("--version", action="version", version=f"optdoc {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("readers", help="list the OCR engines and abilities of this installation")
    pr = sub.add_parser("prepare", help="clean up a document, read it and write the results")
    pr.add_argument("file", type=Path, help="a PDF or an image (JPEG, PNG, TIFF, HEIC …)")
    pr.add_argument("--out", type=Path, help="folder for the results (default: <file>.optdoc/)")
    pr.add_argument("--reader", choices=sorted(_READERS), default="auto", help="OCR engine")
    pr.add_argument("--languages", help="language packs: deu+eng for Tesseract, de for RapidOCR")
    pr.add_argument("--paper", default="a4",
                    help="paper an image is placed on: a4, a5, a3, letter, legal, or image")
    pr.add_argument("--plan", type=Path, help="clean-up plan (JSON), as written by prepare")
    pr.add_argument("--no-clean-up", action="store_true", help="no automatic clean-up")
    pr.add_argument("--no-tables", action="store_true", help="no second pass for table grids")
    pr.add_argument("--no-structure", action="store_true", help="raw OCR lines, no Markdown")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status."""
    args = _parser().parse_args(argv)
    try:
        result = _readers() if args.command == "readers" else _prepare(args)
    except (OSError, ValueError, ocrlib.OCRError) as error:
        print(f"optdoc: {error}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return 0
