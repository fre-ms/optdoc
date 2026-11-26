"""The preparation of one page, checked by eye: before and after side by side, every
step switchable, the sheet's corners dragged on the original, areas erased on the result.

From PseudonyMed's step "Aufbereiten".  The panel works on a :class:`~optdoc.project.
Project`; every change goes into the project at once (:meth:`Project.set_plan`).
"""

from __future__ import annotations

from collections.abc import Callable

from doccor.gui.view import PREVIEW_DPI, PageView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from optdoc import cleanup
from optdoc.errors import describe_error
from optdoc.gui.words import Words
from optdoc.project import Project

# the switches of the form, in the order of the plan's fields they set
_SWITCHES = ("straighten", "unwarp", "background", "borders", "denoise", "contrast", "sharpen",
             "grey")
_STRENGTHS = ("denoise", "contrast", "sharpen")
# what "copy the steps to every page" copies (not a page's own tilt, corners, masks or
# colour, which each page has of its own)
_COPIED = ("background", "borders", "denoise", "denoise_strength", "contrast",
           "contrast_strength", "sharpen", "sharpen_strength")


class CleanupPanel(QWidget):
    """The clean-up of the page :meth:`show_page` names."""

    changed = Signal(int)  # the plan of this page changed

    def __init__(self, project: Project, words: Words, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.w = words
        self.number = 0
        self.plan = cleanup.CleanupPlan()
        self._muted = False
        outer = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_views())
        splitter.addWidget(self._build_controls())
        splitter.setSizes([820, 320])
        outer.addWidget(splitter)
        undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        undo.activated.connect(self.undo)

    # -- building ------------------------------------------------------------------------------
    def _build_views(self) -> QSplitter:
        """Before and after, linked in scroll and zoom; masks are drawn on the after."""
        views = QSplitter(Qt.Orientation.Horizontal)
        self.before, self.after = PageView(), PageView()
        self.after.drawing = True
        self.after.box_drawn.connect(self.add_mask)
        self.before.corners_moved.connect(self.set_corners)
        PageView.link(self.before, self.after)
        for view, title in ((self.before, self.w("before")), (self.after, self.w("after"))):
            column = QWidget()
            layout = QVBoxLayout(column)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(title)
            label.setWordWrap(True)
            layout.addWidget(label)
            layout.addWidget(view, 1)
            views.addWidget(column)
        views.setSizes([410, 410])
        return views

    def _build_controls(self) -> QWidget:
        """The column on the right: note, steps, further steps, page buttons, zoom."""
        right = QWidget()
        r = QVBoxLayout(right)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        r.addWidget(self.note)
        r.addWidget(self._build_steps())
        r.addWidget(self._build_further())
        r.addLayout(self._build_page_buttons())
        r.addStretch(1)
        r.addLayout(self._build_zoom())
        self.controls = right
        return right

    def _check(self, key: str, tip: str = "") -> QCheckBox:
        """A switch of the form, written back into the plan when it changes."""
        box = QCheckBox(self.w(key))
        if tip:
            box.setToolTip(self.w(tip))
        box.toggled.connect(lambda _on: self._from_form())
        return box

    def _build_steps(self) -> QGroupBox:
        """Tilt, sheet, background, colour, rotation and the masks."""
        group = QGroupBox(self.w("steps"))
        form = QFormLayout(group)
        self.boxes: dict[str, QCheckBox] = {}
        self.boxes["straighten"] = self._check("straighten")
        self.angle = QDoubleSpinBox()
        self.angle.setRange(-15.0, 15.0)
        self.angle.setSingleStep(0.1)
        self.angle.setDecimals(1)
        self.angle.setSuffix("°")
        self.angle.valueChanged.connect(lambda _v: self._from_form())
        line = QHBoxLayout()
        line.addWidget(self.boxes["straighten"], 1)
        line.addWidget(self.angle)
        form.addRow(line)
        self.boxes["unwarp"] = self._check("unwarp")
        form.addRow(self.boxes["unwarp"])
        for key, tip in (("background", "background_tip"), ("grey", "grey_tip")):
            self.boxes[key] = self._check(key, tip)
            form.addRow(self.boxes[key])
        rotate = QHBoxLayout()
        for text, degrees in (("↺ 90°", 270), ("↻ 90°", 90), ("180°", 180)):
            button = QPushButton(text)
            button.clicked.connect(lambda _c=False, g=degrees: self.rotate(g))
            rotate.addWidget(button)
        form.addRow(self.w("rotate"), rotate)
        masks = QHBoxLayout()
        for key, action in (("undo_mask", self.undo), ("clear_masks", self.clear_masks)):
            button = QPushButton(self.w(key))
            button.clicked.connect(action)
            masks.addWidget(button)
        form.addRow(masks)
        return group

    def _build_further(self) -> QGroupBox:
        """Borders, the three steps with a strength, orientation."""
        group = QGroupBox(self.w("further"))
        form = QFormLayout(group)
        self.sliders: dict[str, QSlider] = {}
        for key in ("borders", "denoise", "contrast", "sharpen"):
            self.boxes[key] = self._check(key)
            if key in _STRENGTHS:
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(1, 5)
                slider.setMaximumWidth(140)
                slider.setToolTip(self.w("strength"))
                slider.valueChanged.connect(
                    lambda _v, s=slider: None if s.isSliderDown() else self._from_form())
                slider.sliderReleased.connect(self._from_form)
                self.boxes[key].toggled.connect(slider.setEnabled)
                self.sliders[key] = slider
                line = QHBoxLayout()
                line.addWidget(self.boxes[key], 1)
                line.addWidget(slider)
                form.addRow(line)
            else:
                form.addRow(self.boxes[key])
        self.orientation = QPushButton(self.w("orientation"))
        self.orientation.setToolTip(self.w("orientation_tip"))
        self.orientation.clicked.connect(self.detect_orientation)
        form.addRow(self.orientation)
        return group

    def _build_page_buttons(self) -> QVBoxLayout:
        """Restore the suggestion, leave the page alone, copy the steps to every page."""
        buttons = QVBoxLayout()
        for key, action in (("restore", self.restore), ("skip", self.skip),
                            ("steps_to_all", self.copy_to_all)):
            button = QPushButton(self.w(key))
            button.clicked.connect(action)
            buttons.addWidget(button)
        return buttons

    def _build_zoom(self) -> QHBoxLayout:
        """Zoom buttons for both views."""
        zoom = QHBoxLayout()
        actions: list[tuple[str, Callable[[], None]]] = [
            ("+", lambda: self.after.zoom(1.25)), ("−", lambda: self.after.zoom(0.8)),
            (self.w("zoom_reset"), self.after.reset_zoom)]
        for text, action in actions:
            button = QPushButton(text)
            button.setMaximumWidth(48)
            button.clicked.connect(action)
            zoom.addWidget(button)
        zoom.addStretch(1)
        return zoom

    # -- the page ------------------------------------------------------------------------------
    def show_page(self, number: int) -> None:
        """Show page ``number`` with its plan."""
        self.number = number
        cleanable = self.project.cleanable(number)
        self.controls.setEnabled(cleanable)
        self.plan = self.project.plan(number) or cleanup.CleanupPlan()
        self._to_form()
        self.draw()

    def _to_form(self) -> None:
        """Fill the form from the plan, without writing back."""
        a = self.plan
        self._muted = True
        try:
            for key in _SWITCHES:
                self.boxes[key].setChecked(bool(getattr(a, key)))
            self.boxes["unwarp"].setEnabled(bool(a.corners))
            self.angle.setValue(a.angle)
            for key, slider in self.sliders.items():
                slider.setValue(getattr(a, f"{key}_strength"))
                slider.setEnabled(bool(getattr(a, key)))
        finally:
            self._muted = False

    def _from_form(self) -> None:
        """Take the form into the plan and the project, and redraw."""
        if self._muted:
            return
        a = self.plan
        for key in _SWITCHES:
            setattr(a, key, self.boxes[key].isChecked())
        a.unwarp = a.unwarp and bool(a.corners)
        a.angle = self.angle.value()
        for key, slider in self.sliders.items():
            setattr(a, f"{key}_strength", slider.value())
        self._commit()

    def _commit(self, by_person: bool = True) -> None:
        """Hand the plan to the project, redraw, and say that it changed."""
        self.project.set_plan(self.number, self.plan, by_person)
        self.draw()
        self.changed.emit(self.number)

    # -- actions -------------------------------------------------------------------------------
    def _size(self, rotation: int) -> tuple[float, float]:
        """The page's width and height in points once turned by ``rotation``."""
        rect = self.project.original[self.number].rect
        return (rect.width, rect.height) if rotation in (0, 180) else (rect.height, rect.width)

    def rotate(self, degrees: int) -> None:
        """Turn the page by quarter turns; the sheet's corners turn with it, masks drawn
        on the old orientation go."""
        if self.plan.corners:
            self.plan.corners = cleanup.turn_points(self.plan.corners, degrees % 360,
                                                    self._size(self.plan.rotation))
        self.plan.rotation = (self.plan.rotation + degrees) % 360
        self.plan.masks = []
        self._commit()

    def set_corners(self, corners: list[tuple[float, float]]) -> None:
        """The sheet's corners as the person dragged them on the original page (points),
        kept on the turned page as the plan has them; unwarping goes on."""
        self.plan.corners = cleanup.turn_points(corners, self.plan.rotation, self._size(0))
        self.plan.unwarp = True
        self._to_form()
        self._commit()

    def add_mask(self, rect: tuple[float, float, float, float]) -> None:
        """Erase an area (points of the result page) white."""
        self.plan.masks.append(rect)
        self.plan.mask_colour = "white"
        self._commit()

    def undo(self) -> None:
        """Take back the last area erased."""
        if self.plan.masks:
            self.plan.masks.pop()
            self._commit()

    def clear_masks(self) -> None:
        """Take back every area erased."""
        if self.plan.masks:
            self.plan.masks = []
            self._commit()

    def restore(self) -> None:
        """optdoc's suggestion again."""
        self.plan = self.project.suggestion(self.number)
        self._to_form()
        self._commit(by_person=False)

    def skip(self) -> None:
        """Every step off: the page is read as it came."""
        self.plan = cleanup.CleanupPlan(corners=self.plan.corners, angle=self.plan.angle,
                                        grey=self.plan.grey)
        self._to_form()
        self._commit()

    def copy_to_all(self) -> None:
        """The switches of this page (not its tilt, corners or masks) on every page that
        can be cleaned up; straightening and unwarping only where the page has a tilt or
        corners of its own."""
        for n in range(len(self.project.pages)):
            if n == self.number or not self.project.cleanable(n):
                continue
            target = self.project.plan(n) or cleanup.CleanupPlan()
            for name in _COPIED:
                setattr(target, name, getattr(self.plan, name))
            target.straighten = self.plan.straighten and abs(target.angle) >= 0.05
            target.unwarp = self.plan.unwarp and bool(target.corners)
            self.project.set_plan(n, target)
            self.changed.emit(n)

    def detect_orientation(self) -> None:
        """Turn the page upright: portrait or landscape from the lines, upside down by a
        short OCR comparison where ocrdoc is installed."""
        try:
            degrees = self.project.orientation(self.number)
        except Exception as e:  # said in the note, the page stays as it is
            self.note.setText(self.w("orientation_failed",
                                     error=describe_error(e, self.w.language)))
            return
        self.plan.rotation = degrees
        self.plan.masks = []
        self._commit()

    # -- drawing -------------------------------------------------------------------------------
    def _show_corners(self) -> None:
        """The sheet's corners on the original page, to be dragged: those of the plan
        (turned back), else the page's own, dashed, as a start."""
        a = self.plan
        if a.corners:
            back = (360 - a.rotation) % 360
            self.before.show_corners(cleanup.turn_points(a.corners, back, self._size(a.rotation)))
            return
        w, h = self._size(0)
        inset = 0.03 * min(w, h)
        self.before.show_corners([(inset, inset), (w - inset, inset), (w - inset, h - inset),
                                  (inset, h - inset)], found=False)

    def draw(self) -> None:
        """Both views and the note describing the steps."""
        n = self.number
        self.before.scale_factor = PREVIEW_DPI / 72.0
        self.before.display(self.project.original_png(n, PREVIEW_DPI))
        if not self.project.cleanable(n):
            self.after.scale_factor = PREVIEW_DPI / 72.0
            self.after.display(self.project.original_png(n, PREVIEW_DPI))
            self.note.setText(self.w("has_layer") if cleanup.available()
                              else self.w("no_opencv_cleanup"))
            return
        self._show_corners()
        try:
            png, _scale = self.project.preview(n, self.plan, PREVIEW_DPI)
        except Exception as e:  # shown instead of breaking the window
            self.note.setText(self.w("cleanup_failed", error=describe_error(e, self.w.language)))
            return
        image = QImage.fromData(png)
        self.after.scale_factor = image.width() / self.project.cleaned_width(n, self.plan)
        self.after.set_base((PREVIEW_DPI / 72.0) / self.after.scale_factor)
        self.after.display(png)
        text = cleanup.describe(self.plan, self.w.language)
        if self.plan.corners is None:
            text += " · " + self.w("no_sheet")
        self.note.setText(text)
