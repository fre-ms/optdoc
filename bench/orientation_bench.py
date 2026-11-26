"""Measure how well optdoc tells which way up a page stands: by the lines of its text
(the rules, which cannot tell a page on its head), by the lines and an OCR comparison
(where ocrdoc is installed beside optdoc), and by the orientation model (an optional
download: ``optdoc models fetch page-orientation --to <folder>``).

    uv run python bench/orientation_bench.py <folder> --models <folder with the model>

makes invented pages in ``<folder>`` (twelve laboratory reports in three layouts and a
two-page letter), turns each four ways, and counts per set of pages how often each way
names the turn that puts the page upright; for the model also how often it was not sure
and left the page as it was, and how often it turned a page wrongly.  The sets: the pages
as made; as worn scans (askew, grainy, every second in grey); photographed at a slant on
a desk; scanned coarsely (60 dpi); pages with one to three lines of text only; a blank
page.  The answer is JSON, numbers only.  Everything measured is made up.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _reports(folder: Path) -> list[Path]:
    spec = importlib.util.spec_from_file_location("lab_reports", ROOT / "bench" / "lab_reports.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    made: list[Path] = module.make(folder / "labs", 12, seed=1)
    return made


def _image(page: Any, dpi: int = 110) -> Any:
    import numpy as np
    import pymupdf

    pix = page.get_pixmap(dpi=dpi, alpha=False, colorspace=pymupdf.csRGB)
    image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
    return image[:, :, ::-1].copy()


def _pages(pdfs: list[Path], dpi: int = 110) -> list[Any]:
    import pymupdf

    images = []
    for pdf in pdfs:
        with pymupdf.open(pdf) as doc:
            images += [_image(doc[n], dpi) for n in range(len(doc))]
    return images


def _lines(lines: list[str], top: float = 100) -> Any:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    for i, text in enumerate(lines):
        page.insert_text((72, top + 18 * i), text, fontsize=11)
    return _image(page)


def _worn(image: Any, k: int, rng: Any) -> Any:
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    turn = cv2.getRotationMatrix2D((w / 2, h / 2), float(rng.uniform(-2, 2)), 1.0)
    out = cv2.warpAffine(image, turn, (w, h), borderValue=(255, 255, 255))
    out = np.clip(out.astype(np.float32) + rng.normal(0, 5, out.shape), 0, 255).astype(np.uint8)
    out[rng.random(out.shape[:2]) < 0.004] = 0
    grey = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return grey if k % 2 else out


def measure(folder: Path, models: Path | None) -> dict[str, Any]:
    """The figures per set of pages."""
    import cv2
    import numpy as np

    from optdoc import cleanup, orientation
    from optdoc import models as catalogue
    from optdoc.project import reader
    from tests.synthetic import camera_photo, make_report

    folder.mkdir(parents=True, exist_ok=True)
    reports = _reports(folder)
    letter = make_report(folder / "letter.pdf")
    full = _pages([*reports, letter])
    rng = np.random.default_rng(1)
    sets: dict[str, list[Any]] = {
        "as made": full,
        "worn scan": [_worn(image, k, rng) for k, image in enumerate(full)],
        "photo at a slant": [camera_photo(pdf, pitch=20, yaw=(-1) ** k * 7, roll=3)[0]
                             for k, pdf in enumerate(reports)],
        "scan at 60 dpi": _pages(reports, 60),
        "one to three lines": [
            _lines(["Sehr geehrte Frau Kollegin,", "anbei der Befund.", "Mit freundlichen Grüßen"]),
            _lines(["Befund folgt.", "Dr. E. Beispiel", "Musterstadt, 12.03.2026"], top=600),
            _lines(["Kalium 5,8 mmol/l", "Natrium 140 mmol/l", "CRP < 0,5 mg/l"]),
            _lines(["Bitte um Rückruf."]), _lines(["Kontrolle in 6 Monaten empfohlen."], top=700)],
        "blank": [np.full((1286, 909, 3), 255, np.uint8)],
    }
    turns = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
             270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    model = catalogue.orientation(models)
    engine = reader()
    result: dict[str, Any] = {"model": model is not None, "ocr": engine is not None}
    seconds = {"lines": 0.0, "lines_and_ocr": 0.0, "model": 0.0}
    count = 0
    for name, images in sets.items():
        row = {"pages": len(images) * 4, "lines": 0, "lines_and_ocr": 0 if engine else None,
               "model": 0 if model else None, "model_unsure": 0 if model else None,
               "model_wrong": 0 if model else None, "middle_alone": 0 if model else None}
        for image in images:
            for turned, code in turns.items():
                shown = image if code is None else cv2.rotate(image, code)
                needed = (360 - turned) % 360
                count += 1
                start = time.monotonic()
                row["lines"] += cleanup.estimate_orientation(shown) == needed
                seconds["lines"] += time.monotonic() - start
                if engine is not None and name in ("as made", "worn scan"):
                    start = time.monotonic()
                    row["lines_and_ocr"] += cleanup.estimate_orientation(shown, engine) == needed
                    seconds["lines_and_ocr"] += time.monotonic() - start
                if model is not None:
                    start = time.monotonic()
                    found = orientation.upright(shown, model)
                    seconds["model"] += time.monotonic() - start
                    row["model"] += found == needed
                    row["model_unsure"] += found is None
                    row["model_wrong"] += found is not None and found != needed
                    middle = orientation.probabilities(shown, model)
                    row["middle_alone"] += orientation.decided(middle, None) == turned
        if engine is not None and name not in ("as made", "worn scan"):
            row["lines_and_ocr"] = None  # not measured: OCR takes seconds a page
        result[name] = row
    read = (result["as made"]["pages"] + result["worn scan"]["pages"]) or 1
    result["seconds_per_page"] = {
        "lines": round(seconds["lines"] / count, 4),
        "lines_and_ocr": round(seconds["lines_and_ocr"] / read, 2) if engine else None,
        "model": round(seconds["model"] / count, 4) if model else None}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--models", type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.folder, args.models), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
