"""The command line: ``optdoc about``, ``optdoc run`` and ``optdoc edit`` (the window).

Every command answers with exactly one JSON object on standard output, whether it
succeeds or fails, so that programs in any language can call optdoc as a helper.
``docs/interface.md`` describes the answers; they carry the version of that description
as ``interface``.  A failure answers with its kind (:mod:`optdoc.errors`) and its message
in English and German, and ends with exit status 2.  No answer and no message quotes a
document or its path.  ``--progress`` writes a line of JSON per page to standard error.
``run`` and ``edit`` take a configuration document (``--config``) and make the same
result from it every time (:mod:`optdoc.project`).

The command line keeps the manners every tool of docrepro keeps (:mod:`doccor.cli`): one
JSON answer whatever happens, standard error for its own lines, and never the network
(:mod:`doccor.offline`).
"""

from __future__ import annotations

import argparse
import importlib.util
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from doccor import cli as frame

from optdoc import __version__, cleanup
from optdoc.errors import OptdocError
from optdoc.project import SUFFIX, Options, Project, load_config

INTERFACE = 3  # the version of docs/interface.md the answers follow
TOOL = "optdoc"


def _about(args: argparse.Namespace) -> dict[str, Any]:
    """What this installation can do."""
    from optdoc import gui

    return {"version": __version__, "clean_up": cleanup.available(),
            "heic": importlib.util.find_spec("pillow_heif") is not None,
            "window": gui.available(),
            "upside_down": importlib.util.find_spec("ocrdoc") is not None}


# the options that decide the result; with --config the configuration decides them
_SETTINGS = ("paper", "photo", "no_clean_up", "colour_pages")


def _project(args: argparse.Namespace) -> Project:
    """The project on the file: from its configuration document (``--config``, a JSON
    file or a PDF optdoc wrote), or fresh with the options given.  Both at once is a
    "usage"."""
    if args.config is not None:
        if any(getattr(args, name) is not None for name in _SETTINGS):
            raise OptdocError("usage")
        return Project.open(args.file, config=load_config(args.config))
    options = Options(paper=args.paper or "a4", photo=args.photo,
                      clean_up=not args.no_clean_up,
                      colour_pages=args.colour_pages or cleanup.COLOUR_PAGES[0])
    return Project.open(args.file, options)


def _out(args: argparse.Namespace) -> Path:
    """The folder for the results: ``--out``, else ``<file>.optdoc`` beside the file."""
    return args.out or args.file.with_name(f"{args.file.stem}.optdoc")


def _results(project: Project, args: argparse.Namespace) -> dict[str, Any]:
    """Make the result of a project, write it, and sum it up."""
    from optdoc import output

    prepared = project.build(frame.progress if args.progress else None)
    try:
        paths = output.write(prepared, _out(args))
        return {
            **{k: str(v) for k, v in paths.items()},
            "pages": len(project.pages),
            "cleaned_up": [n + 1 for n in prepared.cleaned_up],
            "unwarped": [n + 1 for n in prepared.unwarped],
            "decided": [n + 1 for n in project.decided_by_person],
        }
    finally:
        prepared.close()


def _run(args: argparse.Namespace) -> dict[str, Any]:
    """Prepare the file (or prepare it again from its configuration) and write the
    results."""
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


def _document_options(pr: argparse.ArgumentParser) -> None:
    """The options of run and edit.  The settings default to None, so that the use of one
    beside ``--config`` can be told."""
    pr.add_argument("file", type=Path, help="a photo, an image (JPEG, PNG, TIFF, HEIC …) or a PDF")
    pr.add_argument("--out", type=Path, help="folder for the results (default: <file>.optdoc/)")
    pr.add_argument("--config", type=Path,
                    help="configuration to start from: <name>.optdoc.json, or a PDF optdoc wrote")
    pr.add_argument("--paper",
                    help="paper an image is placed on: a4 (default), a5, a3, letter, legal, image")
    kind = pr.add_mutually_exclusive_group()
    kind.add_argument("--photo", dest="photo", action="store_const", const=True,
                      help="take every page without text for a photo: find the sheet, unwarp it")
    kind.add_argument("--scan", dest="photo", action="store_const", const=False,
                      help="take every page for a scan: never unwarp")
    pr.add_argument("--no-clean-up", action="store_const", const=True,
                    help="leave the pages as they came unless a person prepares them")
    pr.add_argument("--colour-pages", choices=list(cleanup.COLOUR_PAGES),
                    help="how a page in colour is stored: jpeg (default, quality 92) or png "
                         "(lossless, some ten times the size)")
    pr.add_argument("--progress", action="store_true",
                    help='a line {"page": n, "of": m} on standard error per page')


def _parser() -> argparse.ArgumentParser:
    """The argument parser."""
    p = frame.Parser(prog=TOOL, description="Make photographed and scanned pages faithful: "
                                            "upright, unwarped, evenly lit, in their colours.")
    p.add_argument("--version", action="version", version=f"{TOOL} {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("about", help="what this installation can do")
    ru = sub.add_parser("run", help="prepare a document and write the results")
    _document_options(ru)
    ed = sub.add_parser("edit", help="open the window: prepare the pages by eye")
    _document_options(ed)
    ed.add_argument("--language", choices=["de", "en"],
                    help="language of the window (default: the system's)")
    ed.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return p


COMMANDS: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "about": _about, "run": _run, "edit": _edit}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status."""
    return frame.main(_parser(), COMMANDS, tool=TOOL, version=__version__,
                      interface=INTERFACE, argv=argv)
