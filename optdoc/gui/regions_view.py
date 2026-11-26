"""The page with its regions, to be corrected by hand (FineReader's way): regions drawn,
selected, moved and resized, their kind changed; a table's grid lines added, dragged
and taken away, its cells merged and split again.

The view knows the regions (:mod:`optdoc.layout`) and the tool in use, and says when
the person has changed them (``regions_changed``); the panel around it keeps them in
the project.  Shift or Option/Alt and drag, or the middle button, moves the view, as in
every view of the window; Ctrl/Cmd and the wheel zooms.
"""

from __future__ import annotations

from dataclasses import dataclass

from doccor.gui.view import PageView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)

from optdoc import layout
from optdoc.layout import Region

# FineReader's colours where it has the kind
COLOURS = {
    "text": QColor(0, 150, 60), "table": QColor(0, 90, 220), "image": QColor(210, 40, 40),
    "barcode": QColor(130, 60, 200), "handwriting": QColor(225, 130, 0),
    "stamp": QColor(200, 0, 140), "ignore": QColor(120, 120, 120),
}
TOOLS = ("select", "draw", "column", "row", "remove", "merge")
HANDLE = 5.0  # half the side of a corner handle, in screen pixels
NEAR = 6.0  # how close (screen pixels) a click must come to a line or a corner


@dataclass
class _Drag:
    """What a drag in progress does: its kind ("move", "resize", "line", "draw",
    "merge"), the region it works on (None while drawing), where it started (points),
    the corner or line it holds, and what the region was before."""

    kind: str
    index: int | None
    start: tuple[float, float]
    part: tuple[int, int] = (0, 0)  # resize: (corner, 0); line: (axis, index)
    before: Region | None = None
    preview: Region | None = None
    moved: bool = False


