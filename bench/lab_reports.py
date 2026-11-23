"""Invented laboratory reports for the test bench: print them, photograph them the way
real reports arrive, and let ``optdoc bench`` measure the readings.

    uv run python bench/lab_reports.py <folder> [count] [seed]

writes ``lab-01.pdf`` … and next to each ``lab-01.truth.txt`` (one line per result, as
printed) and ``lab-01.cells.json`` (the cells of each result's row, as printed, for the
table figures).  Save the photo of ``lab-01.pdf`` as ``lab-01.jpg`` (or .heic, .png) in the same
folder; the bench pairs a photo with the truth file of the same name.  Everything here is
made up: the laboratory, the patient, the values.

Three layouts, as laboratories print them: a ruled grid, open columns, and two blocks
(blood count and chemistry) with a flag column.  Values have decimal commas, some carry
a comparator (< 0,5), some are flagged H or L against their range.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pymupdf

# name, unit, low, high, decimals; low None for "< high", high None for "> low"
ANALYTES = [
    ("Natrium", "mmol/l", 135, 145, 0), ("Kalium", "mmol/l", 3.5, 5.1, 1),
    ("Calcium", "mmol/l", 2.15, 2.55, 2), ("Kreatinin", "mg/dl", 0.5, 0.9, 2),
    ("eGFR (CKD-EPI)", "ml/min/1,73m²", 60, None, 0), ("Harnstoff", "mg/dl", 17, 43, 0),
    ("GOT (AST)", "U/l", None, 35, 0), ("GPT (ALT)", "U/l", None, 35, 0),
    ("Gamma-GT", "U/l", None, 40, 0), ("Bilirubin gesamt", "mg/dl", None, 1.2, 1),
    ("CRP", "mg/l", None, 5.0, 1), ("TSH basal", "µU/ml", 0.27, 4.2, 2),
    ("fT4", "ng/dl", 0.93, 1.7, 2), ("HbA1c", "%", 4.0, 5.6, 1),
    ("Glukose nüchtern", "mg/dl", 70, 99, 0), ("Cholesterin gesamt", "mg/dl", None, 200, 0),
    ("LDL-Cholesterin", "mg/dl", None, 116, 0), ("HDL-Cholesterin", "mg/dl", 45, None, 0),
    ("Triglyzeride", "mg/dl", None, 150, 0), ("Vitamin B12", "pg/ml", 197, 771, 0),
    ("Folsäure", "ng/ml", 3.9, 26.8, 1), ("Ferritin", "ng/ml", 15, 150, 0),
]
BLOOD_COUNT = [
    ("Leukozyten", "/nl", 4.0, 10.0, 1), ("Erythrozyten", "/pl", 3.9, 5.2, 2),
    ("Hämoglobin", "g/dl", 12.0, 16.0, 1), ("Hämatokrit", "%", 35, 47, 0),
    ("MCV", "fl", 80, 96, 0), ("MCH", "pg", 27, 33, 1), ("MCHC", "g/dl", 32, 36, 1),
    ("Thrombozyten", "/nl", 150, 400, 0),
]


def _number(value: float, decimals: int) -> str:
    """A value as a German report prints it: decimal comma."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _range(low: float | None, high: float | None, decimals: int) -> str:
    """The reference range as printed."""
    if low is None:
        return f"< {_number(high, decimals)}"
    if high is None:
        return f"> {_number(low, decimals)}"
    return f"{_number(low, decimals)} - {_number(high, decimals)}"


def _result(rng: random.Random, analyte: tuple) -> tuple[str, str, str, str, str]:
    """An invented result: name, value, unit, range, flag."""
    name, unit, low, high, decimals = analyte
    lo = low if low is not None else (high or 1) * 0.3
    hi = high if high is not None else (low or 1) * 2.0
    span = hi - lo
    value = rng.uniform(max(lo - 0.25 * span, 0.4 * lo), hi + 0.35 * span)
    value = round(value, decimals)  # the flag goes by the printed value
    if low is None and rng.random() < 0.15:
        return name, f"< {_number(hi * 0.1, decimals)}", unit, _range(low, high, decimals), ""
    flag = ("H" if high is not None and value > high
            else "L" if low is not None and value < low else "")
    return name, _number(value, decimals), unit, _range(low, high, decimals), flag


