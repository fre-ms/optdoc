"""OCR: engine output to page text, scans and photos read, tables, engine choice."""

from __future__ import annotations

import difflib
from pathlib import Path

import pymupdf
import pytest

from optdoc import aufbereitung as aufmodul
from optdoc import ocr as ocrmodul
from optdoc.einstellungen import Einstellungen, setze_einstellungen
from optdoc.laden import oeffne
from optdoc.lesen import lies
from optdoc.ocr import OCRWort, seitentext_aus_woerter
from tests.synthetisch import BEFUND_TEXT, rastere, scan

BACKENDS = ocrmodul.verfuegbare_backends()
braucht_backend = pytest.mark.skipif(not BACKENDS, reason="kein OCR-Backend installiert")


def test_woerter_zu_seitentext() -> None:
    woerter = [OCRWort("Max", 100, 100, 130, 112), OCRWort("Herr", 60, 101, 90, 113),
               OCRWort("Zweite", 60, 130, 110, 142, 0.4)]
    s = seitentext_aus_woerter(woerter, 0, 595, 842)
    assert s.text.splitlines()[0] == "Herr Max"
    assert s.text.splitlines()[1] == "Zweite"
    assert s.quelle == "ocr" and s.unsichere_woerter == 1
    a = s.text.index("Max")
    r = s.rects(a, a + 3)[0]
    assert abs(r.x0 - 100) < 0.01 and abs(r.x1 - 130) < 0.01
    assert s.zeile_von(a) != s.zeile_von(s.text.index("Zweite"))


@braucht_backend
@pytest.mark.parametrize("backend", BACKENDS)
def test_scan_wird_gelesen(tmp_path: Path, befund: Path, backend: str) -> None:
    """Both pages of an image-only scan are read by OCR; the words carry boxes."""
    lesung = lies(scan(befund, tmp_path / "scan.pdf"), leser=backend)
    try:
        assert lesung.leser == backend and [s.ocr for s in lesung.seiten] == [True, True]
        text = "\n".join(s.text.text for s in lesung.seiten)
        assert "Diagnosen" in text and "Ramipril" in text and "Kontrolle" in text
        erste = lesung.seiten[0].text
        a = erste.text.index("Diagnosen")
        assert erste.rects(a, a + len("Diagnosen"))
    finally:
        lesung.schliessen()


@braucht_backend
def test_verrauschter_schiefer_scan(tmp_path: Path, befund: Path) -> None:
    lesung = lies(scan(befund, tmp_path / "scan.pdf", dpi=150, rauschen=0.01, drehung=0.7))
    try:
        assert "Ramipril" in lesung.seiten[0].text.text
    finally:
        lesung.schliessen()


@braucht_backend
def test_foto_als_png(tmp_path: Path, befund: Path) -> None:
    with pymupdf.open(befund) as d:
        bild = tmp_path / "foto.png"
        d[0].get_pixmap(dpi=150).save(bild)
    lesung = lies(bild)
    try:
        assert len(lesung.seiten) == 1 and lesung.seiten[0].ocr
        assert (round(lesung.doc[0].rect.width), round(lesung.doc[0].rect.height)) == (595, 842)
        assert "Diagnosen" in lesung.seiten[0].text.text
    finally:
        lesung.schliessen()


def test_ohne_backend_bleibt_der_scan_ohne_text(tmp_path: Path, befund: Path) -> None:
    lesung = lies(scan(befund, tmp_path / "scan.pdf"), leser="aus")
    try:
        assert lesung.leser is None and lesung.ohne_text == [0, 1]
    finally:
        lesung.schliessen()


def test_textebene_braucht_keine_ocr(befund: Path) -> None:
    lesung = lies(befund)
    try:
        assert not any(s.ocr for s in lesung.seiten) and lesung.plan == {}
        assert "Ramipril" in lesung.seiten[0].text.text
    finally:
        lesung.schliessen()


