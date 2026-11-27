"""What a preparation leaves behind: the prepared document in the type it came in, and
the configuration document that makes it again (:mod:`optdoc.project`).

A picture stays a picture (:mod:`optdoc.pictures`): ``<stem>.jpg`` for a JPEG, and so on,
with the configuration document beside it, since a picture has no place for it.

A PDF has every page upright: a page a plan changed shows the prepared image (in its
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

    assert prepared.doc is not None, "a picture is written as a picture, not as a PDF"
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
    """Write the prepared document (``<stem>.pdf``, or a picture under the ending it came
    with) and the configuration document ``<stem>.optdoc.json`` into ``folder`` (created
    when missing); returns the paths by kind: "document" and "config".  Nothing is written
    anywhere else.  Raises "same-as-source" when the result would replace the document
    that was prepared, "unwritable" when the folder cannot take the files."""
    target = Path(folder)
    stem = stem or prepared.source.stem
    suffix = ".pdf" if prepared.picture is None else prepared.source.suffix
    paths = {"document": target / f"{stem}{suffix}", "config": target / f"{stem}{SUFFIX}"}
    if paths["document"].resolve() == prepared.source.resolve():
        raise OptdocError("same-as-source")
    data = pdf_bytes(prepared) if prepared.picture is None else prepared.picture
    try:
        target.mkdir(parents=True, exist_ok=True)
        paths["document"].write_bytes(data)
        paths["config"].write_bytes(config_bytes(prepared.config))
    except OSError as e:
        raise OptdocError("unwritable") from e
    return paths
