"""A page as an image, zoomable, with boxes on it; two views can move together.

From PseudonyMed's review step.  Dragging draws a box (a mask, in the clean-up), a click
names a point (a word, in the text check); Shift or Option/Alt and drag, or the middle
button, moves the view; Ctrl/Cmd and the wheel zooms.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QMouseEvent, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QScrollBar,
    QWidget,
)

PREVIEW_DPI = 100
YELLOW = QColor(230, 165, 0)
GREY = QColor(120, 120, 120)
Box = tuple[float, float, float, float]


class PageView(QGraphicsView):
    """One page as an image with boxes; see the module."""

    box_drawn = Signal(object)  # (x0, y0, x1, y1) in page points
    point_selected = Signal(float, float)  # a click: x, y in page points
    scrolled = Signal(float, float)  # relative scroll position (0..1, 0..1)
    zoomed = Signal(float)  # zoom factor relative to the base scale

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.scale_factor = PREVIEW_DPI / 72.0  # pixels of the image per page point
        self.base_scale = 1.0  # shows a larger image at the size of a plain one
        self.drawing = False  # dragging draws a box
        self._start: QPointF | None = None
        self._band: QGraphicsRectItem | None = None
        self._follows = False
        self.horizontalScrollBar().valueChanged.connect(self._emit_scroll)
        self.verticalScrollBar().valueChanged.connect(self._emit_scroll)

    # -- showing -------------------------------------------------------------------------------
    def display(self, png: bytes, boxes: Sequence[tuple[Box, QColor, str]] = ()) -> None:
        """Show the page image and a box per ``(box in points, colour, tooltip)``."""
        self._scene.clear()
        image = QImage.fromData(png)
        self._scene.addItem(QGraphicsPixmapItem(QPixmap.fromImage(image)))
        self._scene.setSceneRect(0, 0, image.width(), image.height())
        for box, colour, note in boxes:
            item = QGraphicsRectItem(self._rect(box))
            item.setPen(QPen(colour, 1.5))
            fill = QColor(colour)
            fill.setAlpha(40)
            item.setBrush(QBrush(fill))
            if note:
                item.setToolTip(note)
            self._scene.addItem(item)

    def show_empty(self) -> None:
        """Show nothing."""
        self._scene.clear()

    def _rect(self, box: Box) -> QRectF:
        """A box in page points as a rectangle of the scene (pixels of the image)."""
        f = self.scale_factor
        return QRectF(box[0] * f, box[1] * f, (box[2] - box[0]) * f, (box[3] - box[1]) * f)

    # -- zoom and linked views ----------------------------------------------------------------
    @property
    def zoom_factor(self) -> float:
        """The zoom chosen, relative to the base scale."""
        return self.transform().m11() / self.base_scale

    def set_base(self, base: float) -> None:
        """Change the base scale, keeping the zoom chosen."""
        factor = self.zoom_factor
        self.base_scale = base
        self.follow_zoom(factor)

    def zoom(self, factor: float) -> None:
        """Zoom by ``factor`` and tell a linked view."""
        self.scale(factor, factor)
        if not self._follows:
            self.zoomed.emit(self.zoom_factor)

    def reset_zoom(self) -> None:
        """Back to the base scale; a linked view follows."""
        self.resetTransform()
        self.scale(self.base_scale, self.base_scale)
        self.zoomed.emit(self.zoom_factor)

    def follow_zoom(self, factor: float) -> None:
        """Take a zoom factor from a linked view."""
        self._follows = True
        try:
            self.resetTransform()
            self.scale(factor * self.base_scale, factor * self.base_scale)
        finally:
            self._follows = False

    def follow_scroll(self, x: float, y: float) -> None:
        """Move to the same relative position as a linked view."""
        self._follows = True
        try:
            for bar, value in ((self.horizontalScrollBar(), x), (self.verticalScrollBar(), y)):
                bar.setValue(round(value * bar.maximum()))
        finally:
            self._follows = False

    def _emit_scroll(self, _value: int) -> None:
        """Tell a linked view where this one is, unless it is following right now."""
        if not self._follows:
            self.scrolled.emit(_share(self.horizontalScrollBar()),
                               _share(self.verticalScrollBar()))

    @staticmethod
    def link(a: PageView, b: PageView) -> None:
        """Keep two views congruent: pan or zoom one, the other follows."""
        a.scrolled.connect(b.follow_scroll)
        b.scrolled.connect(a.follow_scroll)
        a.zoomed.connect(b.follow_zoom)
        b.zoomed.connect(a.follow_zoom)

    # -- the mouse -----------------------------------------------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: N802
        """Ctrl/Cmd and the wheel zoom; the plain wheel scrolls."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Shift, Option/Alt or the middle button move the view; else start a box."""
        moving = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier
        if event.modifiers() & moving or event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            if event.button() == Qt.MouseButton.MiddleButton:
                event = QMouseEvent(event.type(), event.position(), event.globalPosition(),
                                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                    event.modifiers())
            super().mousePressEvent(event)
            return
        self._start = self.mapToScene(event.position().toPoint())
        if self.drawing:
            self._band = QGraphicsRectItem(QRectF(self._start, self._start))
            self._band.setPen(QPen(GREY, 1.5))
            self._scene.addItem(self._band)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Grow the box while dragging."""
        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            super().mouseMoveEvent(event)
            return
        if self._start is not None and self._band is not None:
            pos = self.mapToScene(event.position().toPoint())
            self._band.setRect(QRectF(self._start, pos).normalized())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """A box when one was drawn, else a click on a point."""
        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            super().mouseReleaseEvent(event)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        if self._start is None:
            return
        f = self.scale_factor
        if self._band is not None:
            r = self._band.rect()
            self._scene.removeItem(self._band)
            self._band = None
            if r.width() > 4 and r.height() > 4:
                self.box_drawn.emit((r.left() / f, r.top() / f, r.right() / f, r.bottom() / f))
                self._start = None
                return
        self.point_selected.emit(self._start.x() / f, self._start.y() / f)
        self._start = None


def _share(bar: QScrollBar) -> float:
    """A scroll bar's position as a share of its range (0 when it cannot scroll)."""
    return bar.value() / bar.maximum() if bar.maximum() > 0 else 0.0
