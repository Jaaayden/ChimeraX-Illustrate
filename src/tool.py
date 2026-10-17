"""Qt tool window for capturing and rendering Illustrate scenes."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import os
from dataclasses import replace
from typing import Dict, Optional

from chimerax.core.errors import UserError
from chimerax.core.tools import ToolInstance
from chimerax.ui import MainToolWindow
from Qt.QtCore import QRect, QRectF, QSize, Qt, QTimer
from Qt.QtGui import QColor, QImage, QPainter, QPixmap, QTextOption, QValidator
from Qt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .export import (
    FALLBACK_STEM,
    DEFAULT_OUTPUT_HEIGHT,
    DEFAULT_OUTPUT_WIDTH,
    DEFAULT_PREVIEW_SIZE,
    EXPORT_PRESET_SIZES,
    MAX_OUTPUT_SIZE,
    MIN_OUTPUT_SIZE,
    check_output_size,
    default_export_filename,
    estimated_memory_gb,
    is_large_export,
    render_snapshot_to_png,
    snapshot_name,
)
from .i18n import (
    PALETTE_LABELS,
    PARAMETER_HELP_HTML_EN,
    PARAMETER_HELP_HTML_ZH,
    PARAMETER_LABELS,
    PARAMETER_TOOLTIPS_EN,
    PARAMETER_TOOLTIPS_ZH,
    UI_TEXT,
)
from .palette import (
    apply_chain_palette as color_chains,
    available_palette_presets,
    preset_prefers_atom_colors,
)
from .render import (
    IllustrationStyle,
    RenderScene,
    RenderedImage,
    ViewSnapshot,
    clear_caches,
    render_scaled,
)
from .scene import WARNING_PERSPECTIVE
from .scene import capture_scene as capture_chimerax_scene


DEFAULT_STYLE = IllustrationStyle()
# Minimum height of a row of labels/checkboxes.  Latin and CJK fonts have
# different line heights; a common minimum keeps the layout the same in both.
ROW_HEIGHT = 26
# Width of the controls column when the preview sits beside it.
SIDE_PANEL_WIDTH = 310
# Substituted into every message and help text that mentions a size limit.
SIZE_LIMITS = {
    "export_min": MIN_OUTPUT_SIZE,
    "export_max": MAX_OUTPUT_SIZE,
}

class SizeSpinBox(QSpinBox):
    """Pixel-size box that accepts any number and clamps it to its range.

    A plain QSpinBox silently refuses digits that would exceed the maximum,
    which looks like a broken input field.  This one lets the user type the
    number, then limits it when editing finishes and reports the change
    through ``on_clamp(box, requested, applied)``.
    """

    def __init__(self, value, low, high, key, on_clamp=None):
        super().__init__()
        self.size_key = key
        self.on_clamp = on_clamp
        self.setRange(low, high)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Re-render when editing finishes, not on every typed digit.
        self.setKeyboardTracking(False)
        self.setValue(value)
        self.setFixedWidth(70)

    def _typed_number(self, text):
        digits = text.strip()
        return int(digits) if digits.isdigit() and len(digits) <= 9 else None

    def validate(self, text, pos):
        if self._typed_number(text) is not None:
            return QValidator.State.Acceptable, text, pos
        return super().validate(text, pos)

    def valueFromText(self, text):
        requested = self._typed_number(text)
        if requested is None:
            return super().valueFromText(text)
        applied = max(self.minimum(), min(self.maximum(), requested))
        if applied != requested and self.on_clamp is not None:
            self.on_clamp(self, requested, applied)
        return applied


class PreviewView(QWidget):
    """Preview area whose size never depends on the image or text it shows.

    A QLabel holding a pixmap reports the pixmap size as its minimum size, so
    every new preview (or a language change) could resize the whole tool
    window.  This widget paints the image scaled into whatever space it gets.
    """

    def __init__(self):
        super().__init__()
        self._pixmap = None
        self._text = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(320, 300)

    def minimumSizeHint(self):
        return QSize(200, 160)

    def set_image(self, qimage):
        self._pixmap = QPixmap.fromImage(qimage)
        self._text = ""
        self.update()

    def set_text(self, text):
        self._pixmap = None
        self._text = text
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#dddddd"))
        painter.setPen(QColor("#999999"))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        if self._pixmap is not None:
            target = self._pixmap.size().scaled(
                self.size() - QSize(2, 2), Qt.AspectRatioMode.KeepAspectRatio
            )
            left = (self.width() - target.width()) // 2
            top = (self.height() - target.height()) // 2
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(
                QRect(left, top, target.width(), target.height()), self._pixmap
            )
        elif self._text:
            painter.setPen(QColor("#555555"))
            painter.drawText(
                QRectF(self.rect().adjusted(10, 10, -10, -10)),
                self._text,
                QTextOption(Qt.AlignmentFlag.AlignCenter),
            )
        painter.end()


class ElidedLabel(QLabel):
    """Single-line label that clips long text instead of widening the window."""

    def __init__(self):
        super().__init__()
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.fontMetrics().height() + 6)

    def setText(self, text):  # noqa: N802 (Qt naming)
        self._full_text = text
        self.setToolTip(text)
        self.update()

    def text(self):
        return self._full_text

    def minimumSizeHint(self):
        return QSize(10, self.height())

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        shown = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, self.width()
        )
        painter.drawText(
            QRectF(self.rect()), shown,
            QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        )
        painter.end()


class AdaptiveScrollArea(QScrollArea):
    """Scroll area that tells its owner how much room it has.

    The tool switches between a stacked and a side-by-side layout depending on
    that room, and scrolls vertically instead of squeezing the preview when
    the window is short (for example when it shares a dock with the Log).
    """

    def __init__(self, on_resize):
        super().__init__()
        self._on_resize = on_resize
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def sizeHint(self):
        return QSize(700, 400)

    def minimumSizeHint(self):
        return QSize(290, 200)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = self.viewport().size()
        self._on_resize(size.width(), size.height())


class IllustrateTool(ToolInstance):
    SESSION_ENDURING = False
    SESSION_SAVE = False
    # Folder of the last export, shared by all tool windows of this run.
    _last_export_dir = os.path.expanduser("~")
    help = "help:user/tools/illustrate.html"

    def __init__(self, session, tool_name):
        super().__init__(session, tool_name)
        self._language = "en"
        self._scene: Optional[RenderScene] = None
        self._snapshot_name = FALLBACK_STEM
        self._view: Optional[ViewSnapshot] = None
        self._style_state = IllustrationStyle()
        self._capture_width = DEFAULT_PREVIEW_SIZE
        self._capture_height = DEFAULT_PREVIEW_SIZE
        self._generation = 0
        # Previews and exports use separate workers so a long export never
        # blocks the live preview, and the export result does not depend on
        # the preview generation counter.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="illustrate")
        self._export_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="illustrate-export"
        )
        self._preview_future: Optional[Future] = None
        self._closed = False
        self._locked = False
        self._float_controls: Dict[str, QDoubleSpinBox] = {}
        self._parameter_labels: Dict[str, QLabel] = {}
        self._pages = []

        self.tool_window = MainToolWindow(self)
        self._build_ui()
        self.tool_window.manage(placement="side")

    def _build_ui(self):
        area = self.tool_window.ui_area
        frame = QVBoxLayout(area)
        frame.setContentsMargins(0, 0, 0, 0)
        self._scroll = AdaptiveScrollArea(self._on_area_resized)
        frame.addWidget(self._scroll)
        content = QWidget()
        self._scroll.setWidget(content)
        self._root = QGridLayout(content)
        self._root.setContentsMargins(8, 8, 8, 8)
        self._root.setSpacing(6)
        self._layout_mode = None
        # Three blocks that are stacked (narrow window) or arranged side by
        # side (wide window): the basic controls, the preview, the settings.
        self._controls = QWidget()
        outer = self._panel_layout(self._controls)
        self._viewer = QWidget()
        viewer = self._panel_layout(self._viewer)
        self._settings = QWidget()
        settings = self._panel_layout(self._settings)

        # --- the basics: capture, export, size, colors, three options -------
        actions = QHBoxLayout()
        self.capture_button = self._button(self.capture_scene)
        self.save_button = self._button(self._choose_save_path)
        self.save_button.setEnabled(False)
        actions.addWidget(self.capture_button, 1)
        actions.addWidget(self.save_button, 1)
        outer.addLayout(actions)

        size_row = QHBoxLayout()
        self.export_size_label = self._row_label()
        size_row.addWidget(self.export_size_label)
        self.size_combo = QComboBox()
        self.size_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.size_combo.setMinimumContentsLength(8)
        for edge in EXPORT_PRESET_SIZES:
            self.size_combo.addItem("%d \u00d7 %d" % (edge, edge), edge)
        self.size_combo.addItem("", "custom")
        self.size_combo.setCurrentIndex(EXPORT_PRESET_SIZES.index(DEFAULT_OUTPUT_WIDTH))
        size_row.addWidget(self.size_combo, 1)
        outer.addLayout(size_row)

        # Width and height are only shown for "Custom": most people pick a
        # preset and never need them.
        self.custom_size = QWidget()
        custom_row = QHBoxLayout(self.custom_size)
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.setSpacing(6)
        self.output_width = self._new_size(
            DEFAULT_OUTPUT_WIDTH, MIN_OUTPUT_SIZE, MAX_OUTPUT_SIZE, "output_width"
        )
        self.output_height = self._new_size(
            DEFAULT_OUTPUT_HEIGHT, MIN_OUTPUT_SIZE, MAX_OUTPUT_SIZE, "output_height"
        )
        custom_row.addStretch(1)
        custom_row.addWidget(self.output_width)
        custom_row.addWidget(QLabel("\u00d7"))
        custom_row.addWidget(self.output_height)
        custom_row.addStretch(1)
        self.custom_size.setVisible(False)
        outer.addWidget(self.custom_size)
        self.size_combo.currentIndexChanged.connect(self._size_choice_changed)

        palette_row = QHBoxLayout()
        self.palette_label = self._row_label()
        palette_row.addWidget(self.palette_label)
        self.palette_combo = QComboBox()
        self.palette_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.palette_combo.setMinimumContentsLength(8)
        for preset in available_palette_presets():
            self.palette_combo.addItem("", preset)
        palette_row.addWidget(self.palette_combo, 1)
        self.palette_button = self._button(self.apply_chain_palette)
        self._reserve_button_width(self.palette_button, "apply_palette", extra=26)
        palette_row.addWidget(self.palette_button)
        outer.addLayout(palette_row)

        options = QHBoxLayout()
        self.transparent_checkbox = self._checkbox(checked=True)
        self.lock_checkbox = self._checkbox()
        self.lock_checkbox.toggled.connect(self._set_locked)
        self.prefer_atom_colors_checkbox = self._checkbox()
        for box in (self.transparent_checkbox, self.lock_checkbox,
                    self.prefer_atom_colors_checkbox):
            options.addWidget(box, 1)
        outer.addLayout(options)

        self.preview = PreviewView()
        viewer.addWidget(self.preview, 1)

        self.status = ElidedLabel()
        viewer.addWidget(self.status)

        # --- footer: advanced settings toggle, help, language ---------------
        footer = QHBoxLayout()
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setAutoRaise(True)
        self.advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._reserve_button_width(self.advanced_toggle, "advanced", extra=34)
        self.advanced_toggle.toggled.connect(self._set_advanced_visible)
        footer.addWidget(self.advanced_toggle)
        footer.addStretch(1)
        self.help_button = self._button(self.show_parameter_help, flat=True)
        self._reserve_button_width(self.help_button, "help")
        footer.addWidget(self.help_button)
        self.language_button = self._button(self._toggle_language, flat=True)
        self._reserve_button_width(self.language_button, "language")
        footer.addWidget(self.language_button)
        settings.addLayout(footer)

        # --- advanced settings: hidden until the user asks for them ---------
        self.advanced = QTabWidget()
        self.advanced.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
        self.advanced.tabBar().setUsesScrollButtons(False)
        self.advanced.tabBar().setMinimumHeight(ROW_HEIGHT + 6)
        # Tighter padding so the four titles fit the narrow controls column.
        self.advanced.tabBar().setStyleSheet("QTabBar::tab { padding: 5px 4px; }")
        self.advanced.tabBar().setExpanding(True)
        self.advanced.setVisible(False)
        # The tab titles differ per language; do not let them set the width.
        self.advanced.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        contours = self._settings_page()
        self._add_float(contours, "contour_low", DEFAULT_STYLE.contour_low, 0.0, 1000.0, 2)
        self._add_float(contours, "contour_high", DEFAULT_STYLE.contour_high, 0.0, 1000.0, 2)
        self.contour_kernel = self._add_int(
            contours, "contour_kernel", DEFAULT_STYLE.contour_kernel, 1, 4
        )
        self._add_float(contours, "contour_depth_min", DEFAULT_STYLE.contour_depth_min, 0.0, 1000.0, 2)
        self._add_float(contours, "contour_depth_max", DEFAULT_STYLE.contour_depth_max, 0.001, 1000.0, 2)
        self._pack_page(contours)
        self.advanced.addTab(contours.parentWidget(), "")

        boundaries = self._settings_page()
        self._add_float(boundaries, "subunit_low", DEFAULT_STYLE.subunit_low, 0.0, 1000.0, 2)
        self._add_float(boundaries, "subunit_high", DEFAULT_STYLE.subunit_high, 0.0, 1000.0, 2)
        self._add_float(boundaries, "residue_low", DEFAULT_STYLE.residue_low, 0.0, 1000.0, 2)
        self._add_float(boundaries, "residue_high", DEFAULT_STYLE.residue_high, 0.0, 1000.0, 2)
        self._add_float(boundaries, "residue_difference", DEFAULT_STYLE.residue_difference, 0.0, 100000.0, 1)
        self._pack_page(boundaries)
        self.advanced.addTab(boundaries.parentWidget(), "")

        shading = self._settings_page()
        self.shadow_checkbox = self._checkbox(checked=DEFAULT_STYLE.shadows)
        self.shadow_checkbox.toggled.connect(self._schedule_render)
        shading.addWidget(self.shadow_checkbox, 0, 0, 1, 2)
        shading.next_row = 1
        self._add_float(shading, "radius_scale", DEFAULT_STYLE.radius_scale, 0.0, 10.0, 3)
        self._add_float(shading, "shadow_contribution", DEFAULT_STYLE.shadow_contribution, 0.0, 1.0, 5)
        self._add_float(shading, "shadow_cone_angle", DEFAULT_STYLE.shadow_cone_angle, 0.0, 100.0, 3)
        self._add_float(shading, "shadow_depth", DEFAULT_STYLE.shadow_depth, 0.0, 100.0, 3)
        self._add_float(shading, "shadow_maximum", DEFAULT_STYLE.shadow_maximum, 0.0, 1.0, 3)
        self._add_float(shading, "fog_front", DEFAULT_STYLE.fog_front, 0.0, 1.0, 3)
        self._add_float(shading, "fog_back", DEFAULT_STYLE.fog_back, 0.0, 1.0, 3)
        self._pack_page(shading)
        self.advanced.addTab(shading.parentWidget(), "")

        general = self._settings_page()
        self.adjust_scene_checkbox = self._checkbox(checked=True)
        general.addWidget(self.adjust_scene_checkbox, 0, 0, 1, 2)
        general.next_row = 1
        self.reset_button = self._button(self.reset_defaults)
        general.addWidget(self.reset_button, 1, 0, 1, 2)
        self._pack_page(general)
        self.advanced.addTab(general.parentWidget(), "")
        settings.addWidget(self.advanced)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(160)
        self._timer.timeout.connect(self._start_preview_render)

        for control in self._float_controls.values():
            control.valueChanged.connect(self._schedule_render)
        self.contour_kernel.valueChanged.connect(self._schedule_render)
        self._apply_layout_mode("horizontal")
        self._refresh_language()
        self.status.setText(self._tr("status_waiting"))

    @staticmethod
    def _panel_layout(panel):
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        return layout

    def _apply_layout_mode(self, mode):
        """Stack the blocks (``vertical``) or put the preview beside them."""

        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        root = self._root
        for block in (self._controls, self._viewer, self._settings):
            root.removeWidget(block)
        for index in range(4):
            root.setRowStretch(index, 0)
            root.setColumnStretch(index, 0)
            root.setColumnMinimumWidth(index, 0)
        if mode == "vertical":
            root.addWidget(self._controls, 0, 0)
            root.addWidget(self._viewer, 1, 0)
            root.addWidget(self._settings, 2, 0)
            root.setRowStretch(1, 100)  # the preview takes spare height first,
            root.setRowStretch(3, 1)    # then the remainder goes below the settings
        else:
            root.addWidget(self._controls, 0, 0)
            root.addWidget(self._settings, 1, 0)
            root.addWidget(self._viewer, 0, 1, 3, 1)
            root.setRowStretch(2, 1)
            root.setColumnStretch(1, 1)
            root.setColumnMinimumWidth(0, SIDE_PANEL_WIDTH)
        for block in (self._controls, self._viewer, self._settings):
            block.show()

    def _on_area_resized(self, width, height):
        """Pick the layout that gives the (square) preview the most room."""

        mode = self._layout_mode or "horizontal"
        # Side by side is the default (a wide, short window is the usual
        # shape).  Stack the blocks only when the window is narrow or tall.
        # Different thresholds for switching there and back avoid flickering
        # between the two layouts while the user drags the window edge.
        if mode == "horizontal" and width < max(520, 0.95 * height):
            mode = "vertical"
        elif mode == "vertical" and width >= max(580, 1.15 * height):
            mode = "horizontal"
        self._apply_layout_mode(mode)
        if mode == "vertical":
            # The preview is square: ask for about that much height (scrolling
            # rather than squashing it when the window is short) and never
            # more than a square, so no gray bars appear above and below.
            smallest = int(max(220, min(0.9 * width, 400)))
            self.preview.setMinimumHeight(smallest)
            self.preview.setMaximumHeight(max(smallest, width - 16))
        else:
            self.preview.setMinimumHeight(200)
            self.preview.setMaximumHeight(16777215)

    @staticmethod
    def _button(handler, flat=False):
        """Push button whose width never depends on its (translated) text."""

        button = QPushButton()
        button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        button.setFlat(flat)
        button.clicked.connect(handler)
        return button

    def _reserve_button_width(self, button, key, extra=22):
        """Fix a button's width to its widest translation.

        Small footer buttons need a real width, and it must not change when
        the interface language is switched.
        """

        metrics = button.fontMetrics()
        widest = max(
            metrics.horizontalAdvance(UI_TEXT[language][key]) for language in UI_TEXT
        )
        button.setFixedWidth(widest + extra)
        # Latin and CJK fonts have different line heights; pin the height too.
        button.setFixedHeight(26)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    @staticmethod
    def _row_label():
        label = QLabel()
        label.setMinimumHeight(ROW_HEIGHT)
        return label

    @staticmethod
    def _checkbox(checked=False):
        box = QCheckBox()
        box.setChecked(checked)
        box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        box.setMinimumHeight(ROW_HEIGHT)
        return box

    def _settings_page(self):
        """Return the grid of a new settings tab (label column stretches)."""

        page = QWidget()
        self._pages.append(page)  # keep the page (and its layout) alive
        grid = QGridLayout(page)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(0, 1)
        grid.next_row = 0
        return grid

    @staticmethod
    def _pack_page(grid):
        """Keep a settings page's rows at the top of its tab."""

        grid.setRowStretch(grid.next_row, 1)

    def _set_advanced_visible(self, visible):
        self.advanced.setVisible(visible)
        self.advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )

    def _add_label(self, grid, key):
        label = QLabel()
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setMinimumHeight(ROW_HEIGHT)
        self._parameter_labels[key] = label
        row = grid.next_row
        grid.next_row += 1
        grid.addWidget(label, row, 0)
        return row

    def _add_int(self, grid, key, value, low, high):
        row = self._add_label(grid, key)
        control = self._new_int(value, low, high)
        grid.addWidget(control, row, 1)
        return control

    def _new_size(self, value, low, high, key):
        return SizeSpinBox(value, low, high, key, self._size_clamped)

    def _size_choice_changed(self, index):
        edge = self.size_combo.itemData(index)
        custom = edge == "custom"
        self.custom_size.setVisible(custom)
        if custom:
            return
        for box in (self.output_width, self.output_height):
            self._set_control_value(box, edge)
        if is_large_export(edge, edge):
            self._set_status(self._tr(
                "size_large_hint", width=edge, height=edge,
                gb="%.0f" % max(1.0, estimated_memory_gb(edge, edge)),
            ))

    def _select_size_preset(self, edge):
        """Select a preset (or Custom if ``edge`` is not one) and sync the boxes."""

        if edge in EXPORT_PRESET_SIZES:
            self.size_combo.setCurrentIndex(EXPORT_PRESET_SIZES.index(edge))
        else:
            self.size_combo.setCurrentIndex(self.size_combo.count() - 1)
        self._size_choice_changed(self.size_combo.currentIndex())

    def _size_clamped(self, box, _requested, applied):
        self._set_status(self._tr(
            "size_clamped", name=self._tr(box.size_key),
            low=box.minimum(), high=box.maximum(), value=applied,
        ))

    @staticmethod
    def _new_int(value, low, high):
        control = QSpinBox()
        control.setRange(low, high)
        control.setValue(value)
        control.setFixedWidth(100)
        return control

    def _add_float(self, grid, key, value, low, high, decimals):
        row = self._add_label(grid, key)
        control = QDoubleSpinBox()
        control.setRange(low, high)
        control.setDecimals(decimals)
        control.setSingleStep(0.1 if decimals <= 2 else 0.01)
        control.setValue(value)
        control.setFixedWidth(100)
        grid.addWidget(control, row, 1)
        self._float_controls[key] = control
        return control

    def _tr(self, key, **values):
        return UI_TEXT[self._language][key].format(**{**SIZE_LIMITS, **values})

    def _toggle_language(self):
        self._language = "zh" if self._language == "en" else "en"
        self._refresh_language()
        self._set_status(self._tr("status_language"))

    def _refresh_language(self):
        self.capture_button.setText(self._tr("capture"))
        self.save_button.setText(self._tr("save"))
        self.reset_button.setText(self._tr("reset"))
        self.help_button.setText(self._tr("help"))
        self.language_button.setText(self._tr("language"))
        self.advanced_toggle.setText(self._tr("advanced"))
        self.export_size_label.setText(self._tr("export_size"))
        self.palette_label.setText(self._tr("palette_label"))
        self.palette_button.setText(self._tr("apply_palette"))
        self.palette_button.setToolTip(self._tr("palette_tooltip"))
        self.transparent_checkbox.setText(self._tr("transparent"))
        self.transparent_checkbox.setToolTip(self._tr("transparent_tooltip"))
        self.lock_checkbox.setText(self._tr("lock"))
        self.lock_checkbox.setToolTip(self._tr("lock_tooltip"))
        self.prefer_atom_colors_checkbox.setText(self._tr("prefer_atom_colors"))
        self.prefer_atom_colors_checkbox.setToolTip(self._tr("prefer_atom_colors_tooltip"))
        self.adjust_scene_checkbox.setText(self._tr("adjust_scene"))
        self.adjust_scene_checkbox.setToolTip(self._tr("adjust_scene_tooltip"))
        self.size_combo.setItemText(self.size_combo.count() - 1, self._tr("size_custom"))
        self.size_combo.setToolTip(self._tr("export_size_tooltip"))
        self.output_width.setToolTip(self._tr("width_tooltip"))
        self.output_height.setToolTip(self._tr("height_tooltip"))
        for index, key in enumerate(
            ("tab_contours", "tab_boundaries", "tab_shading", "tab_general")
        ):
            self.advanced.setTabText(index, self._tr(key))
        self.shadow_checkbox.setText(self._tr("shadow_enabled"))
        for key, label in self._parameter_labels.items():
            label.setText(PARAMETER_LABELS[self._language][key])
            tooltip = (
                PARAMETER_TOOLTIPS_EN.get(key, "")
                if self._language == "en"
                else PARAMETER_TOOLTIPS_ZH.get(key, "")
            )
            label.setToolTip(tooltip)
            control = (
                self.contour_kernel
                if key == "contour_kernel"
                else self._float_controls[key]
            )
            control.setToolTip(tooltip)
        for index in range(self.palette_combo.count()):
            preset = self.palette_combo.itemData(index)
            self.palette_combo.setItemText(
                index, PALETTE_LABELS[self._language][preset]
            )
        if self._scene is None:
            self.preview.set_text(self._tr("preview_empty"))

    def _set_locked(self, locked):
        self._locked = bool(locked)
        self.capture_button.setEnabled(not self._locked)
        self._set_status(
            self._tr("status_locked")
            if self._locked
            else self._tr("status_unlocked")
        )

    def _set_status(self, message):
        self.status.setText(message)
        try:
            self.session.logger.status(message)
        except Exception:
            pass

    def _current_style(self):
        values = {key: control.value() for key, control in self._float_controls.items()}
        values["contour_kernel"] = self.contour_kernel.value()
        values["shadows"] = self.shadow_checkbox.isChecked()
        return replace(self._style_state, **values)

    @staticmethod
    def _set_control_value(control, value):
        blocked = control.blockSignals(True)
        try:
            control.setValue(value)
        finally:
            control.blockSignals(blocked)

    def reset_defaults(self):
        """Restore UI/render parameters without discarding the captured scene."""

        for key, control in self._float_controls.items():
            self._set_control_value(control, getattr(DEFAULT_STYLE, key))
        self._set_control_value(self.contour_kernel, DEFAULT_STYLE.contour_kernel)
        self._select_size_preset(DEFAULT_OUTPUT_WIDTH)

        blocked = self.shadow_checkbox.blockSignals(True)
        try:
            self.shadow_checkbox.setChecked(DEFAULT_STYLE.shadows)
        finally:
            self.shadow_checkbox.blockSignals(blocked)
        blocked = self.transparent_checkbox.blockSignals(True)
        try:
            self.transparent_checkbox.setChecked(True)
        finally:
            self.transparent_checkbox.blockSignals(blocked)

        style_values = {
            key: getattr(DEFAULT_STYLE, key) for key in self._float_controls
        }
        style_values.update({
            "contour_kernel": DEFAULT_STYLE.contour_kernel,
            "shadows": DEFAULT_STYLE.shadows,
        })
        self._style_state = replace(self._style_state, **style_values)
        self._set_status(self._tr("status_reset"))
        self._schedule_render()

    def show_parameter_help(self):
        dialog = QDialog(self.tool_window.ui_area)
        dialog.setWindowTitle(self._tr("help_title"))
        dialog.resize(620, 680)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(
            (
                PARAMETER_HELP_HTML_EN
                if self._language == "en"
                else PARAMETER_HELP_HTML_ZH
            ).format(**SIZE_LIMITS)
        )
        layout.addWidget(browser)
        close_button = QPushButton(self._tr("close"))
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()

    def capture_scene(self):
        """Capture the current ChimeraX scene; return whether it succeeded."""

        if self._locked:
            self._set_status(self._tr("capture_locked"))
            return False
        size = DEFAULT_PREVIEW_SIZE
        try:
            scene, view, style, warnings = capture_chimerax_scene(
                self.session, size, size,
                prefer_atom_colors=self.prefer_atom_colors_checkbox.isChecked(),
            )
        except Exception as error:
            self._invalidate_snapshot(
                self._tr("capture_failed", error=error)
            )
            return False
        if not scene.atoms:
            self._invalidate_snapshot(self._tr("capture_empty"))
            return False
        self._scene = scene
        self._view = view
        self._style_state = style
        self._snapshot_name = snapshot_name(self.session)
        self._capture_width = size
        self._capture_height = size
        self.save_button.setEnabled(True)
        message = self._tr("captured", count=len(scene.atoms))
        if WARNING_PERSPECTIVE in warnings:
            message += " — " + self._tr("perspective_warning")
        self._set_status(message)
        self._schedule_render()
        return True

    def apply_chain_palette(self):
        preset = self.palette_combo.currentData()
        try:
            assignments = color_chains(
                self.session,
                preset=preset,
                adjust_scene=self.adjust_scene_checkbox.isChecked(),
            )
        except Exception as error:
            self._set_status(self._tr("palette_failed", error=error))
            return
        if not assignments:
            self._set_status(self._tr("palette_empty"))
            return
        # Presets with atom-level colors (backbone vs. nucleobase) only show
        # up in cartoon/surface captures when atom colors are preferred.
        self.prefer_atom_colors_checkbox.setChecked(
            preset_prefers_atom_colors(preset)
        )
        self._set_status(
            self._tr(
                "palette_done",
                preset=PALETTE_LABELS[self._language][preset],
                count=len(assignments),
            )
        )

    def _invalidate_snapshot(self, message):
        self._generation += 1
        self._scene = None
        self._view = None
        clear_caches()
        self.save_button.setEnabled(False)
        self.preview.set_text(message)
        self._set_status(message)

    def clear_scene(self):
        self._invalidate_snapshot(self._tr("snapshot_empty"))
        self._set_status(self._tr("snapshot_cleared"))

    def has_snapshot(self):
        return self._scene is not None and self._view is not None

    def _schedule_render(self, *args):
        if self._scene is None or self._view is None:
            return
        self._timer.start()

    def _start_preview_render(self):
        if self._scene is None or self._view is None:
            return
        if self._preview_future is not None and not self._preview_future.done():
            # A queued stale preview can be cancelled; a currently running
            # NumPy render finishes normally and its generation is discarded.
            # This keeps rapid parameter edits from building a long work queue.
            self._preview_future.cancel()
        self._generation += 1
        generation = self._generation
        width = DEFAULT_PREVIEW_SIZE
        # The preview uses the same renderer as the export, so it shows the
        # style the exported PNG will have.
        self._preview_future = self._executor.submit(
            render_scaled, self._scene, self._view, self._current_style(),
            self._capture_width, width, width,
        )
        self._preview_future.add_done_callback(
            lambda future: self._deliver_render(generation, future)
        )

    def _call_in_ui_thread(self, function, *args):
        try:
            self.session.ui.thread_safe(function, *args)
        except Exception:
            # This fallback is useful for lightweight test doubles; ChimeraX's
            # real UI always provides thread_safe().
            function(*args)

    def _deliver_render(self, generation, future):
        try:
            image = future.result()
            error = None
        except Exception as caught:
            image = None
            error = caught
        self._call_in_ui_thread(self._finish_render, generation, image, error)

    def _finish_render(self, generation, image, error):
        if self._closed or generation != self._generation:
            return
        if error is not None:
            self._set_status(self._tr("render_failed", error=error))
            return
        self._show_image(image)
        self._set_status(self._tr("preview_updated"))

    def _show_image(self, image: RenderedImage):
        rgba = image.composited_rgba(transparent=False)
        format_rgba = getattr(QImage, "Format_RGBA8888", None)
        if format_rgba is None:
            format_rgba = QImage.Format.Format_RGBA8888
        qimage = QImage(rgba, image.width, image.height, image.width * 4, format_rgba).copy()
        self.preview.set_image(qimage)

    def _choose_save_path(self):
        if not self.has_snapshot():
            self._set_status(self._tr("need_capture"))
            return
        # Name the file after what is on screen and the chosen size, and start
        # in the folder used for the previous export.
        filename = default_export_filename(
            self._snapshot_name, self.output_width.value(), self.output_height.value()
        )
        path, _selected_filter = QFileDialog.getSaveFileName(
            self.tool_window.ui_area,
            self._tr("save_dialog"),
            os.path.join(IllustrateTool._last_export_dir, filename),
            "PNG (*.png)",
        )
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            IllustrateTool._last_export_dir = (
                os.path.dirname(path) or IllustrateTool._last_export_dir
            )
            self.save_image(path, transparent=self.transparent_checkbox.isChecked())

    def _prepare_export(self, width, height):
        """Validate an export request and freeze the state it renders from."""

        if not self.has_snapshot() or not self._scene.atoms:
            raise UserError(self._tr("invalid_scene"))
        width = int(width or self.output_width.value())
        height = int(height or self.output_height.value())
        problem = check_output_size(width, height)
        if problem == "minimum_size":
            raise UserError(self._tr("minimum_size"))
        if problem == "maximum_size":
            raise UserError(self._tr("maximum_size", maximum=MAX_OUTPUT_SIZE))
        return (
            self._scene, self._view, self._current_style(),
            self._capture_width, width, height,
        )

    def _rendering_notice(self, width, height):
        if is_large_export(width, height):
            return self._tr(
                "large_export", width=width, height=height,
                gb="%.0f" % max(1.0, estimated_memory_gb(width, height)),
            )
        return self._tr("rendering", width=width, height=height)

    def save_image(self, path, transparent=True, width=None, height=None,
                   wait=False):
        """Export the captured snapshot as a PNG.

        By default the render runs on a background worker and the result is
        reported in the status line.  With ``wait=True`` (used by the
        ``illustrate save`` command) the file is complete when this returns.
        """

        scene, view, style, capture_width, width, height = self._prepare_export(
            width, height
        )
        arguments = (
            scene, view, style, capture_width, width, height, path,
            bool(transparent),
        )
        notice = self._rendering_notice(width, height)
        if wait:
            self._set_status(notice)
            try:
                render_snapshot_to_png(*arguments)
            except Exception as caught:
                message = self._tr("save_failed", error=caught)
                self._set_status(message)
                raise UserError(message) from caught
            self._set_status(self._tr("saved", path=path))
            return path
        future = self._export_executor.submit(render_snapshot_to_png, *arguments)
        future.add_done_callback(self._deliver_save)
        self._set_status(notice)
        return None

    def _deliver_save(self, future):
        try:
            path = future.result()
            error = None
        except Exception as caught:
            path = None
            error = caught
        self._call_in_ui_thread(self._finish_save, path, error)

    def _finish_save(self, path, error):
        # Export results are always reported, even if the preview was
        # re-rendered meanwhile; only a closed tool has nowhere to report.
        if self._closed:
            return
        if error is not None:
            self._set_status(self._tr("save_failed", error=error))
            return
        self._set_status(self._tr("saved", path=path))

    def delete(self):
        self._closed = True
        self._generation += 1
        try:
            self._timer.stop()
        except Exception:
            pass
        self._executor.shutdown(wait=False, cancel_futures=True)
        # Let an export that is already running finish writing its file.
        self._export_executor.shutdown(wait=False)
        clear_caches()
        super().delete()
