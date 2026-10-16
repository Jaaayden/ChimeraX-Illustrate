"""Qt tool window for capturing and rendering Illustrate scenes."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from typing import Dict, Optional

from chimerax.core.errors import UserError
from chimerax.core.tools import ToolInstance
from chimerax.ui import MainToolWindow
from Qt.QtCore import Qt, QTimer
from Qt.QtGui import QImage, QPixmap, QValidator
from Qt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QTextBrowser,
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

        self.tool_window = MainToolWindow(self)
        self._build_ui()
        self.tool_window.manage(placement="side")

    def _build_ui(self):
        area = self.tool_window.ui_area
        outer = QVBoxLayout(area)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        actions = QHBoxLayout()
        self.capture_button = QPushButton()
        self.capture_button.clicked.connect(self.capture_scene)
        actions.addWidget(self.capture_button)
        self.save_button = QPushButton()
        self.save_button.clicked.connect(self._choose_save_path)
        self.save_button.setEnabled(False)
        actions.addWidget(self.save_button)
        self.reset_button = QPushButton()
        self.reset_button.clicked.connect(self.reset_defaults)
        actions.addWidget(self.reset_button)
        self.help_button = QPushButton()
        self.help_button.clicked.connect(self.show_parameter_help)
        actions.addWidget(self.help_button)
        self.language_button = QPushButton()
        self.language_button.clicked.connect(self._toggle_language)
        actions.addWidget(self.language_button)
        outer.addLayout(actions)

        palette_row = QHBoxLayout()
        self.palette_label = QLabel()
        palette_row.addWidget(self.palette_label)
        self.palette_combo = QComboBox()
        for preset in available_palette_presets():
            self.palette_combo.addItem("", preset)
        palette_row.addWidget(self.palette_combo, 1)
        self.palette_button = QPushButton()
        self.palette_button.clicked.connect(self.apply_chain_palette)
        palette_row.addWidget(self.palette_button)
        outer.addLayout(palette_row)

        self.adjust_scene_checkbox = QCheckBox()
        self.adjust_scene_checkbox.setChecked(True)
        outer.addWidget(self.adjust_scene_checkbox)

        options = QHBoxLayout()
        self.lock_checkbox = QCheckBox()
        self.lock_checkbox.toggled.connect(self._set_locked)
        options.addWidget(self.lock_checkbox)
        self.transparent_checkbox = QCheckBox()
        self.transparent_checkbox.setChecked(True)
        options.addWidget(self.transparent_checkbox)
        self.prefer_atom_colors_checkbox = QCheckBox()
        options.addWidget(self.prefer_atom_colors_checkbox)
        options.addStretch(1)
        outer.addLayout(options)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(260, 260)
        self.preview.setMaximumHeight(400)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.preview.setStyleSheet("QLabel { background: #dddddd; border: 1px solid #999999; }")
        outer.addWidget(self.preview)

        self.size_box = QGroupBox()
        size_layout = QGridLayout(self.size_box)
        size_layout.setContentsMargins(10, 6, 10, 6)
        self.preview_size_label = QLabel()
        size_layout.addWidget(self.preview_size_label, 0, 0)
        self.preview_size = self._new_size(
            DEFAULT_PREVIEW_SIZE, MIN_PREVIEW_SIZE, MAX_PREVIEW_SIZE, "preview_size"
        )
        size_layout.addWidget(self.preview_size, 0, 1)
        self.output_width_label = QLabel()
        size_layout.addWidget(self.output_width_label, 0, 2)
        self.output_width = self._new_size(
            DEFAULT_OUTPUT_WIDTH, MIN_OUTPUT_SIZE, MAX_OUTPUT_SIZE, "output_width"
        )
        size_layout.addWidget(self.output_width, 0, 3)
        self.output_height_label = QLabel()
        size_layout.addWidget(self.output_height_label, 0, 4)
        self.output_height = self._new_size(
            DEFAULT_OUTPUT_HEIGHT, MIN_OUTPUT_SIZE, MAX_OUTPUT_SIZE, "output_height"
        )
        size_layout.addWidget(self.output_height, 0, 5)
        for column in (1, 3, 5):
            size_layout.setColumnStretch(column, 1)
        self.size_hint = QLabel()
        self.size_hint.setWordWrap(True)
        self.size_hint.setEnabled(False)  # drawn in the muted text color
        size_layout.addWidget(self.size_hint, 1, 0, 1, 6)
        outer.addWidget(self.size_box)

        style_widget = QWidget()
        style_grid = QGridLayout(style_widget)
        style_grid.setContentsMargins(0, 0, 0, 0)
        style_grid.setHorizontalSpacing(8)

        self.contour_box = QGroupBox()
        contour_form = QFormLayout(self.contour_box)
        self._configure_form(contour_form)
        self._add_float(contour_form, "contour_low", DEFAULT_STYLE.contour_low, 0.0, 1000.0, 2)
        self._add_float(contour_form, "contour_high", DEFAULT_STYLE.contour_high, 0.0, 1000.0, 2)
        self.contour_kernel = self._add_int(
            contour_form, "contour_kernel", DEFAULT_STYLE.contour_kernel, 1, 4
        )
        self._add_float(contour_form, "contour_depth_min", DEFAULT_STYLE.contour_depth_min, 0.0, 1000.0, 2)
        self._add_float(contour_form, "contour_depth_max", DEFAULT_STYLE.contour_depth_max, 0.001, 1000.0, 2)
        style_grid.addWidget(self.contour_box, 0, 0)

        self.boundary_box = QGroupBox()
        boundary_form = QFormLayout(self.boundary_box)
        self._configure_form(boundary_form)
        self._add_float(boundary_form, "subunit_low", DEFAULT_STYLE.subunit_low, 0.0, 1000.0, 2)
        self._add_float(boundary_form, "subunit_high", DEFAULT_STYLE.subunit_high, 0.0, 1000.0, 2)
        self._add_float(boundary_form, "residue_low", DEFAULT_STYLE.residue_low, 0.0, 1000.0, 2)
        self._add_float(boundary_form, "residue_high", DEFAULT_STYLE.residue_high, 0.0, 1000.0, 2)
        self._add_float(boundary_form, "residue_difference", DEFAULT_STYLE.residue_difference, 0.0, 100000.0, 1)
        style_grid.addWidget(self.boundary_box, 0, 1)

        self.shading_box = QGroupBox()
        shading_form = QFormLayout(self.shading_box)
        self._configure_form(shading_form)
        self._add_float(shading_form, "radius_scale", DEFAULT_STYLE.radius_scale, 0.0, 10.0, 3)
        self._add_float(shading_form, "shadow_contribution", DEFAULT_STYLE.shadow_contribution, 0.0, 1.0, 5)
        self._add_float(shading_form, "shadow_cone_angle", DEFAULT_STYLE.shadow_cone_angle, 0.0, 100.0, 3)
        self._add_float(shading_form, "shadow_depth", DEFAULT_STYLE.shadow_depth, 0.0, 100.0, 3)
        self._add_float(shading_form, "shadow_maximum", DEFAULT_STYLE.shadow_maximum, 0.0, 1.0, 3)
        self._add_float(shading_form, "fog_front", DEFAULT_STYLE.fog_front, 0.0, 1.0, 3)
        self._add_float(shading_form, "fog_back", DEFAULT_STYLE.fog_back, 0.0, 1.0, 3)
        self.shadow_checkbox = QCheckBox()
        self.shadow_checkbox.setChecked(DEFAULT_STYLE.shadows)
        self.shadow_checkbox.toggled.connect(self._schedule_render)
        shading_form.addRow(self.shadow_checkbox)
        style_grid.addWidget(self.shading_box, 0, 2)
        for column in range(3):
            style_grid.setColumnStretch(column, 1)

        style_scroll = QScrollArea()
        style_scroll.setWidgetResizable(True)
        style_scroll.setMinimumHeight(180)
        style_scroll.setMaximumHeight(300)
        style_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        style_scroll.setWidget(style_widget)
        outer.addWidget(style_scroll, 1)

        self.status = QLabel()
        outer.addWidget(self.status)

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
    def _configure_form(form):
        form.setContentsMargins(8, 6, 8, 6)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(4)

    def _add_int(self, form, key, value, low, high):
        control = self._new_int(value, low, high)
        label = QLabel()
        self._parameter_labels[key] = label
        form.addRow(label, control)
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
        control.setMaximumWidth(110)
        return control

    def _add_float(self, form, key, value, low, high, decimals):
        control = QDoubleSpinBox()
        control.setRange(low, high)
        control.setDecimals(decimals)
        control.setSingleStep(0.1 if decimals <= 2 else 0.01)
        control.setValue(value)
        control.setMaximumWidth(105)
        label = QLabel()
        self._parameter_labels[key] = label
        form.addRow(label, control)
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
        self.palette_label.setText(self._tr("palette_label"))
        self.palette_button.setText(self._tr("apply_palette"))
        self.palette_button.setToolTip(self._tr("palette_tooltip"))
        self.lock_checkbox.setText(self._tr("lock"))
        self.transparent_checkbox.setText(self._tr("transparent"))
        self.prefer_atom_colors_checkbox.setText(self._tr("prefer_atom_colors"))
        self.prefer_atom_colors_checkbox.setToolTip(self._tr("prefer_atom_colors_tooltip"))
        self.adjust_scene_checkbox.setText(self._tr("adjust_scene"))
        self.adjust_scene_checkbox.setToolTip(self._tr("adjust_scene_tooltip"))
        self.size_box.setTitle(self._tr("size_group"))
        self.preview_size_label.setText(self._tr("preview_size"))
        self.size_hint.setText(self._tr(
            "size_hint", preview_min=MIN_PREVIEW_SIZE, preview_max=MAX_PREVIEW_SIZE,
            export_min=MIN_OUTPUT_SIZE, export_max=MAX_OUTPUT_SIZE,
        ))
        self.output_width_label.setText(self._tr("output_width"))
        self.output_height_label.setText(self._tr("output_height"))
        self.preview_size.setToolTip(self._tr("preview_tooltip"))
        self.output_width.setToolTip(self._tr("width_tooltip"))
        self.output_height.setToolTip(self._tr("height_tooltip"))
        self.contour_box.setTitle(self._tr("contour_group"))
        self.boundary_box.setTitle(self._tr("boundary_group"))
        self.shading_box.setTitle(self._tr("shading_group"))
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
            self.preview.setText(self._tr("preview_empty"))

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
        self.preview.setPixmap(QPixmap())
        self.preview.setText(message)
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
        pixmap = QPixmap.fromImage(qimage)
        self.preview.setPixmap(pixmap.scaled(
            self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

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