def test_unbekanntes_backend() -> None:
    with pytest.raises(ocrmodul.OCRFehler):
        ocrmodul.backend("zauber")


def test_heic_laden(tmp_path: Path, befund: Path) -> None:
    pillow_heif = pytest.importorskip("pillow_heif")
    from PIL import Image

    pillow_heif.register_heif_opener()
    with pymupdf.open(befund) as d:
        pix = d[0].get_pixmap(dpi=100, alpha=False)
    bild = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    heic = tmp_path / "foto.heic"
    bild.save(heic, format="HEIF")
    doc = oeffne(heic)
    assert len(doc) == 1 and doc[0].get_images()
    doc.close()


def test_unlesbare_zeile() -> None:
    from optdoc.ocr import unlesbare_regionen

    fragmente = ["G6ot", "n", "e", "n", "e", "i", "l", "e", "5g"]
    woerter = [OCRWort(w, 50 + 30 * i, 100, 70 + 30 * i, 112, k)
               for i, (w, k) in enumerate(zip(fragmente, [0.87, 0.5, 0.99, 0.9, 0.25, 0.5, 0.47,
                                                           0.97, 0.81], strict=True))]
    woerter += [OCRWort(w, 50 + 40 * i, 130, 85 + 40 * i, 142, 0.99)
                for i, w in enumerate(["in", "Riesa.", "Flantz,", "berichtet"])]
    s = seitentext_aus_woerter(woerter, 0, 595, 842)
    regionen = unlesbare_regionen(s)
    assert len(regionen) == 1
    r = regionen[0]
    assert r.seite == 0 and r.text == "G6ot n e n e i l e 5g" == s.text[r.start:r.ende]
    assert r.rects and r.schriftgroesse > 0
    assert "Riesa" not in r.text


@braucht_backend
@pytest.mark.skipif(not aufmodul.verfuegbar(), reason="OpenCV fehlt")
def test_aufbereitung_vor_der_ocr(tmp_path: Path, befund: Path) -> None:
    """A tilted scan: the suggestion straightens it before OCR and is recorded; an
    explicit plan wins over the suggestion; a text layer needs no clean-up."""
    schief = scan(befund, tmp_path / "scan.pdf", drehung=2.5)
    lesung = lies(schief)
    try:
        assert set(lesung.plan) == {0, 1}
        a = lesung.plan[0]
        assert a.begradigen and abs(abs(a.winkel) - 2.5) < 0.5, a
        assert "Ramipril" in lesung.seiten[0].text.text
    finally:
        lesung.schliessen()
    eigen = lies(schief, plan={0: aufmodul.Aufbereitung(masken=[(56, 60, 400, 95)])})
    try:
        assert set(eigen.plan) == {0} and eigen.plan[0].masken
    finally:
        eigen.schliessen()
    roh = lies(schief, aufbereiten=False)
    try:
        assert roh.plan == {}
    finally:
        roh.schliessen()


@braucht_backend
@pytest.mark.skipif(not aufmodul.verfuegbar(), reason="OpenCV fehlt")
def test_vorschlag_schadet_der_ocr_nicht(tmp_path: Path, befund: Path) -> None:
    """Guard for the automatic clean-up: on a noisy, slightly tilted scan the OCR text
    after the suggested steps must be about as close to the truth as without them."""
    wahr = " ".join("\n".join(BEFUND_TEXT[0]).split())
    verrauscht = scan(befund, tmp_path / "scan.pdf", dpi=150, rauschen=0.01, drehung=1.0)

    def guete(plan: dict[int, aufmodul.Aufbereitung] | None, aufbereiten: bool = True) -> float:
        lesung = lies(verrauscht, plan=plan, aufbereiten=aufbereiten)
        try:
            text = " ".join(lesung.seiten[0].text.text.split())
        finally:
            lesung.schliessen()
        return difflib.SequenceMatcher(None, wahr, text).ratio()

    g_roh, g_auto = guete(None, aufbereiten=False), guete(None)
    assert g_roh > 0.95, g_roh
    assert g_auto >= g_roh - 0.03, (g_roh, g_auto)
    g_text = guete({0: aufmodul.Aufbereitung(hochskalieren=2, textmodus=True)})
    assert g_text >= g_roh - 0.03, (g_roh, g_text)  # the letter mode must not hurt