def _header(page: pymupdf.Page, rng: random.Random, number: int) -> float:
    """Laboratory, patient and dates at the top; returns where the table starts."""
    y = 60
    for text, size in (("Labor am Beispielpark · Medizinisches Versorgungszentrum", 12),
                       ("Musterweg 1 · 00000 Beispielstadt · Tel. 089 99998100", 8.5)):
        page.insert_text((56, y), text, fontsize=size, fontname="helv")
        y += size + 6
    y += 10
    day, month = rng.randint(1, 28), rng.randint(1, 12)
    date = f"{day:02d}.{month:02d}.2026"
    order_no = f"2026-{4711 + number}"
    for text in (f"Patientin: Erika Musterfrau, geb. 12.08.1964      Auftrag Nr. {order_no}",
                 f"Abnahme: {date} 07:45      Eingang: {date} 10:12      Endbefund"):
        page.insert_text((56, y), text, fontsize=9.5, fontname="helv")
        y += 15
    return y + 14


def _grid(page: pymupdf.Page, rows: list[tuple], y: float) -> None:
    """Layout 1: a ruled grid with a grey head."""
    widths, height = (170, 70, 90, 110, 40), 16
    head = ("Untersuchung", "Ergebnis", "Einheit", "Referenzbereich", "")
    for r, row in enumerate([head, *rows]):
        x = 56
        for c, text in enumerate(row):
            rect = pymupdf.Rect(x, y, x + widths[c], y + height)
            fill = (0.88, 0.88, 0.88) if r == 0 else None
            page.draw_rect(rect, color=(0, 0, 0), width=0.8, fill=fill)
            font = "hebo" if r == 0 else "helv"
            page.insert_text((x + 3, y + 11.5), text, fontsize=9, fontname=font)
            x += widths[c]
        y += height


def _columns(page: pymupdf.Page, rows: list[tuple], y: float) -> None:
    """Layout 2: open columns, a rule under the head only."""
    xs = (56, 230, 300, 395, 510)
    for c, text in enumerate(("Untersuchung", "Ergebnis", "Einheit", "Referenz", "")):
        page.insert_text((xs[c], y), text, fontsize=9.5, fontname="hebo")
    page.draw_line((56, y + 4), (540, y + 4), color=(0, 0, 0), width=0.6)
    y += 18
    for row in rows:
        for c, text in enumerate(row):
            font = "hebo" if c == 4 and text else "helv"
            page.insert_text((xs[c], y), text, fontsize=9.5, fontname=font)
        y += 14.5


def _blocks(page: pymupdf.Page, blood: list[tuple], chemistry: list[tuple], y: float) -> None:
    """Layout 3: blood count and chemistry as two titled blocks, flag before the value."""
    xs = (56, 210, 236, 310, 400)
    for title, rows in (("Kleines Blutbild", blood), ("Klinische Chemie", chemistry)):
        page.insert_text((56, y), title, fontsize=10.5, fontname="hebo")
        y += 16
        for name, value, unit, ref, flag in rows:
            for c, text in enumerate((name, flag, value, unit, ref)):
                page.insert_text((xs[c], y), text, fontsize=9, fontname="helv")
            y += 13.5
        y += 10


def make(folder: Path, count: int = 6, seed: int = 1) -> list[Path]:
    """Write ``count`` reports with their truth files; returns the PDFs."""
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    made = []
    for number in range(1, count + 1):
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        y = _header(page, rng, number)
        layout = (number - 1) % 3
        chemistry = [_result(rng, a) for a in rng.sample(ANALYTES, 14 if layout < 2 else 10)]
        blood = [_result(rng, a) for a in BLOOD_COUNT]
        if layout == 0:
            rows = blood[:4] + chemistry
            _grid(page, rows, y)
        elif layout == 1:
            rows = blood + chemistry[:10]
            _columns(page, rows, y)
        else:
            rows = blood + chemistry
            _blocks(page, blood, chemistry, y)
        stem = f"lab-{number:02d}"
        pdf = folder / f"{stem}.pdf"
        doc.save(pdf)
        doc.close()
        truth = [f"# {stem}: invented laboratory report, layout {layout + 1}"]
        cells = []
        for name, value, unit, ref, flag in rows:
            order = ((name, flag, value, unit, ref) if layout == 2
                     else (name, value, unit, ref, flag))
            truth.append(" ".join(t for t in order if t))
            cells.append([t for t in order if t])
        (folder / f"{stem}.truth.txt").write_text("\n".join(truth) + "\n", encoding="utf-8")
        (folder / f"{stem}.cells.json").write_text(json.dumps(cells, ensure_ascii=False, indent=1)
                                                   + "\n", encoding="utf-8")
        made.append(pdf)
    return made


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("bench-reports")
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    for pdf in make(target, count, seed):
        print(pdf)
