"""The regions of a page and the grid of a table: changed as the window changes them,
kept in the configuration, and what they make of the result: cells from the grid,
words in regions that are not read left out, a person's regions kept or dropped as
the clean-up moves the page or not."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from optdoc import cleanup, layout, output, tables
from optdoc import ocr as ocrlib
from optdoc.errors import OptdocError
from optdoc.layout import Region
from optdoc.project import SUFFIX, Options, Project, load_config
from tests.synthetic import lab_report, scan

needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                   reason="no OCR engine installed")
needs_tables = pytest.mark.skipif(not tables.available(), reason="needs Camelot (extra 'tables')")


def _grid() -> Region:
    """A table of three rows and three columns, 100 by 60 points."""
    return Region("table", (0, 0, 300, 60), "auto", [100, 200], [20, 40])


def test_lines_added_moved_and_taken_away() -> None:
    """A line splits the cell it falls in; one too close to another is refused; a moved
    line stays between its neighbours; taking one away joins two rows or columns, and
    merged cells that then meet become one."""
    g = layout.add_line(_grid(), 1, 150)
    assert g.columns == [100, 150, 200] and g.size == (3, 4) and g.by == "person"
    assert layout.add_line(g, 1, 151) is g  # too close to the line at 150
    assert layout.move_line(g, 1, 1, 400).columns == [100, 200 - layout.SMALLEST, 200]
    g = layout.merge(g, (0, 0, 0, 1))
    g = layout.merge(g, (0, 2, 0, 3))
    assert g.merged == [(0, 0, 0, 1), (0, 2, 0, 3)]
    g = layout.remove_line(g, 1, 1)  # the line at 150 between both merges
    assert g.columns == [100, 200] and g.merged == [(0, 0, 0, 2)] and g.valid()
    assert layout.split(g, 0, 1).merged == []


def test_a_line_through_merged_cells() -> None:
    """A new line through merged cells keeps them merged, now over one more column."""
    g = layout.merge(_grid(), (1, 0, 1, 1))
    g = layout.add_line(g, 1, 50)
    assert g.merged == [(1, 0, 1, 2)] and g.valid()


def test_moving_a_table_takes_its_grid_along() -> None:
    """Moved and resized, a table keeps its rows and columns, in proportion."""
    g = layout.moved(_grid(), (10, 10, 160, 130))
    assert g.columns == [60, 110] and g.rows == [50, 90] and g.valid()


def test_words_into_cells() -> None:
    """Every word goes into the cell its middle lies in, lines top to bottom and words
    left to right; merged cells keep their text in the first, which spans them all."""
    words = [("3,5", (210, 22, 230, 30)), ("-", (232, 22, 236, 30)), ("5,1", (238, 22, 258, 30)),
             ("Kalium", (5, 22, 40, 30)), ("mmol/l", (110, 22, 140, 30)),
             ("Natrium", (5, 42, 45, 50)), ("135", (110, 42, 125, 50))]
    t = layout.table_of(_grid(), words)
    assert [c.text for c in t.rows[1]] == ["Kalium", "mmol/l", "3,5 - 5,1"]
    merged = layout.table_of(layout.merge(_grid(), (2, 0, 2, 1)), words)
    assert [c.text for c in merged.rows[2]] == ["Natrium 135", "", ""]
    assert merged.rows[2][0].box == (0, 40, 200, 60) and merged.by == "person"


def test_regions_in_the_configuration() -> None:
    """A region goes to the configuration and comes back the same; one that makes no
    sense is refused as a broken configuration."""
    g = layout.merge(_grid(), (0, 0, 1, 0))
    assert Region.from_dict(json.loads(json.dumps(g.as_dict()))) == g
    image = Region("image", (10, 10, 80, 40))
    assert Region.from_dict(image.as_dict()) == image
    for broken in ({"kind": "poster", "box": [0, 0, 9, 9]},
                   {"kind": "table", "box": [0, 0, 100, 50], "columns": [101]},
                   {"kind": "table", "box": [0, 0, 100, 50], "columns": [50], "rows": [25],
                    "merged": [[0, 0, 1, 1], [1, 1, 1, 1]]},
                   {"kind": "image", "box": [0, 0, 100, 50], "rows": [25]},
                   {"box": [0, 0, 9, 9]}):
        with pytest.raises(OptdocError) as caught:
            Region.from_dict(broken)
        assert (caught.value.kind, caught.value.details) == ("bad-config", {"reason": "field"})


def test_words_in_regions_not_read() -> None:
    """Words in a picture, a barcode or "ignore" are not read; in a smaller region drawn
    within, the smaller one decides."""
    regions = [Region("image", (0, 0, 100, 100)), Region("text", (10, 10, 50, 50))]
    assert layout.is_read(regions, (20, 20, 30, 30))  # in the text drawn within the picture
    assert not layout.is_read(regions, (60, 60, 70, 70))
    assert layout.is_read(regions, (120, 120, 130, 130))  # in no region: text


@needs_tables
def test_tables_found_and_set_by_hand(tmp_path: Path) -> None:
    """A born-digital report: its table is found with its grid; a person takes away the
    line between unit and range, and the cells, the reading and the configuration
    follow; the configuration made again gives the same files."""
    pdf, _ = lab_report(tmp_path, 1)
    project = Project.open(pdf, Options(reader="none"))
    try:
        found = project.regions(0)
        assert [r.kind for r in found] == ["table"] and found[0].size == (19, 5)
        table = found[0]
        changed = layout.remove_line(table, 1, 2)  # unit and range in one column
        project.set_regions(0, [changed])
        reading = project.build()
        try:
            first = output.write(reading, tmp_path / "a")
        finally:
            reading.close()
    finally:
        project.close()
    page = json.loads(first["reading"].read_text(encoding="utf-8"))["pages"][0]
    rows = page["tables"][0]["rows"]
    assert len(rows[0]) == 4 and page["tables"][0]["by"] == "person"
    kalium = next(r for r in rows if r[0]["text"] == "Kalium")
    assert kalium[2]["text"].startswith("mmol/l") and "5,1" in kalium[2]["text"]
    assert page["regions"] == [{"kind": "table", "box": page["regions"][0]["box"],
                                "by": "person", "table": 0}]
    config = load_config(first["config"])
    assert config["pages"][0]["layout"]["by"] == "person"
    again = Project.open(pdf, config=config)
    try:
        assert again.regions_by_person(0) and again.regions(0)[0].columns == changed.columns
        reading = again.build()
        try:
            second = output.write(reading, tmp_path / "b")
        finally:
            reading.close()
    finally:
        again.close()
    for key in ("pdf", "reading", "markdown", "config"):
        assert first[key].read_bytes() == second[key].read_bytes(), key


@needs_backend
def test_a_region_not_read_leaves_the_text(tmp_path: Path, report: Path) -> None:
    """On a scan, words in a region marked "ignore" are in neither the text, the text
    layer of the PDF, nor the reading; the region is in the reading."""
    source = scan(report, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        project.read(0)
        ocr = project.ocr_text(0)
        assert ocr is not None and "Ramipril" in ocr.text
        a = ocr.text.index("Ramipril")
        box = ocr.rects(a, a + 8)[0]
        project.set_regions(0, [Region("ignore", (box.x0 - 2, box.y0 - 2, box.x1 + 2, box.y1 + 2),
                                       "person")])
        assert "Ramipril" not in project.text(0)
        reading = project.build()
        try:
            paths = output.write(reading, tmp_path / "out")
        finally:
            reading.close()
    finally:
        project.close()
    with pymupdf.open(paths["pdf"]) as doc:
        assert "Ramipril" not in doc[0].get_text() and "Diagnosen" in doc[0].get_text()
    page = json.loads(paths["reading"].read_text(encoding="utf-8"))["pages"][0]
    assert "Ramipril" not in page["text"] and page["regions"][0]["kind"] == "ignore"


@needs_backend
def test_a_persons_regions_and_the_clean_up(tmp_path: Path, report: Path) -> None:
    """A person's regions stay when the clean-up changes only how the page looks (more
    contrast); when it moves the page (a quarter turn), they no longer fit and go."""
    source = scan(report, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        project.set_regions(0, [Region("stamp", (300, 600, 500, 700), "person")])
        plan = project.plan(0) or cleanup.CleanupPlan()
        plan.contrast = True
        project.set_plan(0, plan)
        assert project.regions_by_person(0) and project.regions(0)[0].kind == "stamp"
        plan.rotation = 90
        project.set_plan(0, plan)
        assert not project.regions_by_person(0)
        assert all(r.kind == "table" for r in project.regions(0))
        project.save(tmp_path / f"scan{SUFFIX}")
    finally:
        project.close()


def test_a_persons_grid_is_certain() -> None:
    """A table optdoc found has the finder's confidence; once a person changed its grid,
    the table is theirs and certain."""
    found = Region("table", (0, 0, 300, 60), "auto", [100, 200], [20, 40], [], 0.7)
    assert layout.table_of(found, []).confidence == 0.7
    changed = layout.move_line(found, 1, 0, 110)
    assert changed.by == "person" and layout.table_of(changed, []).confidence == 1.0


@needs_tables
def test_finding_tables_writes_nothing_elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               ) -> None:
    """Camelot writes a PDF it is given in memory to the temporary folder; optdoc gives it
    a path in the results folder, for a moment.  Nothing touches the temporary folder,
    not even briefly, and nothing is left in the results folder but the results."""
    import tempfile

    def refused(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("nothing may go to the temporary folder")

    for name in ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile",
                 "TemporaryDirectory", "SpooledTemporaryFile"):
        monkeypatch.setattr(tempfile, name, refused)
    pdf, _ = lab_report(tmp_path, 1)
    out = tmp_path / "out"
    project = Project.open(pdf, Options(reader="none"))
    project.scratch = out
    try:
        assert [r.kind for r in project.regions(0)] == ["table"]
        assert not out.exists()  # made for the moment, and taken away again
        reading = project.build()
        try:
            output.write(reading, out)
        finally:
            reading.close()
    finally:
        project.close()
    assert sorted(p.name for p in out.iterdir()) == sorted(
        ["lab-01.pdf", "lab-01.reading.json", "lab-01.md", f"lab-01{SUFFIX}"])
