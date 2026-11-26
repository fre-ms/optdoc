"""The window, driven without a screen: the clean-up changes the project's plans, the
text panel its corrections, and the three ways out end as they say; the words are there
in both languages."""

from __future__ import annotations

import ast
import string
from pathlib import Path

import pytest

from optdoc import cleanup
from optdoc import ocr as ocrlib
from optdoc.project import Project
from tests.synthetic import scan

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from optdoc.gui.window import EditWindow  # noqa: E402
from optdoc.gui.words import WORDS, Words  # noqa: E402

needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                   reason="no OCR engine installed")
needs_opencv = pytest.mark.skipif(not cleanup.available(), reason="needs OpenCV")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication(["optdoc"])


@pytest.fixture
def scanned(tmp_path: Path, report: Path) -> Path:
    return scan(report, tmp_path / "scan.pdf", rotation=2.0)


def test_words_in_both_languages() -> None:
    """Every word has the same placeholders in English and German, and every word the
    window asks for exists."""
    for key, (english, german) in WORDS.items():
        fields = [{f for _, f, _, _ in string.Formatter().parse(t) if f} for t in (english, german)]
        assert fields[0] == fields[1], key
    used: set[str] = set()
    for path in (Path(__file__).resolve().parents[1] / "optdoc" / "gui").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "w" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                used.add(node.args[0].value)
    assert used and used <= set(WORDS), used - set(WORDS)
    assert Words("de")("page", number=3) == "Seite 3" and Words("en")("apply") == "Apply"


@needs_opencv
def test_clean_up_by_hand(app: QApplication, scanned: Path) -> None:
    """Switches, masks, rotation, the suggestion and copying to every page go into the
    project's plans."""
    project = Project.open(scanned)
    window = EditWindow(project, Words("de"), synchronous=True)
    try:
        panel = window.cleanup
        assert panel.boxes["straighten"].isChecked()  # the suggestion is shown
        panel.boxes["contrast"].setChecked(True)
        assert project.plan(0).contrast and project.pages[0].decided
        panel.add_mask((10, 10, 60, 40))
        panel.add_mask((80, 10, 120, 40))
        panel.undo()
        assert project.plan(0).masks == [(10, 10, 60, 40)]
        panel.rotate(180)
        assert project.plan(0).rotation == 180 and project.plan(0).masks == []
        panel.copy_to_all()
        assert project.plan(1).contrast and project.plan(1).rotation == 0
        panel.skip()
        assert project.active_plan(0) is None and window.changed
        panel.restore()
        assert project.plan(0).straighten and not project.plan(0).contrast
        assert "begradigt" in panel.note.text()
    finally:
        window.outcome = "cancelled"
        window.close()
        project.close()


@needs_backend
def test_correct_the_text_and_apply(app: QApplication, scanned: Path) -> None:
    """A correction typed into the text goes into the project on leaving the page; back to
    the OCR text takes it back; a click on a printed word selects it; apply reads every
    page and closes as "applied"."""
    project = Project.open(scanned)
    window = EditWindow(project, Words("en"), synchronous=True)
    try:
        window.tabs.setCurrentWidget(window.text)
        panel = window.text
        original = panel.text.toPlainText()
        assert "Ramipril" in original and not panel.text.isReadOnly()
        ocr = project.ocr_text(0)
        a = ocr.text.index("Ramipril")
        box = ocr.rects(a, a + 8)[0]
        panel.select_word_at((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
        assert panel.text.textCursor().selectedText() == "Ramipril"
        panel.text.setPlainText(original.replace("Ramipril", "Ramiprill"))
        window.pages.setCurrentRow(1)  # leaving the page keeps the correction
        assert project.corrected == [0]
        assert window.pages.item(0).text() == "Page 1 ✎"
        window.pages.setCurrentRow(0)
        assert "Ramiprill" in panel.text.toPlainText() and panel.note.text().startswith("corrected")
        panel.reset_text()
        assert project.corrected == [] and panel.text.toPlainText() == original
        panel.text.setPlainText(original.replace("Ramipril", "Ramiprill"))
        window.apply()
        assert window.outcome == "applied" and project.corrected == [0]
        assert not any(project.needs_reading(n) for n in range(len(project.pages)))
    finally:
        project.close()


def test_later_and_cancel(app: QApplication, report: Path) -> None:
    """Save and continue later closes as "saved", cancel as "cancelled"; a born-digital PDF
    opens on the text, which cannot be changed."""
    for button, outcome in (("later_button", "saved"), ("cancel_button", "cancelled")):
        project = Project.open(report)
        window = EditWindow(project, Words("de"), synchronous=True)
        try:
            assert window.tabs.currentWidget() is window.text
            assert window.text.text.isReadOnly() and "Ramipril" in window.text.text.toPlainText()
            getattr(window, button).click()
            assert window.outcome == outcome
        finally:
            project.close()


@needs_opencv
def test_corners_dragged_and_turned(app: QApplication, tmp_path: Path, report: Path) -> None:
    """The sheet's corners are shown on the original and dragged there: the plan takes
    them and unwarps.  A quarter turn takes the corners with it; turning back brings
    them back.  A photo whose sheet optdoc did not find starts from the page's own
    corners, dashed."""
    import cv2

    from tests.synthetic import camera_photo

    image, _true = camera_photo(report, pitch=25, yaw=8)
    cv2.imwrite(str(tmp_path / "foto.jpg"), image)
    project = Project.open(tmp_path / "foto.jpg")
    window = EditWindow(project, Words("en"), synchronous=True)
    try:
        panel = window.cleanup
        found = project.plan(0).corners
        assert found and project.plan(0).unwarp
        assert len(panel.before._handles) == 4  # shown where they were found
        x, y = found[0]
        panel.before.move_corner(0, x + 5, y + 3)  # what a drag ends in
        assert project.plan(0).corners[0] == pytest.approx((x + 5, y + 3))
        moved = list(project.plan(0).corners)
        panel.rotate(90)
        assert project.plan(0).rotation == 90 and project.plan(0).corners != moved
        panel.rotate(270)
        assert project.plan(0).rotation == 0
        assert [c for p in project.plan(0).corners for c in p] == pytest.approx(
            [c for p in moved for c in p])
    finally:
        window.outcome = "cancelled"
        window.close()
        project.close()
    flat = tmp_path / "flach.png"
    cv2.imwrite(str(flat), cv2.imread(str(tmp_path / "foto.jpg"))[200:1400, 200:1000])
    project = Project.open(flat)  # a piece of the sheet, no edges: nothing found
    window = EditWindow(project, Words("de"), synchronous=True)
    try:
        assert project.plan(0) is None or not project.plan(0).corners
        panel = window.cleanup
        assert len(panel.before._handles) == 4
        assert panel.before._outline.pen().style() == Qt.PenStyle.DashLine
        assert "Ecken" in panel.note.text()
        panel.before.move_corner(2, 400, 600)
        assert project.plan(0).unwarp and project.plan(0).corners[2] == pytest.approx((400, 600))
    finally:
        window.outcome = "cancelled"
        window.close()
        project.close()


def _click(view, x: float, y: float, drag_to: tuple[float, float] | None = None) -> None:
    """A click (or a drag) with the mouse at page points ``(x, y)`` of a view."""
    from PySide6.QtCore import QPointF
    from PySide6.QtTest import QTest

    def at(px: float, py: float):
        return view.mapFromScene(QPointF(px * view.scale_factor, py * view.scale_factor))

    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=at(x, y))
    if drag_to is not None:
        QTest.mouseMove(view.viewport(), at((x + drag_to[0]) / 2, (y + drag_to[1]) / 2))
        QTest.mouseMove(view.viewport(), at(*drag_to))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton,
                       pos=at(*(drag_to or (x, y))))


