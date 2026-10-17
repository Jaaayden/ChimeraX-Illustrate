"""Qt tool window for capturing and rendering Illustrate scenes."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
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
    DEFAULT_OUTPUT_HEIGHT,
    DEFAULT_OUTPUT_WIDTH,
    DEFAULT_PREVIEW_SIZE,
    MAX_OUTPUT_SIZE,
    MAX_PREVIEW_SIZE,
    MIN_OUTPUT_SIZE,
    MIN_PREVIEW_SIZE,
    check_output_size,
    estimated_memory_gb,
    is_large_export,
    render_snapshot_to_png,
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
# Substituted into every message and help text that mentions a size limit.
SIZE_LIMITS = {
    "preview_min": MIN_PREVIEW_SIZE,
    "preview_max": MAX_PREVIEW_SIZE,
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
        self.setSuffix(" px")
        # Re-render when editing finishes, not on every typed digit.
        self.setKeyboardTracking(False)
        self.setValue(value)
        self.setMaximumWidth(115)

    def _typed_number(self, text):
        digits = text.replace(self.suffix(), "").strip()
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


class IllustrateTool(ToolInstance):
    SESSION_ENDURING = False
    SESSION_SAVE = False
    help = "help:user/tools/illustrate.html"

    def __init__(self, session, tool_name):
        super().__init__(session, tool_name)
        self._language = "en"
        self._scene: Optional[RenderScene] = None
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
        outer = QVBoxLayout(area)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

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
        self.output_width = self._new_size(
            DEFAULT_OUTPUT_WIDTH, MIN_OUTPUT_SIZE, MAX_OUTPUT_SIZE, "output_width"
        )
        size_row.addWidget(self.output_width, 1)
        size_row.addWidget(QLabel("\u00d7"))
        self.output_height = self._new_size(
            DEFAULT_OUTPUT_HEIGHT, MIN_OUTPUT_SIZE, MAX_OUTPUT_SIZE, "output_height"
        )
        size_row.addWidget(self.output_height, 1)
        outer.addLayout(size_row)

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
        outer.addWidget(self.preview, 1)

        self.status = ElidedLabel()
        outer.addWidget(self.status)

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
        outer.addLayout(footer)

        # --- advanced settings: hidden until the user asks for them ---------
        self.advanced = QTabWidget()
        self.advanced.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
        self.advanced.tabBar().setUsesScrollButtons(False)
        self.advanced.tabBar().setMinimumHeight(ROW_HEIGHT + 6)
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
        self.preview_size_label = self._row_label()
        general.addWidget(self.preview_size_label, 0, 0)
        self.preview_size = self._new_size(
            DEFAULT_PREVIEW_SIZE, MIN_PREVIEW_SIZE, MAX_PREVIEW_SIZE, "preview_size"
        )
        general.addWidget(self.preview_size, 0, 1)
        self.adjust_scene_checkbox = self._checkbox(checked=True)
        general.addWidget(self.adjust_scene_checkbox, 1, 0, 1, 2)
        self.size_hint = QLabel()
        self.size_hint.setWordWrap(True)
        self.size_hint.setEnabled(False)  # drawn in the muted text color
        self.size_hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        general.addWidget(self.size_hint, 2, 0, 1, 2)
        self.reset_button = self._button(self.reset_defaults)
        general.addWidget(self.reset_button, 3, 0, 1, 2)
        self._pack_page(general)
        self.advanced.addTab(general.parentWidget(), "")
        outer.addWidget(self.advanced)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(160)
        self._timer.timeout.connect(self._start_preview_render)

        for control in self._float_controls.values():
            control.valueChanged.connect(self._schedule_render)
        self.contour_kernel.valueChanged.connect(self._schedule_render)
        self.preview_size.valueChanged.connect(self._schedule_render)
        self._refresh_language()
        self.status.setText(self._tr("status_waiting"))

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
        self.preview_size_label.setText(self._tr("preview_size"))
        self.size_hint.setText(self._tr(
            "size_hint", preview_min=MIN_PREVIEW_SIZE, preview_max=MAX_PREVIEW_SIZE,
            export_min=MIN_OUTPUT_SIZE, export_max=MAX_OUTPUT_SIZE,
        ))
        self.output_width.setToolTip(self._tr("width_tooltip"))
        self.output_height.setToolTip(self._tr("height_tooltip"))
        self.preview_size.setToolTip(self._tr("preview_tooltip"))
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
        self._set_control_value(self.preview_size, DEFAULT_PREVIEW_SIZE)
        self._set_control_value(self.output_width, DEFAULT_OUTPUT_WIDTH)
        self._set_control_value(self.output_height, DEFAULT_OUTPUT_HEIGHT)

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
        size = self.preview_size.value()
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
        width = self.preview_size.value()
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
        path, _selected_filter = QFileDialog.getSaveFileName(
            self.tool_window.ui_area,
            self._tr("save_dialog"),
            "illustrate.png",
            "PNG (*.png)",
        )
        if path:
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
