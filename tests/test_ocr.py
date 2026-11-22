"""OCR: engine output to page text, scans and photos read, tables, engine choice."""

from __future__ import annotations

import difflib
from pathlib import Path

import pymupdf
import pytest

from optdoc import cleanup
from optdoc import ocr as ocrlib
from optdoc.loading import open_document
from optdoc.ocr import OCRWord, page_text_from_words
from optdoc.reading import read
from optdoc.settings import Settings, set_settings
from tests.synthetic import REPORT_TEXT, rasterise, scan

BACKENDS = ocrlib.available_backends()
needs_backend = pytest.mark.skipif(not BACKENDS, reason="kein OCR-Backend installiert")


def test_words_to_page_text() -> None:
    words = [OCRWord("Max", 100, 100, 130, 112), OCRWord("Herr", 60, 101, 90, 113),
               OCRWord("Zweite", 60, 130, 110, 142, 0.4)]
    s = page_text_from_words(words, 0, 595, 842)
    assert s.text.splitlines()[0] == "Herr Max"
    assert s.text.splitlines()[1] == "Zweite"
    assert s.source == "ocr" and s.uncertain_words == 1
    a = s.text.index("Max")
    r = s.rects(a, a + 3)[0]
    assert abs(r.x0 - 100) < 0.01 and abs(r.x1 - 130) < 0.01
    assert s.line_of(a) != s.line_of(s.text.index("Zweite"))


@needs_backend
@pytest.mark.parametrize("backend", BACKENDS)
def test_scan_is_read(tmp_path: Path, report: Path, backend: str) -> None:
    """Both pages of an image-only scan are read by OCR; the words carry boxes."""
    reading = read(scan(report, tmp_path / "scan.pdf"), reader=backend)
    try:
        assert reading.reader == backend and [s.ocr for s in reading.pages] == [True, True]
        text = "\n".join(s.text.text for s in reading.pages)
        assert "Diagnosen" in text and "Ramipril" in text and "Kontrolle" in text
        first = reading.pages[0].text
        a = first.text.index("Diagnosen")
        assert first.rects(a, a + len("Diagnosen"))
    finally:
        reading.close()


@needs_backend
def test_noisy_tilted_scan(tmp_path: Path, report: Path) -> None:
    reading = read(scan(report, tmp_path / "scan.pdf", dpi=150, noise=0.01, rotation=0.7))
    try:
        assert "Ramipril" in reading.pages[0].text.text
    finally:
        reading.close()


@needs_backend
def test_photo_as_png(tmp_path: Path, report: Path) -> None:
    with pymupdf.open(report) as d:
        image = tmp_path / "photo.png"
        d[0].get_pixmap(dpi=150).save(image)
    reading = read(image)
    try:
        assert len(reading.pages) == 1 and reading.pages[0].ocr
        assert (round(reading.doc[0].rect.width), round(reading.doc[0].rect.height)) == (595, 842)
        assert "Diagnosen" in reading.pages[0].text.text
    finally:
        reading.close()


def test_without_backend_the_scan_has_no_text(tmp_path: Path, report: Path) -> None:
    reading = read(scan(report, tmp_path / "scan.pdf"), reader="none")
    try:
        assert reading.reader is None and reading.without_text == [0, 1]
    finally:
        reading.close()


def test_text_layer_needs_no_ocr(report: Path) -> None:
    reading = read(report)
    try:
        assert not any(s.ocr for s in reading.pages) and reading.plan == {}
        assert "Ramipril" in reading.pages[0].text.text
    finally:
        reading.close()


def test_unknown_backend() -> None:
    with pytest.raises(ocrlib.OCRError):
        ocrlib.backend("zauber")


