"""The test bench: how well optdoc reads documents whose content is known.

A bench folder holds documents (photos, scans, PDFs) and, next to each, a truth file
``<stem>.truth.txt``: one line per item worth checking, written as it is printed
("Kalium 5,8 mmol/l 3,5 - 5,1 H"); empty lines and lines starting with ``#`` are
skipped.  :func:`bench` reads every document and compares each truth line with the
reading line that resembles it most.

What it reports is numbers only.  Documents are named by their position in the
folder and their suffix, never by file name; no text of a document or of its truth
file, and no error message, leaves this module.  So the bench can run on real
documents on the user's own computer, with only the figures shown to anyone else.

Per document and in total:

- ``lines``: truth lines; ``lines_exact``: found word for word (spacing and case aside);
- ``numbers``: numbers in the truth lines; ``numbers_right``: those read right, in the line
  that matches their truth line (a number elsewhere on the page does not count);
- ``rows_all_numbers_right``: truth lines whose every number was read right;
- ``similarity``: mean similarity of a truth line to its best reading line (0 to 1);
- ``confidence``: the engine's mean word confidence on OCR pages.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from optdoc import ocr as ocrlib
from optdoc.errors import OptdocError
from optdoc.loading import HEIC_SUFFIXES, IMAGE_SUFFIXES
from optdoc.pagetext import PageText

TRUTH_SUFFIX = ".truth.txt"
DOCUMENT_SUFFIXES = IMAGE_SUFFIXES | HEIC_SUFFIXES | {".pdf"}
_NUMBER = re.compile(r"[<>≤≥]?\d+(?:[.,]\d+)?")


def _normal(text: str) -> str:
    """Case folded, spacing collapsed; a decimal point and comma count as the same."""
    return " ".join(text.casefold().replace(",", ".").split())


def numbers_of(text: str) -> list[str]:
    """The numbers of a text as printed, comparators included, with a decimal point."""
    return [n.replace(",", ".") for n in _NUMBER.findall(text)]


def truth_lines(path: Path) -> list[str]:
    """The lines of a truth file worth checking."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [z.strip() for z in lines if z.strip() and not z.lstrip().startswith("#")]


def _numbers_right(expected: list[str], found: list[str]) -> int:
    """How many of the expected numbers the reading line has, in their order."""
    matcher = difflib.SequenceMatcher(None, expected, found, autojunk=False)
    return sum(block.size for block in matcher.get_matching_blocks())


@dataclass
class Score:
    """The figures of one document, or of several added up."""

    lines: int = 0
    lines_exact: int = 0
    numbers: int = 0
    numbers_right: int = 0
    rows_all_numbers_right: int = 0
    similarity_sum: float = 0.0
    confidence_sum: float = 0.0
    confidence_words: int = 0

    def add(self, other: Score) -> None:
        """Add the figures of another score."""
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def as_dict(self) -> dict[str, Any]:
        """The figures, with the shares worked out."""
        def share(a: int, b: int) -> float | None:
            return round(a / b, 4) if b else None

        return {
            "lines": self.lines, "lines_exact": self.lines_exact,
            "lines_exact_share": share(self.lines_exact, self.lines),
            "numbers": self.numbers, "numbers_right": self.numbers_right,
            "numbers_right_share": share(self.numbers_right, self.numbers),
            "rows_all_numbers_right": self.rows_all_numbers_right,
            "rows_all_numbers_right_share": share(self.rows_all_numbers_right, self.lines),
            "similarity": round(self.similarity_sum / self.lines, 4) if self.lines else None,
            "confidence": (round(self.confidence_sum / self.confidence_words, 4)
                           if self.confidence_words else None),
        }


def score_text(truth: list[str], reading_lines: list[str]) -> Score:
    """Compare the truth lines with the lines of a reading."""
    score = Score()
    normal = [_normal(z) for z in reading_lines if z.strip()]
    whole = " ".join(normal)
    for line in truth:
        expected = numbers_of(line)
        wanted = _normal(line)
        best, best_ratio = "", 0.0
        for candidate in normal:
            ratio = difflib.SequenceMatcher(None, wanted, candidate, autojunk=False).ratio()
            if ratio > best_ratio:
                best, best_ratio = candidate, ratio
        right = _numbers_right(expected, numbers_of(best))
        score.lines += 1
        score.lines_exact += wanted in whole
        score.numbers += len(expected)
        score.numbers_right += right
        score.rows_all_numbers_right += right == len(expected)
        score.similarity_sum += best_ratio
    return score


