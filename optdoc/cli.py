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

from optdoc import __version__
from optdoc import aufbereitung as aufmodul
from optdoc import ocr as ocrmodul

_LESER = {"auto": "auto", "rapidocr": "rapidocr", "tesseract": "tesseract", "none": "aus"}


def _heic() -> bool:
    """True when HEIC photos can be opened (pillow-heif installed)."""
    try:
        import pillow_heif  # noqa: F401
    except ImportError:
        return False
    return True


def _readers() -> dict[str, object]:
    """What this installation can do."""
    return {"version": __version__, "readers": ocrmodul.verfuegbare_backends(),
            "clean_up": aufmodul.verfuegbar(), "heic": _heic()}


def _plan(pfad: Path | None) -> dict[int, aufmodul.Aufbereitung] | None:
    """A clean-up plan from JSON keyed by page number (from 1), as ``prepare`` writes it."""
    if pfad is None:
        return None
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    return {int(n) - 1: aufmodul.Aufbereitung.aus_dict(a) for n, a in roh.items()}


def _prepare(args: argparse.Namespace) -> dict[str, object]:
    """Read the file and write the results; returns their paths and a summary."""
    from optdoc import ausgabe
    from optdoc.lesen import lies

    quelle: Path = args.file
    if not quelle.is_file():
        raise FileNotFoundError(f"no such file: {quelle}")
    ordner = args.out or quelle.with_name(f"{quelle.stem}.optdoc")
    papier = None if args.paper.lower() in ("image", "bild") else args.paper
    lesung = lies(quelle, leser=_LESER[args.reader], sprachen=args.languages,
                  tabellen=not args.no_tables, papier=papier, plan=_plan(args.plan),
                  aufbereiten=not args.no_clean_up, gliedern=not args.no_structure)
    try:
        pfade = ausgabe.schreibe(lesung, ordner)
        return {
            **{k: str(v) for k, v in pfade.items()},
            "pages": len(lesung.seiten),
            "ocr_pages": [s.nummer + 1 for s in lesung.seiten if s.ocr],
            "pages_without_text": [n + 1 for n in lesung.ohne_text],
            "cleaned_up": [n + 1 for n in sorted(lesung.plan)],
            "reader": lesung.leser,
        }
    finally:
        lesung.schliessen()


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
    pr.add_argument("--reader", choices=sorted(_LESER), default="auto", help="OCR engine")
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
        ergebnis = _readers() if args.command == "readers" else _prepare(args)
    except (OSError, ValueError, ocrmodul.OCRFehler) as fehler:
        print(f"optdoc: {fehler}", file=sys.stderr)
        return 2
    json.dump(ergebnis, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return 0
