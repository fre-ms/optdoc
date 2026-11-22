"""What a reading leaves behind: a searchable PDF, the reading as JSON, the text as
Markdown, and the clean-up plan that can make it again.

The PDF is the cleaned-up document; every OCR word is laid invisibly (render mode 3)
over the place where it is printed, so that a reader can search and select the text
of a scan like that of a born-digital document.  The JSON names every word with its
box in page points and the engine's confidence; it is meant for programs in other
languages (a records app, a laboratory reader) and says which version of optdoc and
which engine made it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf

from optdoc import __version__
from optdoc.lesen import Lesung, Seite
from optdoc.textebene import Seitentext

FORMAT = "optdoc-reading"
FORMAT_VERSION = 1
SCHRIFT = "helv"


def _wortkasten(seite: Seitentext, a: int, b: int) -> pymupdf.Rect | None:
    """The union of the boxes of ``seite.text[a:b]``, or None without boxes."""
    kaesten = seite.rects(a, b)
    if not kaesten:
        return None
    wort = pymupdf.Rect(kaesten[0])
    for r in kaesten[1:]:
        wort |= r
    return wort


def _unsichtbare_groesse(text: str, rect: pymupdf.Rect) -> float:
    """The font size that makes ``text`` as wide as its box, so that selecting it in a
    reader covers the printed word; capped a little above the box height."""
    nach_hoehe = max(2.0, rect.height * 0.8)
    einheit = pymupdf.get_text_length(text, fontname=SCHRIFT, fontsize=1.0)
    groesse = min(nach_hoehe * 1.15, rect.width / einheit) if einheit > 0 else nach_hoehe
    return max(2.0, groesse)


def _schreibe_unsichtbar(page: pymupdf.Page, text: str, rect: pymupdf.Rect) -> bool:
    """Write ``text`` invisibly over ``rect``; a glyph the base font lacks is replaced by
    what it can encode.  False when there is nothing to write."""
    if rect.is_empty or rect.height <= 0 or not text.strip():
        return False
    punkt = (rect.x0, rect.y1 - 0.22 * rect.height)
    groesse = _unsichtbare_groesse(text, rect)
    try:
        page.insert_text(punkt, text, fontsize=groesse, fontname=SCHRIFT, render_mode=3,
                         overlay=True)
    except Exception:
        ersatz = text.encode("cp1252", "replace").decode("cp1252")
        page.insert_text(punkt, ersatz, fontsize=groesse, fontname=SCHRIFT, render_mode=3,
                         overlay=True)
    return True


def unsichtbare_textebene(page: pymupdf.Page, seite: Seitentext) -> int:
    """Lay the words of ``seite`` invisibly onto ``page`` where they stand; returns the
    number of words written."""
    anzahl = 0
    for a, b in seite.woerter():
        kasten = _wortkasten(seite, a, b)
        if kasten is not None and _schreibe_unsichtbar(page, seite.text[a:b], kasten):
            anzahl += 1
    return anzahl


def _woerter(seite: Seitentext) -> list[dict[str, Any]]:
    """The words of a page with their boxes and, for OCR, the engine's confidence."""
    konfidenzen = seite.konfidenzen if len(seite.konfidenzen) == len(seite.woerter()) else []
    woerter = []
    for i, (a, b) in enumerate(seite.woerter()):
        kasten = _wortkasten(seite, a, b)
        wort: dict[str, Any] = {"text": seite.text[a:b], "start": a, "end": b,
                                "box": [round(v, 2) for v in kasten] if kasten else None}
        if konfidenzen:
            wort["confidence"] = round(konfidenzen[i], 3)
        woerter.append(wort)
    return woerter


def _seite_als_dict(s: Seite) -> dict[str, Any]:
    """One page of the reading."""
    return {
        "page": s.nummer + 1,
        "width": round(s.text.breite, 2),
        "height": round(s.text.hoehe, 2),
        "source": "ocr" if s.ocr else "text",
        "text": s.text.text,
        "markdown": s.markdown,
        "words": _woerter(s.text),
    }


def plan_als_dict(lesung: Lesung) -> dict[str, Any]:
    """The clean-up plan by page number (counted from 1), every switch and corner."""
    return {str(n + 1): a.vollstaendig() for n, a in sorted(lesung.plan.items())}


def lesung_als_dict(lesung: Lesung) -> dict[str, Any]:
    """The reading as a JSON-ready dictionary."""
    return {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "made_with": f"optdoc {__version__}",
        "reader": lesung.leser,
        "source": lesung.quelle.name,
        "plan": plan_als_dict(lesung),
        "pages": [_seite_als_dict(s) for s in lesung.seiten],
    }


def markdown(lesung: Lesung) -> str:
    """The text of all pages as Markdown, a heading per page."""
    teile = [f"## Page {s.nummer + 1}\n\n{s.markdown.strip()}\n" for s in lesung.seiten]
    return "\n".join(teile)


def durchsuchbares_pdf(lesung: Lesung) -> bytes:
    """The cleaned-up document with an invisible text layer on every OCR page."""
    kopie = pymupdf.open("pdf", lesung.doc.tobytes())
    try:
        for s in lesung.seiten:
            if s.ocr:
                unsichtbare_textebene(kopie[s.nummer], s.text)
        kennung = f"optdoc {__version__}"
        kopie.set_metadata({"producer": kennung, "creator": kennung})
        return kopie.tobytes(garbage=3, deflate=True)
    finally:
        kopie.close()


def schreibe(lesung: Lesung, ordner: str | Path, stamm: str | None = None) -> dict[str, Path]:
    """Write ``<stamm>.pdf``, ``<stamm>.reading.json``, ``<stamm>.md`` and
    ``<stamm>.plan.json`` into ``ordner`` (created when missing); returns the paths."""
    ziel = Path(ordner)
    ziel.mkdir(parents=True, exist_ok=True)
    stamm = stamm or lesung.quelle.stem
    pfade = {
        "pdf": ziel / f"{stamm}.pdf",
        "reading": ziel / f"{stamm}.reading.json",
        "markdown": ziel / f"{stamm}.md",
        "plan": ziel / f"{stamm}.plan.json",
    }
    if pfade["pdf"].resolve() == lesung.quelle.resolve():
        raise ValueError(f"the output would overwrite the source: {lesung.quelle}")
    pfade["pdf"].write_bytes(durchsuchbares_pdf(lesung))
    pfade["reading"].write_text(json.dumps(lesung_als_dict(lesung), ensure_ascii=False, indent=1),
                                encoding="utf-8")
    pfade["markdown"].write_text(markdown(lesung), encoding="utf-8")
    pfade["plan"].write_text(json.dumps(plan_als_dict(lesung), indent=1), encoding="utf-8")
    return pfade
