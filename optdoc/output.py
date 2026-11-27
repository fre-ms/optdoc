"""What a preparation leaves behind: the PDF of the prepared pages, and the configuration
document that makes it again (:mod:`optdoc.project`).

The PDF has every page upright: a page a plan changed shows the prepared image (in its
colours as JPEG, a page without colour in grey as PNG), any other page is as it came.
It carries no time, a file identifier made from its configuration document, and that
document as an embedded file (``optdoc.json``) without dates, so that the same input and
document give the same bytes, and the steps after optdoc (ocrdoc) find the frames of its
pages there.  It has no text layer: reading the pages is ocrdoc's step.
"""

from __future__ import annotations

from pathlib import Path

from doccor import documents

from optdoc import __version__
from optdoc.errors import OptdocError
from optdoc.project import EMBEDDED, SUFFIX, Prepared, config_bytes


def pdf_bytes(prepared: Prepared) -> bytes:
    """The prepared document as a PDF, carrying its configuration document; the same
    input and document give the same bytes."""
    import pymupdf

    duplicate = pymupdf.open("pdf", prepared.doc.tobytes())
    try:
        if EMBEDDED in duplicate.embfile_names():
            duplicate.embfile_del(EMBEDDED)  # an input optdoc wrote before: its own goes
        config = config_bytes(prepared.config)
        documents.embed(duplicate, EMBEDDED, config,
                        "optdoc configuration: prepares this PDF again from the original")
        return documents.finished_pdf(duplicate, [config], f"optdoc {__version__}")
    finally:
        duplicate.close()


def write(prepared: Prepared, folder: str | Path, stem: str | None = None) -> dict[str, Path]:
    """Write ``<stem>.pdf`` and the configuration document ``<stem>.optdoc.json`` into
    ``folder`` (created when missing); returns the paths by kind: "document" (the prepared
    document) and "config".  Nothing is written anywhere else.  Raises "same-as-source"
    when the PDF would replace the document that was prepared, "unwritable" when the
    folder cannot take the files."""
    target = Path(folder)
    stem = stem or prepared.source.stem
    paths = {"document": target / f"{stem}.pdf", "config": target / f"{stem}{SUFFIX}"}
    if paths["document"].resolve() == prepared.source.resolve():
        raise OptdocError("same-as-source")
    pdf = pdf_bytes(prepared)
    try:
        target.mkdir(parents=True, exist_ok=True)
        paths["document"].write_bytes(pdf)
        paths["config"].write_bytes(config_bytes(prepared.config))
    except OSError as e:
        raise OptdocError("unwritable") from e
    return paths
