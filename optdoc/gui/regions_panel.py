"""The areas of one page, found by optdoc and corrected by hand: text, tables with their
grids, pictures, barcodes, handwriting, stamps, and what is not to be read.

The panel works on a :class:`~optdoc.project.Project`: it shows the regions of a page
(:meth:`Project.regions`, found on the page once it is read, which may take seconds and
runs off the window's thread through ``prepare_page``), and every change a person makes
goes into the project at once (:meth:`Project.set_regions`).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from optdoc import layout
from optdoc.gui.regions_view import COLOURS, TOOLS, RegionsView
from optdoc.gui.view import PREVIEW_DPI
from optdoc.gui.words import Words
from optdoc.project import Project


class RegionsPanel(QWidget):
    """The areas of the page :meth:`show_page` names."""

    changed = Signal(int)  # the regions of this page changed

    def __init__(self, project: Project, words: Words,
                 prepare_page: Callable[[int, Callable[[], None]], None],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.w = words
        self.prepare_page = prepare_page  # read page n and find its regions, then call back
        self.number: int | None = None
        outer = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.view = RegionsView()
        self.view.names = {k: self.w(f"kind_{k}") for k in layout.KINDS}
        self.view.regions_changed.connect(self._regions_changed)
        self.view.selection_changed.connect(lambda _k: self._selected())
        self.view.tool_changed.connect(self._tool_from_view)
        splitter.addWidget(self.view)
        splitter.addWidget(self._build_controls())
        splitter.setSizes([860, 300])
        outer.addWidget(splitter)

    # -- building ------------------------------------------------------------------------------
    def _build_controls(self) -> QWidget:
        """The column on the right: note, kind, tools, the buttons, zoom."""
        right = QWidget()
        column = QVBoxLayout(right)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        column.addWidget(self.note)
        self.tools = QButtonGroup(self)
        self.tool_buttons: dict[str, QPushButton] = {}
        draw = QGroupBox(self.w("tool_draw"))
        grid = QGridLayout(draw)
        for i, name in enumerate(layout.KINDS):  # FineReader's way: a drawing tool per kind
            button = QPushButton(_swatch(name), self.w(f"kind_{name}"))
            button.setCheckable(True)
            button.setStyleSheet("text-align: left; padding: 3px 6px;")
            button.clicked.connect(lambda _c=False, n=name: self.draw(n))
            self.tools.addButton(button)
            self.tool_buttons[f"draw:{name}"] = button
            grid.addWidget(button, i // 2, i % 2)
        column.addWidget(draw)
        tools = QGroupBox(self.w("tools"))
        t = QVBoxLayout(tools)
        for name in (n for n in TOOLS if n != "draw"):
            button = QPushButton(self.w(f"tool_{name}"))
            button.setCheckable(True)
            button.setStyleSheet("text-align: left; padding: 4px 8px;")
            button.clicked.connect(lambda _c=False, n=name: self.use_tool(n))
            self.tools.addButton(button)
            self.tool_buttons[name] = button
            t.addWidget(button)
        self.tool_buttons["select"].setChecked(True)
        column.addWidget(tools)
        kind = QGroupBox(self.w("kind"))
        k = QVBoxLayout(kind)
        self.kinds = QComboBox()
        self.kinds.setToolTip(self.w("kind_tip"))
        for name in layout.KINDS:
            self.kinds.addItem(_swatch(name), self.w(f"kind_{name}"), name)
        self.kinds.currentIndexChanged.connect(self._kind_chosen)
        self.kinds.setEnabled(False)
        k.addWidget(self.kinds)
        column.addWidget(kind)
        for key, action in (("delete_region", self.view.delete_selected),
                            ("find_again", self.find_again)):
            button = QPushButton(self.w(key))
            button.clicked.connect(action)
            column.addWidget(button)
        help_text = QLabel(self.w("regions_help"))
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #555;")
        column.addWidget(help_text)
        column.addStretch(1)
        zoom = QHBoxLayout()
        for text, action in (("+", lambda: self.view.zoom(1.25)),
                             ("−", lambda: self.view.zoom(0.8)),
                             (self.w("zoom_reset"), self.view.reset_zoom)):
            button = QPushButton(text)
            button.setMaximumWidth(48)
            button.clicked.connect(action)
            zoom.addWidget(button)
        zoom.addStretch(1)
        column.addLayout(zoom)
        self.controls = right
        return right

    # -- the page ------------------------------------------------------------------------------
    def show_page(self, number: int) -> None:
        """Show page ``number`` with its areas, reading it and finding them first where
        needed."""
        self.number = number
        if self.project.needs_reading(number) or not self.project.has_regions(number):
            self.view.show_empty()
            self.controls.setEnabled(False)
            self.prepare_page(number, lambda: self._draw() if self.number == number else None)
            return
        self._draw()

    def _draw(self) -> None:
        """The page as OCR sees it, with its areas."""
        n = self.number
        if n is None:
            return
        self.controls.setEnabled(True)
        self.view.scale_factor = PREVIEW_DPI / 72.0
        self.view.show_regions(self.project.page_png(n, PREVIEW_DPI), self.project.regions(n))
        self._note()

    def _note(self) -> None:
        """Who set the areas, how many, and the grid of the table selected."""
        n = self.number
        if n is None:
            return
        regions = self.view.regions
        key = "regions_person" if self.project.regions_by_person(n) else "regions_auto"
        lines = [self.w(key, count=len(regions))]
        k = self.view.selected
        if k is not None and regions[k].kind == "table":
            rows, columns = regions[k].size
            lines.append(self.w("regions_table", rows=rows, columns=columns))
        if not self.project.finds_tables():
            lines.append(self.w("regions_no_tables"))
        self.note.setText("\n".join(lines))

    def _selected(self) -> None:
        """An area selected (or none): the chooser shows its kind and can change it."""
        k = self.view.selected
        self.kinds.setEnabled(k is not None)
        if k is not None:
            self.kinds.blockSignals(True)
            try:
                self.kinds.setCurrentIndex(layout.KINDS.index(self.view.regions[k].kind))
            finally:
                self.kinds.blockSignals(False)
        self._note()

    # -- changes -------------------------------------------------------------------------------
    def _regions_changed(self, regions: list[layout.Region]) -> None:
        """The person changed the areas: into the project."""
        if self.number is None:
            return
        self.project.set_regions(self.number, regions)
        self._note()
        self.changed.emit(self.number)

    def _kind_chosen(self, _index: int) -> None:
        """Another kind for the area selected."""
        self.view.change_kind(str(self.kinds.currentData()))

    def use_tool(self, name: str) -> None:
        """Work with a tool (``draw`` through :meth:`draw`)."""
        self.view.tool = name
        self.tool_buttons[name].setChecked(True)

    def draw(self, kind: str) -> None:
        """Draw areas of a kind; nothing stays selected, so that nothing else changes."""
        self.view.select(None)
        self.view.tool, self.view.kind = "draw", kind
        self.tool_buttons[f"draw:{kind}"].setChecked(True)

    def _tool_from_view(self, name: str) -> None:
        self.tool_buttons[name].setChecked(True)

    def find_again(self) -> None:
        """Forget the areas of the page (a person's too) and let optdoc find them."""
        if self.number is None:
            return
        self.project.forget_regions(self.number)
        self.changed.emit(self.number)
        self.show_page(self.number)


def _swatch(kind: str) -> QIcon:
    """A small square in a kind's colour."""
    swatch = QPixmap(12, 12)
    swatch.fill(COLOURS.get(kind, QColor(0, 0, 0)))
    return QIcon(swatch)