@dataclass
class Result:
    """The bench's answer: per document and reader, and the totals per reader."""

    documents: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, Score] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready, numbers only."""
        return {"documents": self.documents,
                "totals": {reader: s.as_dict() for reader, s in self.totals.items()}}


def rows_of(page_text: PageText) -> list[str]:
    """The printed rows of a page, made from the word boxes: words whose boxes share a
    height band form a row, read left to right.  Readers build their lines differently
    (a text layer may hold every table cell as a line of its own); rows make them
    comparable."""
    words = []
    for a, b in page_text.words():
        boxes = page_text.rects(a, b)
        if boxes:
            box = boxes[0]
            for r in boxes[1:]:
                box |= r
            words.append((box, page_text.text[a:b]))
    if not words:
        return [z for z in page_text.text.splitlines() if z.strip()]
    heights = sorted(box.height for box, _ in words)
    tolerance = 0.5 * heights[len(heights) // 2]
    rows: list[tuple[list[tuple[Any, str]], float]] = []
    for box, text in sorted(words, key=lambda w: (w[0].y0 + w[0].y1) / 2):
        middle = (box.y0 + box.y1) / 2
        if rows and abs(middle - rows[-1][1]) <= tolerance:
            rows[-1][0].append((box, text))
        else:
            rows.append(([(box, text)], middle))
    return [" ".join(t for _, t in sorted(row, key=lambda w: w[0].x0)) for row, _ in rows]


def _read_lines(path: Path, reader: str, clean_up: bool) -> tuple[list[str], Score, dict[str, Any]]:
    """The reading lines of a document, its confidence figures and a summary."""
    from optdoc.reading import read

    reading = read(path, reader=reader, clean_up=clean_up)
    try:
        lines: list[str] = []
        confidence = Score()
        for page in reading.pages:
            lines += rows_of(page.text)
            if page.ocr:
                confidence.confidence_sum += sum(page.text.confidences)
                confidence.confidence_words += len(page.text.confidences)
        summary = {"pages": len(reading.pages), "ocr_pages": sum(p.ocr for p in reading.pages),
                   "cleaned_up": len(reading.plan)}
        return lines, confidence, summary
    finally:
        reading.close()


def documents_in(folder: Path) -> list[tuple[Path, Path]]:
    """The documents of a bench folder that have a truth file, in name order."""
    pairs = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in DOCUMENT_SUFFIXES and not path.name.startswith("."):
            truth = path.with_name(path.stem + TRUTH_SUFFIX)
            if truth.is_file():
                pairs.append((path, truth))
    return pairs


def bench(folder: str | Path, readers: list[str] | None = None, clean_up: bool = True) -> Result:
    """Read every document of ``folder`` that has a truth file with each of ``readers``
    (default: every installed engine) and score it."""
    pairs = documents_in(Path(folder))
    readers = readers or ocrlib.available_backends()
    result = Result()
    for reader in readers:
        result.totals[reader] = Score()
    for number, (path, truth_path) in enumerate(pairs, 1):
        truth = truth_lines(truth_path)
        for reader in readers:
            entry: dict[str, Any] = {"document": number, "suffix": path.suffix.lower(),
                                     "reader": reader}
            try:
                lines, confidence, summary = _read_lines(path, reader, clean_up)
            except Exception as error:  # the message may quote a path; only its kind leaves
                entry["error"] = (error.kind if isinstance(error, OptdocError)
                                  else type(error).__name__)
                result.documents.append(entry)
                continue
            score = score_text(truth, lines)
            score.confidence_sum, score.confidence_words = (confidence.confidence_sum,
                                                            confidence.confidence_words)
            result.totals[reader].add(score)
            result.documents.append({**entry, **summary, **score.as_dict()})
    return result