class RegionsView(PageView):
    """The regions of one page over its image; see the module."""

    regions_changed = Signal(object)  # the regions after a change, list[Region]
    selection_changed = Signal(object)  # the index of the region selected, or None
    tool_changed = Signal(str)  # the tool, when the view itself changes it (Escape)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.regions: list[Region] = []
        self.selected: int | None = None
        self.tool = "select"
        self.kind = "text"  # the kind of a region drawn
        self.names: dict[str, str] = {}  # the kinds' names, for the labels
        self._drag: _Drag | None = None
        self._items: list[QGraphicsItem] = []
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # -- showing ---------------------------------------------------------------------------
    def show_regions(self, png: bytes, regions: list[Region]) -> None:
        """Show the page image and its regions."""
        self.display(png)
        self._items = []
        self.regions = [layout.copy(r) for r in regions]
        if self.selected is not None and self.selected >= len(self.regions):
            self.select(None)
        self._draw()

    def set_regions(self, regions: list[Region]) -> None:
        """New regions over the same image (after a change outside the view)."""
        self.regions = [layout.copy(r) for r in regions]
        if self.selected is not None and self.selected >= len(self.regions):
            self.select(None)
        self._draw()

    def select(self, index: int | None) -> None:
        """Select a region (None: none)."""
        if index != self.selected:
            self.selected = index
            self.selection_changed.emit(index)
        self._draw()

    def _draw(self) -> None:
        """Every region, the one dragged as it is now, and the band of a drag."""
        for item in self._items:
            self._scene.removeItem(item)
        self._items = []
        drag = self._drag
        for k, region in enumerate(self.regions):
            if drag is not None and drag.index == k and drag.preview is not None:
                region = drag.preview
            self._draw_region(k, region)
        if drag is not None and drag.kind in ("draw", "merge") and drag.preview is not None:
            band = QGraphicsRectItem(self._rect(drag.preview.box))
            pen = QPen(COLOURS.get(self.kind if drag.kind == "draw" else "table", BLACK), 1.5,
                       Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            band.setPen(pen)
            self._add(band)

    def _add(self, item: QGraphicsItem) -> None:
        self._scene.addItem(item)
        self._items.append(item)

    def _draw_region(self, k: int, region: Region) -> None:
        """One region: its box in its kind's colour, lightly filled, its number and kind,
        a table's grid (no line inside merged cells), and corner handles when selected."""
        colour = COLOURS.get(region.kind, BLACK)
        selected = k == self.selected
        box = QGraphicsRectItem(self._rect(region.box))
        pen = QPen(colour, 2.5 if selected else 1.5)
        pen.setCosmetic(True)
        box.setPen(pen)
        fill = QColor(colour)
        fill.setAlpha(45 if selected else 25)
        box.setBrush(QBrush(fill))
        self._add(box)
        label = QGraphicsSimpleTextItem(f"{k + 1} {self.names.get(region.kind, region.kind)}")
        label.setBrush(QBrush(colour))
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        f = self.scale_factor
        inset = (2 * HANDLE + 2) / max(self.transform().m11(), 1e-6)  # clear of the handle
        at = (region.box[0] * f + inset, region.box[1] * f + inset / 3)
        backing = QGraphicsRectItem(label.boundingRect().adjusted(-2, 0, 2, 0))
        backing.setPen(QPen(Qt.PenStyle.NoPen))
        backing.setBrush(QBrush(QColor(255, 255, 255, 210)))  # readable over print
        for item in (backing, label):
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            item.setPos(*at)
            self._add(item)
        if region.kind == "table":
            self._draw_grid(region, colour)
        if selected:
            for x, y in _corners(region.box):
                handle = QGraphicsRectItem(-HANDLE, -HANDLE, 2 * HANDLE, 2 * HANDLE)
                handle.setPos(x * f, y * f)
                handle.setPen(pen)
                handle.setBrush(QBrush(QColor(255, 255, 255, 220)))
                handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
                self._add(handle)

    def _draw_grid(self, region: Region, colour: QColor) -> None:
        """The inner lines of a table, piece by piece, left out between merged cells."""
        f = self.scale_factor
        pen = QPen(colour, 1.0)
        pen.setCosmetic(True)
        xs, ys = region.xs, region.ys
        n_rows, n_columns = region.size
        for i, x in enumerate(region.columns):
            for r in range(n_rows):
                if region.span_of(r, i) != region.span_of(r, i + 1):
                    self._add(_line(x * f, ys[r] * f, x * f, ys[r + 1] * f, pen))
        for i, y in enumerate(region.rows):
            for c in range(n_columns):
                if region.span_of(i, c) != region.span_of(i + 1, c):
                    self._add(_line(xs[c] * f, y * f, xs[c + 1] * f, y * f, pen))

    # -- where the mouse is ------------------------------------------------------------------
    def _point(self, event: QMouseEvent) -> tuple[float, float]:
        """The point under the mouse, in page points."""
        p = self.mapToScene(event.position().toPoint())
        return p.x() / self.scale_factor, p.y() / self.scale_factor

    def _near(self) -> float:
        """NEAR screen pixels in page points, at the zoom shown."""
        return NEAR / max(self.transform().m11() * self.scale_factor, 1e-6)

    def _region_at(self, x: float, y: float) -> int | None:
        """The region under a point: of those that hold it, the smallest."""
        holding = [k for k, r in enumerate(self.regions)
                   if r.box[0] <= x <= r.box[2] and r.box[1] <= y <= r.box[3]]
        if not holding:
            return None
        return min(holding, key=lambda k: _area(self.regions[k].box))

    def _table_at(self, x: float, y: float) -> int | None:
        """The table under a point: the one selected where it holds the point, else the
        smallest that does."""
        near = self._near()
        selected = self.selected
        if selected is not None and self.regions[selected].kind == "table" \
                and _inside(self.regions[selected].box, x, y, near):
            return selected
        tables = [k for k, r in enumerate(self.regions)
                  if r.kind == "table" and _inside(r.box, x, y, near)]
        return min(tables, key=lambda k: _area(self.regions[k].box)) if tables else None

    def _line_at(self, region: Region, x: float, y: float) -> tuple[int, int] | None:
        """The inner line of a table near a point: (axis, index), axis 1 for a column
        line, 0 for a row line; the nearer one where both are near."""
        near = self._near()
        best: tuple[float, tuple[int, int]] | None = None
        if region.box[1] - near <= y <= region.box[3] + near:
            for i, line in enumerate(region.columns):
                if abs(x - line) <= near and (best is None or abs(x - line) < best[0]):
                    best = (abs(x - line), (1, i))
        if region.box[0] - near <= x <= region.box[2] + near:
            for i, line in enumerate(region.rows):
                if abs(y - line) <= near and (best is None or abs(y - line) < best[0]):
                    best = (abs(y - line), (0, i))
        return None if best is None else best[1]

    # -- the mouse -----------------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Start what the tool does here; Shift, Option/Alt or the middle button move the
        view."""
        moving = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier
        if event.modifiers() & moving or event.button() == Qt.MouseButton.MiddleButton:
            super().mousePressEvent(event)
            return
        self.setFocus()
        x, y = self._point(event)
        self._drag = self._begin(x, y)
        self._draw()

    def _begin(self, x: float, y: float) -> _Drag | None:
        """The drag that a press at a point starts with the tool in use."""
        if self.tool == "draw":
            return _Drag("draw", None, (x, y))
        if self.tool == "merge":
            k = self._table_at(x, y)
            return None if k is None else _Drag("merge", None, (x, y), part=(k, 0))
        if self.tool in ("column", "row", "remove"):
            k = self._table_at(x, y)
            return None if k is None else _Drag(self.tool, k, (x, y))
        # select: a corner or a grid line of the region selected, else a region to move
        if self.selected is not None:
            region = self.regions[self.selected]
            for c, (cx, cy) in enumerate(_corners(region.box)):
                if abs(x - cx) <= self._near() and abs(y - cy) <= self._near():
                    return _Drag("resize", self.selected, (x, y), (c, 0), region)
            if region.kind == "table":
                line = self._line_at(region, x, y)
                if line is not None:
                    return _Drag("line", self.selected, (x, y), line, region)
        k = self._region_at(x, y)
        self.select(k)
        return None if k is None else _Drag("move", k, (x, y), before=self.regions[k])

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Show what the drag would make."""
        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            super().mouseMoveEvent(event)
            return
        drag = self._drag
        if drag is None:
            return
        x, y = self._point(event)
        if abs(x - drag.start[0]) + abs(y - drag.start[1]) > self._near() / 2:
            drag.moved = True
        if not drag.moved:
            return
        drag.preview = self._previewed(drag, x, y)
        self._draw()

    def _previewed(self, drag: _Drag, x: float, y: float) -> Region | None:
        """The region a drag makes, with the mouse at ``(x, y)``."""
        x0, y0 = drag.start
        if drag.kind in ("draw", "merge"):
            return Region("text", (min(x0, x), min(y0, y), max(x0, x), max(y0, y)))
        before = drag.before
        if before is None:
            return None
        if drag.kind == "move":
            dx, dy = x - x0, y - y0
            b = before.box
            return layout.moved(before, (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy))
        if drag.kind == "resize":
            corners = _corners(before.box)
            opposite = corners[(drag.part[0] + 2) % 4]
            box = (min(x, opposite[0]), min(y, opposite[1]), max(x, opposite[0]),
                   max(y, opposite[1]))
            if box[2] - box[0] < layout.SMALLEST or box[3] - box[1] < layout.SMALLEST:
                return before
            return layout.moved(before, box)
        if drag.kind == "line":
            axis, index = drag.part
            return layout.move_line(before, axis, index, y if axis == 0 else x)
        return None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finish what the drag does, and say so when the regions changed."""
        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            super().mouseReleaseEvent(event)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        drag, self._drag = self._drag, None
        if drag is None:
            self._draw()
            return
        x, y = self._point(event)
        changed = self._finish(drag, x, y)
        self._draw()
        if changed:
            self.regions_changed.emit([layout.copy(r) for r in self.regions])

    def _finish(self, drag: _Drag, x: float, y: float) -> bool:
        """Apply a finished drag; True when the regions changed."""
        if drag.kind == "draw":
            box = (min(drag.start[0], x), min(drag.start[1], y),
                   max(drag.start[0], x), max(drag.start[1], y))
            if not drag.moved or box[2] - box[0] < 4 or box[3] - box[1] < 4:
                return False
            self.regions.append(Region(self.kind, box, "person"))
            self.select(len(self.regions) - 1)
            return True
        if drag.kind == "merge":
            k = drag.part[0]
            table = self.regions[k]
            first, last = table.cell_at(*drag.start), table.cell_at(x, y)
            if first is None or last is None:
                return False
            if first == last:
                if table.span_of(*first) == (*first, *first):
                    return False  # a plain cell: nothing to split
                self.regions[k] = layout.split(table, *first)
            else:
                self.regions[k] = layout.merge(table, (*first, *last))
            self.select(k)
            return True
        if drag.kind in ("column", "row", "remove"):
            return self._tool_click(drag)
        if drag.index is None or not drag.moved:
            return False
        preview = self._previewed(drag, x, y)
        if preview is None or preview == drag.before:
            return False
        self.regions[drag.index] = preview
        return True

    def _tool_click(self, drag: _Drag) -> bool:
        """A click with a grid tool on a table: a column or row line where it was clicked,
        or the line clicked taken away."""
        k = drag.index
        if k is None or drag.moved:
            return False
        table = self.regions[k]
        x, y = drag.start
        if drag.kind == "remove":
            line = self._line_at(table, x, y)
            changed = line is not None
            if line is not None:
                self.regions[k] = layout.remove_line(table, *line)
        else:
            axis = 1 if drag.kind == "column" else 0
            self.regions[k] = layout.add_line(table, axis, x if axis == 1 else y)
            changed = self.regions[k] is not table
        self.select(k)
        return changed

    # -- the keyboard ---------------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Delete or Backspace takes the region selected away; Escape goes back to
        selecting."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.tool = "select"
            self.tool_changed.emit("select")
            return
        super().keyPressEvent(event)

    def delete_selected(self) -> None:
        """Take the region selected away."""
        if self.selected is None:
            return
        del self.regions[self.selected]
        self.select(None)
        self.regions_changed.emit([layout.copy(r) for r in self.regions])

    def change_kind(self, kind: str) -> None:
        """Give the region selected another kind (a table loses its grid when it stops
        being one)."""
        if self.selected is None or self.regions[self.selected].kind == kind:
            return
        region = layout.copy(self.regions[self.selected])
        region.kind, region.by, region.confidence = kind, "person", None
        if kind != "table":
            region.columns, region.rows, region.merged = [], [], []
        if kind != "barcode":
            region.format = region.content = None
        self.regions[self.selected] = region
        self._draw()
        self.regions_changed.emit([layout.copy(r) for r in self.regions])


BLACK = QColor(0, 0, 0)


def _line(x0: float, y0: float, x1: float, y1: float, pen: QPen) -> QGraphicsLineItem:
    item = QGraphicsLineItem(x0, y0, x1, y1)
    item.setPen(pen)
    return item


def _corners(box: layout.Box) -> list[tuple[float, float]]:
    """The corners of a box: top left, top right, bottom right, bottom left."""
    return [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]


def _area(box: layout.Box) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _inside(box: layout.Box, x: float, y: float, margin: float = 0.0) -> bool:
    return box[0] - margin <= x <= box[2] + margin and box[1] - margin <= y <= box[3] + margin