ZELLEN = [("Medikament", "Dosis", "morgens", "mittags", "abends"),
          ("Methylphenidat ret.", "20 mg", "1", "0", "0"),
          ("Sertralin", "50 mg", "1", "0", "0"),
          ("Melatonin", "2 mg", "0", "0", "1"),
          ("Pantoprazol", "40 mg", "1", "0", "0"),
          ("Amlodipin", "5 mg", "1", "0", "0")]


def _tabellenseite(pfad: Path, dpi: int = 200) -> Path:
    """Letter with a bordered medication table (thick rules, grey header), as an image."""
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    y = 80
    for t in ("Sehr geehrte Frau Kollegin,", "wir berichten über die Patientin.", "",
              "Aktuelle Medikation:"):
        p.insert_text((60, y), t, fontsize=11, fontname="helv")
        y += 16
    x0, y0, breiten, zh = 60, y + 10, (170, 70, 70, 70, 70), 18
    for r, zeile in enumerate(ZELLEN):
        x = x0
        for c, text in enumerate(zeile):
            rect = pymupdf.Rect(x, y0 + r * zh, x + breiten[c], y0 + (r + 1) * zh)
            p.draw_rect(rect, color=(0, 0, 0), width=2.0,
                        fill=(0.85, 0.85, 0.85) if r == 0 else None)
            p.insert_text((x + 3, y0 + r * zh + 13), text, fontsize=9, fontname="helv")
            x += breiten[c]
    bilder = rastere(doc, dpi=dpi)
    bilder.save(pfad)
    bilder.close()
    doc.close()
    return pfad


def _zellenwoerter(text: str) -> int:
    woerter = text.split()
    gefunden = 0
    for zelle in (z for zeile in ZELLEN for z in zeile):
        for w in zelle.split():
            if w in woerter:
                woerter.remove(w)
                gefunden += 1
    return gefunden


@pytest.mark.skipif("tesseract" not in BACKENDS or not aufmodul.verfuegbar(),
                    reason="Tesseract oder OpenCV fehlt")
def test_tesseract_liest_tabellen(tmp_path: Path, befund: Path) -> None:
    """Tesseract's page segmentation drops the cells of a bordered table; the second
    pass on the line-free grid gets them back.  Pages without a grid are untouched."""
    bild_pdf = _tabellenseite(tmp_path / "tabelle.pdf")
    with pymupdf.open(bild_pdf) as d:
        bild, _skala = aufmodul.rendere(d[0], 200)
        bereiche = aufmodul.gitterbereiche(bild)
        assert len(bereiche) == 1
        x0, y0, x1, y1 = bereiche[0]
        assert x1 - x0 > bild.shape[1] * 0.6 and y1 - y0 > bild.shape[0] * 0.1
        ohne = ocrmodul.erkenne_seite(d[0], ocrmodul.TesseractBackend(tabellen=False))
        mit = ocrmodul.erkenne_seite(d[0], ocrmodul.TesseractBackend(tabellen=True))
    assert _zellenwoerter(mit.text) >= 25
    assert _zellenwoerter(mit.text) >= _zellenwoerter(ohne.text) + 10
    assert "Kollegin," in mit.text  # the running text is still there
    with pymupdf.open(befund) as d:
        bild, _skala = aufmodul.rendere(d[0], 150)
        assert aufmodul.gitterbereiche(bild) == []


