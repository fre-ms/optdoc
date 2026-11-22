"""The reading pipeline: open a file, clean up its image-only pages, read every page
(its text layer, or OCR where there is none) and give the OCR text its structure.

A page with a text layer is read as it is.  A page without one (a scan, a photo) gets
the clean-up plan: the one given, else the automatic suggestion of
:func:`optdoc.aufbereitung.vorschlag`.  The cleaned-up image replaces the page, so that
OCR, the output and anything a caller does afterwards (redaction, for instance) see
the same page.  Upscaling is not baked into the page; such pages are read by OCR at
the higher resolution instead.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from optdoc import aufbereitung as aufmodul
from optdoc import ocr as ocrmodul
from optdoc.gliederung import Gliederung, gliedere_seite
from optdoc.laden import BILDENDUNGEN, HEIC_ENDUNGEN, oeffne
from optdoc.textebene import Seitentext, lese_seite

VORSCHLAG_DPI = 150  # resolution the clean-up suggestion looks at a page with
MAX_PIXEL_HOCHSKALIERT = 9000  # cap for the OCR image of an upscaled page


def ist_foto(pfad: str | Path) -> bool:
    """True for an image file (photo, scan as JPEG, PNG, HEIC) rather than a PDF."""
    return Path(pfad).suffix.lower() in BILDENDUNGEN | HEIC_ENDUNGEN


def vorschlag_fuer(page: pymupdf.Page, foto: bool) -> aufmodul.Aufbereitung:
    """The automatic clean-up suggestion for one image-only page."""
    bild, skala = aufmodul.rendere(page, VORSCHLAG_DPI)
    return aufmodul.vorschlag(bild, foto, skala, aufmodul.native_dpi(page))


def plan_fuer(doc: pymupdf.Document, foto: bool) -> dict[int, aufmodul.Aufbereitung]:
    """The suggestions for the image-only pages of ``doc``, active ones only; empty
    without OpenCV."""
    if not aufmodul.verfuegbar():
        return {}
    plan: dict[int, aufmodul.Aufbereitung] = {}
    for i, page in enumerate(doc):
        if lese_seite(page, i).hat_textebene:
            continue
        a = vorschlag_fuer(page, foto)
        if a.aktiv:
            plan[i] = a
    return plan


@dataclass
class Seite:
    """One page as read: its text (with a box for every character), whether that text
    came from OCR, and the structure of an OCR text."""

    nummer: int
    text: Seitentext
    ocr: bool
    gliederung: Gliederung | None = None

    @property
    def markdown(self) -> str:
        """The page text as Markdown where it has a structure, else as it is."""
        return self.gliederung.rendere(self.text.text) if self.gliederung else self.text.text


@dataclass
class Lesung:
    """A read document: the cleaned-up document, the plan that was applied, the pages,
    and the OCR engine used (None without one).  Call :meth:`schliessen` when done."""

    quelle: Path
    doc: pymupdf.Document
    plan: dict[int, aufmodul.Aufbereitung]
    seiten: list[Seite] = field(default_factory=list)
    leser: str | None = None

    @property
    def ohne_text(self) -> list[int]:
        """Pages that hold no text at all after reading (no text layer and no OCR)."""
        return [s.nummer for s in self.seiten if not s.text.text.strip()]

    def schliessen(self) -> None:
        """Close the document."""
        self.doc.close()


def lies_seite(page: pymupdf.Page, leser: ocrmodul.OCRBackend,
               plan: aufmodul.Aufbereitung | None = None, nummer: int | None = None,
               dpi: int = ocrmodul.OCR_DPI) -> Seitentext:
    """OCR of one page at the resolution and with the finish its plan asks for: an
    upscaled page is read at that multiple of ``dpi`` (capped), a page in letter mode
    gets the letter-aware finish before the engine."""
    faktor = max(1, plan.hochskalieren) if plan is not None else 1
    filter_ = (functools.partial(aufmodul.textverfeinerung, faktor=faktor)
               if plan is not None and plan.textmodus else None)
    return ocrmodul.erkenne_seite(
        page, leser, nummer, dpi=dpi * faktor,
        max_pixel=min(ocrmodul.MAX_PIXEL * faktor, MAX_PIXEL_HOCHSKALIERT), filter_=filter_)


def _lies(doc: pymupdf.Document, nummer: int, leser: ocrmodul.OCRBackend | None,
          plan: aufmodul.Aufbereitung | None, dpi: int, gliedern: bool) -> Seite:
    """One page: its text layer where that suffices, else its OCR with structure."""
    page = doc[nummer]
    ebene = lese_seite(page, nummer)
    if leser is None or not ocrmodul.braucht_ocr(page, ebene):
        return Seite(nummer, ebene, False)
    text = lies_seite(page, leser, plan, nummer, dpi)
    return Seite(nummer, text, True, gliedere_seite(page, text) if gliedern else None)


def lies(
    pfad: str | Path,
    leser: str = "auto",
    sprachen: str | None = None,
    tabellen: bool = True,
    papier: str | None = "a4",
    plan: dict[int, aufmodul.Aufbereitung] | None = None,
    aufbereiten: bool = True,
    dpi: int = ocrmodul.OCR_DPI,
    gliedern: bool = True,
) -> Lesung:
    """Read a PDF or an image.

    ``leser`` is the OCR engine ("auto", "rapidocr", "tesseract", "aus"), ``sprachen``
    its language packs, ``tabellen`` Tesseract's second pass for table grids, ``papier``
    the paper size an image is placed on (``None`` keeps the image's own size).  ``plan``
    is the clean-up per page number; without it the automatic suggestion is used, unless
    ``aufbereiten`` is False.  ``gliedern`` gives OCR pages their structure."""
    quelle = Path(pfad)
    engine = ocrmodul.backend(leser, sprachen, tabellen=tabellen)
    doc = oeffne(quelle, papier)
    try:
        if plan is None:
            plan = plan_fuer(doc, ist_foto(quelle)) if aufbereiten else {}
        plan = {n: a for n, a in plan.items() if a.aktiv and 0 <= n < len(doc)}
        for nummer in sorted(plan):
            aufmodul.seite_ersetzen(doc, nummer, plan[nummer], dpi)
        seiten = [_lies(doc, i, engine, plan.get(i), dpi, gliedern) for i in range(len(doc))]
    except Exception:
        doc.close()
        raise
    return Lesung(quelle, doc, plan, seiten, engine.name if engine else None)