@pytest.mark.skipif(not __import__("optdoc.tables").tables.available(),
                    reason="needs Camelot (extra 'tables')")
def test_areas_by_mouse(app: QApplication, tmp_path: Path) -> None:
    """The areas tab shows the table optdoc found; with the mouse a person adds a column
    line and takes it away, merges two cells, drags a line, draws a picture and makes it a
    stamp,
    deletes the table; each change is in the project at once; finding again brings
    optdoc's table back."""
    from optdoc.project import Options
    from tests.synthetic import lab_report

    pdf, _ = lab_report(tmp_path, 1)
    project = Project.open(pdf, Options(reader="none"))
    window = EditWindow(project, Words("en"), synchronous=True)
    window.resize(1300, 900)
    window.show()
    try:
        window.tabs.setCurrentWidget(window.areas)
        panel, view = window.areas, window.areas.view
        assert [r.kind for r in view.regions] == ["table"]
        table = view.regions[0]
        x0, y0, x1, y1 = table.box
        _click(view, x0 + 5, y0 + 5)
        assert view.selected == 0
        panel.use_tool("column")
        middle_of_first = (x0 + table.columns[0]) / 2
        _click(view, middle_of_first, (y0 + y1) / 2)
        assert len(project.regions(0)[0].columns) == len(table.columns) + 1
        assert project.regions_by_person(0)
        panel.use_tool("remove")
        _click(view, middle_of_first, (y0 + y1) / 2)
        assert project.regions(0)[0].columns == pytest.approx(table.columns)
        panel.use_tool("merge")
        row_middle = (table.rows[1] + table.rows[2]) / 2
        _click(view, x0 + 3, row_middle, drag_to=((table.columns[0] + table.columns[1]) / 2,
                                                  row_middle))
        assert project.regions(0)[0].merged == [(2, 0, 2, 1)]
        panel.use_tool("select")  # the table is still selected: drag its last column line
        last, bottom_row = table.columns[-1], (table.rows[-1] + y1) / 2
        _click(view, last, bottom_row, drag_to=(last + 12, bottom_row))
        assert project.regions(0)[0].columns[-1] == pytest.approx(last + 12, abs=1.5)
        panel.draw("image")
        _click(view, 400, 760, drag_to=(520, 800))
        assert [r.kind for r in project.regions(0)] == ["table", "image"]
        panel.kinds.setCurrentIndex(panel.kinds.findData("stamp"))  # the picture drawn: a stamp
        assert [r.kind for r in project.regions(0)] == ["table", "stamp"]
        panel.use_tool("select")
        _click(view, x0 + 5, y0 + 5)
        view.delete_selected()
        assert [r.kind for r in project.regions(0)] == ["stamp"] and window.changed
        panel.find_again()
        assert [r.kind for r in project.regions(0)] == ["table"]
        assert not project.regions_by_person(0)
    finally:
        window.outcome = "cancelled"
        window.close()
        project.close()