@braucht_backend
def test_gegliederter_ocr_text(tmp_path: Path, befund: Path) -> None:
    """An OCR page gets its structure: lines that ran to the margin are joined, blocks
    stay apart; without structure the raw lines come back."""
    lesung = lies(scan(befund, tmp_path / "scan.pdf"))
    try:
        seite = lesung.seiten[0]
        assert seite.gliederung is not None
        roh, gegliedert = seite.text.text, seite.markdown
        assert gegliedert != roh and "\n\n" in gegliedert
        rollen, zeilen = seite.gliederung.rollen, roh.split("\n")
        k = next(i for i, r in enumerate(rollen) if r.trenner == "wort")
        assert zeilen[k - 1].strip() + " " + zeilen[k].strip() in gegliedert
    finally:
        lesung.schliessen()
    ohne = lies(scan(befund, tmp_path / "scan2.pdf"), gliedern=False)
    try:
        assert ohne.seiten[0].gliederung is None
        assert ohne.seiten[0].markdown == ohne.seiten[0].text.text
    finally:
        ohne.schliessen()


# -- steps of the OCR layer on synthetic engine output ---------------------------------------------
def test_tesseract_tsv_zu_woertern() -> None:
    """Word rows only; pixel boxes shifted by the crop offset and scaled to points;
    a negative confidence is clamped; rows with unreadable numbers are skipped."""
    kopf = "\t".join(["level", "page_num", "block_num", "par_num", "line_num", "word_num",
                      "left", "top", "width", "height", "conf", "text"])
    tsv = "\n".join([
        kopf,
        "4\t1\t1\t1\t1\t0\t10\t20\t300\t40\t-1\t",
        "5\t1\t1\t1\t1\t1\t100\t200\t50\t20\t91.5\tHallo",
        "5\t1\t1\t1\t1\t2\t160\t200\t60\t20\t-1\t   ",
        "5\t1\t1\t1\t1\t3\t230\t200\t40\t20\t-1\tx",
        "5\t1\t1\t1\t1\t4\tabc\t200\t40\t20\t50\tkaputt",
    ])
    woerter = ocrmodul._woerter_aus_tsv(tsv, 2.0, (10.0, -20.0))
    assert [w.text for w in woerter] == ["Hallo", "x"]
    hallo = woerter[0]
    assert (hallo.x0, hallo.y0, hallo.x1, hallo.y1) == (55.0, 90.0, 80.0, 100.0)
    assert abs(hallo.konfidenz - 0.915) < 1e-9 and woerter[1].konfidenz == 0.0


def test_rapidocr_ergebnis_zu_woertern() -> None:
    """A line with the engine's word boxes keeps them (blank words dropped); a line
    without is split by character share; a result without boxes gives no words."""
    from types import SimpleNamespace

    box = [[0, 0], [200, 0], [200, 20], [0, 20]]
    wbox = [[10, 2], [50, 2], [50, 18], [10, 18]]
    ergebnis = SimpleNamespace(
        boxes=[box, box], txts=["Herr Max", "ab cd"], scores=[0.9, 0.8],
        word_results=[[("Herr", 0.95, wbox), (" ", 0.1, wbox)], []],
    )
    woerter = ocrmodul._woerter_aus_ergebnis(ergebnis, 2.0)
    assert [(w.text, w.konfidenz) for w in woerter] == [("Herr", 0.95), ("ab", 0.8), ("cd", 0.8)]
    assert (woerter[0].x0, woerter[0].y0, woerter[0].x1, woerter[0].y1) == (5.0, 1.0, 25.0, 9.0)
    assert (woerter[1].x0, woerter[1].x1) == (0.0, 40.0)
    assert (woerter[2].x0, woerter[2].x1) == (60.0, 100.0)
    assert ocrmodul._woerter_aus_ergebnis(SimpleNamespace(boxes=None), 1.0) == []