def test_open_heic(tmp_path: Path, report: Path) -> None:
    pillow_heif = pytest.importorskip("pillow_heif")
    from PIL import Image

    pillow_heif.register_heif_opener()
    with pymupdf.open(report) as d:
        pix = d[0].get_pixmap(dpi=100, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    heic = tmp_path / "photo.heic"
    image.save(heic, format="HEIF")
    doc = open_document(heic)
    assert len(doc) == 1 and doc[0].get_images()
    doc.close()


def test_unreadable_line() -> None:
    from optdoc.ocr import unreadable_lines

    fragments = ["G6ot", "n", "e", "n", "e", "i", "l", "e", "5g"]
    words = [OCRWord(w, 50 + 30 * i, 100, 70 + 30 * i, 112, k)
               for i, (w, k) in enumerate(zip(fragments, [0.87, 0.5, 0.99, 0.9, 0.25, 0.5, 0.47,
                                                           0.97, 0.81], strict=True))]
    words += [OCRWord(w, 50 + 40 * i, 130, 85 + 40 * i, 142, 0.99)
                for i, w in enumerate(["in", "Riesa.", "Flantz,", "berichtet"])]
    s = page_text_from_words(words, 0, 595, 842)
    regions = unreadable_lines(s)
    assert len(regions) == 1
    r = regions[0]
    assert r.page_number == 0 and r.text == "G6ot n e n e i l e 5g" == s.text[r.start:r.end]
    assert r.rects and r.font_size > 0
    assert "Riesa" not in r.text


@needs_backend
@pytest.mark.skipif(not cleanup.available(), reason="OpenCV fehlt")
def test_cleanup_before_ocr(tmp_path: Path, report: Path) -> None:
    """A tilted scan: the suggestion straightens it before OCR and is recorded; an
    explicit plan wins over the suggestion; a text layer needs no clean-up."""
    tilted = scan(report, tmp_path / "scan.pdf", rotation=2.5)
    reading = read(tilted)
    try:
        assert set(reading.plan) == {0, 1}
        a = reading.plan[0]
        assert a.straighten and abs(abs(a.angle) - 2.5) < 0.5, a
        assert "Ramipril" in reading.pages[0].text.text
    finally:
        reading.close()
    own = read(tilted, plan={0: cleanup.CleanupPlan(masks=[(56, 60, 400, 95)])})
    try:
        assert set(own.plan) == {0} and own.plan[0].masks
    finally:
        own.close()
    raw = read(tilted, clean_up=False)
    try:
        assert raw.plan == {}
    finally:
        raw.close()


@needs_backend
@pytest.mark.skipif(not cleanup.available(), reason="OpenCV fehlt")
def test_suggestion_does_not_hurt_the_ocr(tmp_path: Path, report: Path) -> None:
    """Guard for the automatic clean-up: on a noisy, slightly tilted scan the OCR text
    after the suggested steps must be about as close to the truth as without them."""
    truth = " ".join("\n".join(REPORT_TEXT[0]).split())
    noisy = scan(report, tmp_path / "scan.pdf", dpi=150, noise=0.01, rotation=1.0)

    def quality(plan: dict[int, cleanup.CleanupPlan] | None, clean_up: bool = True) -> float:
        reading = read(noisy, plan=plan, clean_up=clean_up)
        try:
            text = " ".join(reading.pages[0].text.text.split())
        finally:
            reading.close()
        return difflib.SequenceMatcher(None, truth, text).ratio()

    g_raw, g_auto = quality(None, clean_up=False), quality(None)
    assert g_raw > 0.95, g_raw
    assert g_auto >= g_raw - 0.03, (g_raw, g_auto)
    g_text = quality({0: cleanup.CleanupPlan(upscale=2, letter_mode=True)})
    assert g_text >= g_raw - 0.03, (g_raw, g_text)  # the letter mode must not hurt


CELLS = [("Medikament", "Dosis", "morgens", "mittags", "abends"),
          ("Methylphenidat ret.", "20 mg", "1", "0", "0"),
          ("Sertralin", "50 mg", "1", "0", "0"),
          ("Melatonin", "2 mg", "0", "0", "1"),
          ("Pantoprazol", "40 mg", "1", "0", "0"),
          ("Amlodipin", "5 mg", "1", "0", "0")]


def _table_page(path: Path, dpi: int = 200) -> Path:
    """Letter with a bordered medication table (thick rules, grey header), as an image."""
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    y = 80
    for t in ("Sehr geehrte Frau Kollegin,", "wir berichten über die Patientin.", "",
              "Aktuelle Medikation:"):
        p.insert_text((60, y), t, fontsize=11, fontname="helv")
        y += 16
    x0, y0, widths, zh = 60, y + 10, (170, 70, 70, 70, 70), 18
    for r, line in enumerate(CELLS):
        x = x0
        for c, text in enumerate(line):
            rect = pymupdf.Rect(x, y0 + r * zh, x + widths[c], y0 + (r + 1) * zh)
            p.draw_rect(rect, color=(0, 0, 0), width=2.0,
                        fill=(0.85, 0.85, 0.85) if r == 0 else None)
            p.insert_text((x + 3, y0 + r * zh + 13), text, fontsize=9, fontname="helv")
            x += widths[c]
    images = rasterise(doc, dpi=dpi)
    images.save(path)
    images.close()
    doc.close()
    return path


def _cell_words(text: str) -> int:
    words = text.split()
    found = 0
    for cell in (z for line in CELLS for z in line):
        for w in cell.split():
            if w in words:
                words.remove(w)
                found += 1
    return found


@pytest.mark.skipif("tesseract" not in BACKENDS or not cleanup.available(),
                    reason="Tesseract oder OpenCV fehlt")
def test_tesseract_reads_tables(tmp_path: Path, report: Path) -> None:
    """Tesseract's page segmentation drops the cells of a bordered table; the second
    pass on the line-free grid gets them back.  Pages without a grid are untouched."""
    image_pdf = _table_page(tmp_path / "tabelle.pdf")
    with pymupdf.open(image_pdf) as d:
        image, _scale = cleanup.render(d[0], 200)
        areas = cleanup.grid_areas(image)
        assert len(areas) == 1
        x0, y0, x1, y1 = areas[0]
        assert x1 - x0 > image.shape[1] * 0.6 and y1 - y0 > image.shape[0] * 0.1
        without = ocrlib.recognise_page(d[0], ocrlib.TesseractBackend(tables=False))
        with_grid = ocrlib.recognise_page(d[0], ocrlib.TesseractBackend(tables=True))
    assert _cell_words(with_grid.text) >= 25
    assert _cell_words(with_grid.text) >= _cell_words(without.text) + 10
    assert "Kollegin," in with_grid.text  # the running text is still there
    with pymupdf.open(report) as d:
        image, _scale = cleanup.render(d[0], 150)
        assert cleanup.grid_areas(image) == []


@needs_backend
def test_structured_ocr_text(tmp_path: Path, report: Path) -> None:
    """An OCR page gets its structure: lines that ran to the margin are joined, blocks
    stay apart; without structure the raw lines come back."""
    reading = read(scan(report, tmp_path / "scan.pdf"))
    try:
        read_page = reading.pages[0]
        assert read_page.structure is not None
        raw, structured = read_page.text.text, read_page.markdown
        assert structured != raw and "\n\n" in structured
        roles, lines = read_page.structure.roles, raw.split("\n")
        k = next(i for i, r in enumerate(roles) if r.separator == "word")
        assert lines[k - 1].strip() + " " + lines[k].strip() in structured
    finally:
        reading.close()
    without = read(scan(report, tmp_path / "scan2.pdf"), with_structure=False)
    try:
        assert without.pages[0].structure is None
        assert without.pages[0].markdown == without.pages[0].text.text
    finally:
        without.close()


# -- steps of the OCR layer on synthetic engine output ---------------------------------------------
def test_tesseract_tsv_to_words() -> None:
    """Word rows only; pixel boxes shifted by the crop offset and scaled to points;
    a negative confidence is clamped; rows with unreadable numbers are skipped."""
    flipped = "\t".join(["level", "page_num", "block_num", "par_num", "line_num", "word_num",
                      "left", "top", "width", "height", "conf", "text"])
    tsv = "\n".join([
        flipped,
        "4\t1\t1\t1\t1\t0\t10\t20\t300\t40\t-1\t",
        "5\t1\t1\t1\t1\t1\t100\t200\t50\t20\t91.5\tHallo",
        "5\t1\t1\t1\t1\t2\t160\t200\t60\t20\t-1\t   ",
        "5\t1\t1\t1\t1\t3\t230\t200\t40\t20\t-1\tx",
        "5\t1\t1\t1\t1\t4\tabc\t200\t40\t20\t50\tkaputt",
    ])
    words = ocrlib._words_from_tsv(tsv, 2.0, (10.0, -20.0))
    assert [w.text for w in words] == ["Hallo", "x"]
    hello = words[0]
    assert (hello.x0, hello.y0, hello.x1, hello.y1) == (55.0, 90.0, 80.0, 100.0)
    assert abs(hello.confidence - 0.915) < 1e-9 and words[1].confidence == 0.0


def test_rapidocr_result_to_words() -> None:
    """A line with the engine's word boxes keeps them (blank words dropped); a line
    without is split by character share; a result without boxes gives no words."""
    from types import SimpleNamespace

    box = [[0, 0], [200, 0], [200, 20], [0, 20]]
    wbox = [[10, 2], [50, 2], [50, 18], [10, 18]]
    result = SimpleNamespace(
        boxes=[box, box], txts=["Herr Max", "ab cd"], scores=[0.9, 0.8],
        word_results=[[("Herr", 0.95, wbox), (" ", 0.1, wbox)], []],
    )
    words = ocrlib._words_from_result(result, 2.0)
    assert [(w.text, w.confidence) for w in words] == [("Herr", 0.95), ("ab", 0.8), ("cd", 0.8)]
    assert (words[0].x0, words[0].y0, words[0].x1, words[0].y1) == (5.0, 1.0, 25.0, 9.0)
    assert (words[1].x0, words[1].x1) == (0.0, 40.0)
    assert (words[2].x0, words[2].x1) == (60.0, 100.0)
    assert ocrlib._words_from_result(SimpleNamespace(boxes=None), 1.0) == []


def test_better_reading_replaces_only_with_more_confidence() -> None:
    """The second pass replaces the words inside the grid's box only when its reading
    carries more confidence mass; words reaching outside the box are never touched."""
    bounds = (0.0, 0.0, 100.0, 50.0)
    inside = [OCRWord("Müll", 10, 10, 30, 20, 0.3), OCRWord("##", 40, 10, 60, 20, 0.9)]
    margin = [OCRWord("Rand", 90, 10, 120, 20, 0.1)]  # reaches out of the box
    outside = [OCRWord("Text", 200, 10, 240, 20, 0.9)]
    new = [OCRWord("Dosis", 10, 10, 60, 20, 0.8)]
    assert ocrlib._better_reading(outside + inside + margin, new, bounds) == outside + margin + new
    weak = [OCRWord("Do", 10, 10, 60, 20, 0.5)]
    assert ocrlib._better_reading(outside + inside, weak, bounds) == outside + inside


def test_wide_gaps_become_tabs() -> None:
    """A gap far wider than the usual one becomes a tab, but only once the page has at
    least four gaps to tell what usual means."""
    def line(y: float, texts: list[str], xs: list[float]) -> list[OCRWord]:
        return [OCRWord(t, x, y, x + 6 * len(t), y + 10, 0.9)
                for t, x in zip(texts, xs, strict=True)]

    words = (line(100, ["Medikament", "Dosis"], [50, 300])
               + line(120, ["a", "b", "c"], [50, 60, 70])
               + line(140, ["d", "e", "f"], [50, 60, 70]))
    s = page_text_from_words(words, 0, 595, 842)
    assert s.text.splitlines()[0] == "Medikament\tDosis"
    assert s.word_spans[:2] == [(0, 10), (11, 16)] and len(s.confidences) == 8
    few = line(100, ["Medikament", "Dosis"], [50, 300]) + line(120, ["a", "b"], [50, 60])
    assert "\t" not in page_text_from_words(few, 0, 595, 842).text


def test_line_unreadable_rules() -> None:
    """Three uncertain words, or the required share of them, make a line unreadable;
    a single uncertain word only when it is the whole line."""
    def spans(*uncertain: bool) -> list[ocrlib._WordSpan]:
        return [ocrlib._WordSpan(i * 3, i * 3 + 2, u) for i, u in enumerate(uncertain)]

    check = ocrlib._line_unreadable
    assert not check(spans(False, False, False), 0.4)
    assert check(spans(True), 0.4)  # a single word is the whole line
    assert not check(spans(True, False), 0.4)  # one fragment next to a read word
    assert check(spans(True, True), 0.4)
    assert not check(spans(True, False, False, False), 0.4)  # 25 % is below the share
    assert check(spans(True, True, False, False, False), 0.4)
    assert check(spans(True, True, True, False, False, False, False, False, False, False), 0.4)
    assert not check(spans(True, True, False, False, False), 0.5)


def test_backend_choice_follows_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """"auto" takes the preference (of the environment, or what an application set)
    when it names an engine or "none"; an unknown preference leaves "auto" in place; an
    unknown name is an error."""
    monkeypatch.setenv("OPTDOC_OCR", "none")
    assert ocrlib._preferred_backend("auto") == "none"
    assert ocrlib.backend("AUTO") is None and ocrlib.backend("") is None
    set_settings(Settings(ocr_backend="zauber"))
    assert ocrlib._preferred_backend("auto") == "auto"
    assert ocrlib._preferred_backend("tesseract") == "tesseract"
    with pytest.raises(ocrlib.OCRError, match="unknown OCR engine: 'zauber'"):
        ocrlib.backend("Zauber")