def test_bessere_lesung_ersetzt_nur_bei_mehr_konfidenz() -> None:
    """The second pass replaces the words inside the grid's box only when its reading
    carries more confidence mass; words reaching outside the box are never touched."""
    kasten = (0.0, 0.0, 100.0, 50.0)
    innen = [OCRWort("Müll", 10, 10, 30, 20, 0.3), OCRWort("##", 40, 10, 60, 20, 0.9)]
    rand = [OCRWort("Rand", 90, 10, 120, 20, 0.1)]  # reaches out of the box
    aussen = [OCRWort("Text", 200, 10, 240, 20, 0.9)]
    neu = [OCRWort("Dosis", 10, 10, 60, 20, 0.8)]
    assert ocrmodul._bessere_lesung(aussen + innen + rand, neu, kasten) == aussen + rand + neu
    schwach = [OCRWort("Do", 10, 10, 60, 20, 0.5)]
    assert ocrmodul._bessere_lesung(aussen + innen, schwach, kasten) == aussen + innen


def test_breite_luecken_werden_tabs() -> None:
    """A gap far wider than the usual one becomes a tab, but only once the page has at
    least four gaps to tell what usual means."""
    def zeile(y: float, texte: list[str], xs: list[float]) -> list[OCRWort]:
        return [OCRWort(t, x, y, x + 6 * len(t), y + 10, 0.9)
                for t, x in zip(texte, xs, strict=True)]

    woerter = (zeile(100, ["Medikament", "Dosis"], [50, 300])
               + zeile(120, ["a", "b", "c"], [50, 60, 70])
               + zeile(140, ["d", "e", "f"], [50, 60, 70]))
    s = seitentext_aus_woerter(woerter, 0, 595, 842)
    assert s.text.splitlines()[0] == "Medikament\tDosis"
    assert s.wortspannen[:2] == [(0, 10), (11, 16)] and len(s.konfidenzen) == 8
    wenige = zeile(100, ["Medikament", "Dosis"], [50, 300]) + zeile(120, ["a", "b"], [50, 60])
    assert "\t" not in seitentext_aus_woerter(wenige, 0, 595, 842).text


def test_zeile_unlesbar_regeln() -> None:
    """Three uncertain words, or the required share of them, make a line unreadable;
    a single uncertain word only when it is the whole line."""
    def lage(*unsicher: bool) -> list[ocrmodul._Wortlage]:
        return [ocrmodul._Wortlage(i * 3, i * 3 + 2, u) for i, u in enumerate(unsicher)]

    pruefe = ocrmodul._zeile_unlesbar
    assert not pruefe(lage(False, False, False), 0.4)
    assert pruefe(lage(True), 0.4)  # a single word is the whole line
    assert not pruefe(lage(True, False), 0.4)  # one fragment next to a read word
    assert pruefe(lage(True, True), 0.4)
    assert not pruefe(lage(True, False, False, False), 0.4)  # 25 % is below the share
    assert pruefe(lage(True, True, False, False, False), 0.4)
    assert pruefe(lage(True, True, True, False, False, False, False, False, False, False), 0.4)
    assert not pruefe(lage(True, True, False, False, False), 0.5)


def test_backend_auswahl_folgt_den_einstellungen(monkeypatch: pytest.MonkeyPatch) -> None:
    """"auto" takes the preference (of the environment, or what an application set)
    when it names an engine or "aus"; an unknown preference leaves "auto" in place; an
    unknown name is an error."""
    monkeypatch.setenv("OPTDOC_OCR", "aus")
    assert ocrmodul._bevorzugtes_backend("auto") == "aus"
    assert ocrmodul.backend("AUTO") is None and ocrmodul.backend("") is None
    setze_einstellungen(Einstellungen(ocr_backend="zauber"))
    assert ocrmodul._bevorzugtes_backend("auto") == "auto"
    assert ocrmodul._bevorzugtes_backend("tesseract") == "tesseract"
    with pytest.raises(ocrmodul.OCRFehler, match="Unbekanntes OCR-Backend: 'zauber'"):
        ocrmodul.backend("Zauber")
