"""Qt tool window for capturing and rendering Illustrate scenes."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from typing import Dict, Optional, Tuple

from chimerax.core.errors import UserError
from chimerax.core.tools import ToolInstance
from chimerax.ui import MainToolWindow
from Qt.QtCore import Qt, QTimer
from Qt.QtGui import QImage, QPixmap
from Qt.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
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

from .render import (
    IllustrationStyle,
    RenderScene,
    RenderedImage,
    ViewSnapshot,
    render,
    save_png,
    scale_style_for_output,
)
from .scene import capture_scene as capture_chimerax_scene
from .palette import apply_chain_palette as color_chains


DEFAULT_STYLE = IllustrationStyle()
DEFAULT_PREVIEW_SIZE = 320
DEFAULT_OUTPUT_WIDTH = 1200
DEFAULT_OUTPUT_HEIGHT = 1200
MAX_OUTPUT_SIZE = 8000

PARAMETER_TOOLTIPS = {
    "contour_low": "轮廓开始出现的敏感度。常用 1–10；越小越容易出现轮廓。",
    "contour_high": "轮廓达到最强的阈值。常用 5–20；越大通常轮廓越少、越淡。",
    "contour_depth_min": "参与轮廓计算的最小深度差。0 会保留更多细节；常用 0–1。",
    "contour_depth_max": "深度差的上限。0–5 常用于原子级轮廓，0–1000 更接近整体轮廓。",
    "subunit_low": "亚基边界开始变黑的阈值。常用 3–20；越小边界越容易出现。",
    "subunit_high": "亚基边界达到最强的阈值。常用 8–20；越大边界越少、越淡。",
    "residue_low": "残基边界开始变黑的阈值。常用 3–20；越小边界越容易出现。",
    "residue_high": "残基边界达到最强的阈值。常用 8–20；越大边界越少、越淡。",
    "residue_difference": "触发残基边界所需的编号差。越大只保留更大的残基间隔。",
    "radius_scale": "原子球半径倍率。1.0 为 ChimeraX 当前半径；更大更粗。",
    "shadow_contribution": "每个遮挡采样对阴影的贡献。越大阴影越明显；常用 0–0.05。",
    "shadow_cone_angle": "阴影锥角。越大阴影范围通常越窄；常用 1–5。",
    "shadow_depth": "产生阴影所需的深度差。越小越容易产生阴影。",
    "shadow_maximum": "阴影亮度下限。越小阴影越黑；范围 0–1。",
    "fog_front": "前景保留原色的比例。1 表示不变；越小越偏向雾色。",
    "fog_back": "背景保留原色的比例。1 表示不变；越小远处越淡。",
}

PARAMETER_HELP_HTML = """
<h2>Illustrate 参数说明</h2>
<p>参数修改只影响当前捕获快照，不会修改 ChimeraX 中的模型、颜色或视角。</p>
<h3>轮廓与边界</h3>
<ul>
<li><b>轮廓低阈值</b>：轮廓开始出现的敏感度。常用 1–10；越小越容易出现轮廓。</li>
<li><b>轮廓高阈值</b>：轮廓达到最强的阈值。常用 5–20；越大通常轮廓越少、越淡。低、高阈值距离越窄，轮廓对比越强，也可能更锯齿。</li>
<li><b>轮廓等级</b>：范围 1–4。1/2 使用像素深度导数，3/4 使用归一化邻域深度差；等级越高越平滑。默认 4，与 Illustrate 参考输入一致。插件会自动校准 3/4 的响应范围，避免只剩外围轮廓。</li>
<li><b>轮廓深度最小差</b>：参与计算的最小深度差。0 会保留更多细节；常用 0–1。</li>
<li><b>轮廓深度最大差</b>：深度差上限。0–5 常用于原子级轮廓；0–1000 更接近只描绘整体分子外轮廓。</li>
<li><b>亚基低/高阈值</b>：亚基边界从出现到变黑的范围。常用 3–20；降低低阈值会增加边界。</li>
<li><b>残基低/高阈值</b>：残基边界从出现到变黑的范围。常用 3–20；降低低阈值会增加边界。</li>
<li><b>残基编号差</b>：触发残基边界所需的编号差。越大只保留更大的残基间隔。</li>
</ul>
<h3>原子、阴影与雾化</h3>
<ul>
<li><b>原子半径倍率</b>：1.0 表示使用 ChimeraX 当前半径；更大更粗，常用 0.8–1.5。</li>
<li><b>启用软阴影</b>：打开或关闭深度阴影。</li>
<li><b>阴影贡献</b>：每个遮挡采样的强度。越大阴影越明显；常用 0–0.05。</li>
<li><b>阴影锥角</b>：阴影扩散范围。越大阴影通常越窄；常用 1–5。</li>
<li><b>阴影深度</b>：产生阴影所需的深度差。越小越容易出现阴影。</li>
<li><b>阴影下限</b>：阴影最低亮度，范围 0–1。越小越黑。</li>
<li><b>前景/背景雾比例</b>：保留原色的比例，范围 0–1。1 表示不雾化；越小越接近背景雾色。</li>
</ul>
<h3>输出尺寸</h3>
<p>预览边长范围为 64–1024；导出宽度和高度范围为 2–8000。原始 Fortran 版本为了固定帧缓冲区把尺寸限制在 3000 像素；本插件使用动态 NumPy 缓冲区，因此提高到 8000，但尺寸越大，内存占用和渲染时间会按像素数增加。导出时会按 1200 像素参考比例同步缩放轮廓、边界和阴影的像素邻域，因此只改变输出尺寸不会明显改变整体风格。</p>
"""


class IllustrateTool(ToolInstance):
    SESSION_ENDURING = False
    SESSION_SAVE = False
    help = "help:user/tools/illustrate.html"

    def __init__(self, session, tool_name):
        super().__init__(session, tool_name)
        self._scene: Optional[RenderScene] = None
        self._view: Optional[ViewSnapshot] = None
        self._style_state = IllustrationStyle()
        self._capture_width = DEFAULT_PREVIEW_SIZE
        self._capture_height = DEFAULT_PREVIEW_SIZE
        self._generation = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="illustrate")
        self._preview_future: Optional[Future] = None
        self._locked = False
        self._float_controls: Dict[str, QDoubleSpinBox] = {}

        self.tool_window = MainToolWindow(self)
        self._build_ui()
        self.tool_window.manage(placement="side")

    def _build_ui(self):
        area = self.tool_window.ui_area
        outer = QVBoxLayout(area)

        actions = QHBoxLayout()
        self.capture_button = QPushButton("捕获当前场景")
        self.capture_button.clicked.connect(self.capture_scene)
        actions.addWidget(self.capture_button)
        self.palette_button = QPushButton("一键链配色")
        self.palette_button.clicked.connect(self.apply_chain_palette)
        self.palette_button.setToolTip(
            "按链自动配色，并设置白色背景、柔和光照和 ChimeraX 轮廓线。"
        )
        actions.addWidget(self.palette_button)
        self.save_button = QPushButton("导出 PNG")
        self.save_button.clicked.connect(self._choose_save_path)
        self.save_button.setEnabled(False)
        actions.addWidget(self.save_button)
        self.reset_button = QPushButton("恢复默认参数")
        self.reset_button.clicked.connect(self.reset_defaults)
        actions.addWidget(self.reset_button)
        self.help_button = QPushButton("参数说明")
        self.help_button.clicked.connect(self.show_parameter_help)
        actions.addWidget(self.help_button)
        outer.addLayout(actions)

        self.lock_checkbox = QCheckBox("锁定快照")
        self.lock_checkbox.toggled.connect(self._set_locked)
        outer.addWidget(self.lock_checkbox)

        self.transparent_checkbox = QCheckBox("透明背景")
        self.transparent_checkbox.setChecked(True)
        outer.addWidget(self.transparent_checkbox)

        self.preview = QLabel("请先捕获一个 ChimeraX 场景")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(280, 280)
        self.preview.setMaximumHeight(320)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.preview.setStyleSheet("QLabel { background: #dddddd; border: 1px solid #999999; }")
        outer.addWidget(self.preview)

        size_box = QGroupBox("输出尺寸")
        size_layout = QHBoxLayout(size_box)
        size_layout.setContentsMargins(10, 6, 10, 6)
        size_layout.addWidget(QLabel("预览边长"))
        self.preview_size = self._new_int(DEFAULT_PREVIEW_SIZE, 64, 1024)
        self.preview_size.setToolTip("预览边长，范围 64–1024。数值越大细节越多，但预览更慢。")
        size_layout.addWidget(self.preview_size)
        size_layout.addSpacing(16)
        size_layout.addWidget(QLabel("导出宽度"))
        self.output_width = self._new_int(DEFAULT_OUTPUT_WIDTH, 2, MAX_OUTPUT_SIZE)
        self.output_width.setToolTip("导出 PNG 的宽度，范围 2–8000。尺寸越大，渲染越慢、占用内存越多。")
        size_layout.addWidget(self.output_width)
        size_layout.addSpacing(16)
        size_layout.addWidget(QLabel("导出高度"))
        self.output_height = self._new_int(DEFAULT_OUTPUT_HEIGHT, 2, MAX_OUTPUT_SIZE)
        self.output_height.setToolTip("导出 PNG 的高度，范围 2–8000。尺寸越大，渲染越慢、占用内存越多。")
        size_layout.addWidget(self.output_height)
        size_layout.addStretch(1)
        outer.addWidget(size_box)

        style_box = QGroupBox("Illustrate 参数")
        style_form = QFormLayout(style_box)
        self._add_float(style_form, "contour_low", "轮廓低阈值", DEFAULT_STYLE.contour_low, 0.0, 1000.0, 2)
        self._add_float(style_form, "contour_high", "轮廓高阈值", DEFAULT_STYLE.contour_high, 0.0, 1000.0, 2)
        self.contour_kernel = self._add_int(style_form, "轮廓等级", DEFAULT_STYLE.contour_kernel, 1, 4)
        self.contour_kernel.setToolTip("轮廓等级，范围 1–4；1/2 较锐，3 较平滑但保留原子级边界，4 最平滑、偏向整体轮廓。默认 4，与 Illustrate 参考输入一致。插件会自动校准不同等级的响应范围。")
        self._add_float(style_form, "contour_depth_min", "轮廓深度最小差", DEFAULT_STYLE.contour_depth_min, 0.0, 1000.0, 2)
        self._add_float(style_form, "contour_depth_max", "轮廓深度最大差", DEFAULT_STYLE.contour_depth_max, 0.001, 1000.0, 2)
        self._add_float(style_form, "subunit_low", "亚基低阈值", DEFAULT_STYLE.subunit_low, 0.0, 1000.0, 2)
        self._add_float(style_form, "subunit_high", "亚基高阈值", DEFAULT_STYLE.subunit_high, 0.0, 1000.0, 2)
        self._add_float(style_form, "residue_low", "残基低阈值", DEFAULT_STYLE.residue_low, 0.0, 1000.0, 2)
        self._add_float(style_form, "residue_high", "残基高阈值", DEFAULT_STYLE.residue_high, 0.0, 1000.0, 2)
        self._add_float(style_form, "residue_difference", "残基编号差", DEFAULT_STYLE.residue_difference, 0.0, 100000.0, 1)
        self._add_float(style_form, "radius_scale", "原子半径倍率", DEFAULT_STYLE.radius_scale, 0.0, 10.0, 3)
        self._add_float(style_form, "shadow_contribution", "阴影贡献", DEFAULT_STYLE.shadow_contribution, 0.0, 1.0, 5)
        self._add_float(style_form, "shadow_cone_angle", "阴影锥角", DEFAULT_STYLE.shadow_cone_angle, 0.0, 100.0, 3)
        self._add_float(style_form, "shadow_depth", "阴影深度", DEFAULT_STYLE.shadow_depth, 0.0, 100.0, 3)
        self._add_float(style_form, "shadow_maximum", "阴影下限", DEFAULT_STYLE.shadow_maximum, 0.0, 1.0, 3)
        self._add_float(style_form, "fog_front", "前景雾比例", DEFAULT_STYLE.fog_front, 0.0, 1.0, 3)
        self._add_float(style_form, "fog_back", "背景雾比例", DEFAULT_STYLE.fog_back, 0.0, 1.0, 3)
        self.shadow_checkbox = QCheckBox("启用软阴影")
        self.shadow_checkbox.setChecked(DEFAULT_STYLE.shadows)
        self.shadow_checkbox.toggled.connect(self._schedule_render)
        style_form.addRow(self.shadow_checkbox)

        style_scroll = QScrollArea()
        style_scroll.setWidgetResizable(True)
        style_scroll.setMinimumHeight(160)
        style_scroll.setMaximumHeight(260)
        style_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        style_scroll.setWidget(style_box)
        outer.addWidget(style_scroll, 1)

        self.status = QLabel("等待捕获场景")
        outer.addWidget(self.status)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(160)
        self._timer.timeout.connect(self._start_preview_render)

        for control in self._float_controls.values():
            control.valueChanged.connect(self._schedule_render)
        self.contour_kernel.valueChanged.connect(self._schedule_render)
        self.preview_size.valueChanged.connect(self._schedule_render)

    @staticmethod
    def _add_int(form, label, value, low, high):
        control = IllustrateTool._new_int(value, low, high)
        form.addRow(label, control)
        return control

    @staticmethod
    def _new_int(value, low, high):
        control = QSpinBox()
        control.setRange(low, high)
        control.setValue(value)
        control.setMaximumWidth(110)
        return control

    def _add_float(self, form, key, label, value, low, high, decimals):
        control = QDoubleSpinBox()
        control.setRange(low, high)
        control.setDecimals(decimals)
        control.setSingleStep(0.1 if decimals <= 2 else 0.01)
        control.setValue(value)
        control.setToolTip(PARAMETER_TOOLTIPS.get(key, ""))
        form.addRow(label, control)
        self._float_controls[key] = control
        return control

    def _set_locked(self, locked):
        self._locked = bool(locked)
        self.capture_button.setEnabled(not self._locked)
        self._set_status("快照已锁定" if self._locked else "快照已解锁")

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
        self._set_status("已恢复默认参数")
        self._schedule_render()

    def show_parameter_help(self):
        dialog = QDialog(self.tool_window.ui_area)
        dialog.setWindowTitle("Illustrate 参数说明")
        dialog.resize(620, 680)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(PARAMETER_HELP_HTML)
        layout.addWidget(browser)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()

    def capture_scene(self):
        if self._locked:
            return
        try:
            scene, view, style, warning = capture_chimerax_scene(
                self.session, self.preview_size.value(), self.preview_size.value()
            )
        except Exception as error:
            self._invalidate_snapshot("捕获失败: %s" % error)
            return
        if not scene.atoms:
            self._invalidate_snapshot(
                "没有捕获到可见原子、cartoon 或 molecular surface"
            )
            return
        self._scene = scene
        self._view = view
        self._style_state = style
        self._capture_width = self.preview_size.value()
        self._capture_height = self.preview_size.value()
        self.save_button.setEnabled(True)
        message = "已捕获 %d 个原子（来自 atom/cartoon/surface）" % len(scene.atoms)
        if warning:
            message += "；" + warning
        self._set_status(message)
        self._schedule_render()

    def apply_chain_palette(self):
        try:
            assignments = color_chains(self.session)
        except Exception as error:
            self._set_status("链配色失败: %s" % error)
            return
        if not assignments:
            self._set_status("没有可配色的原子模型")
            return
        self._set_status(
            "已为 %d 条链配色；请点击“捕获当前场景”更新预览"
            % len(assignments)
        )

    def _invalidate_snapshot(self, message):
        self._generation += 1
        self._scene = None
        self._view = None
        self.save_button.setEnabled(False)
        self.preview.setPixmap(QPixmap())
        self.preview.setText(message)
        self._set_status(message)

    def clear_scene(self):
        self._invalidate_snapshot("请先捕获一个 ChimeraX 场景")
        self._set_status("已清除快照")

    def _schedule_render(self, *args):
        if self._scene is None or self._view is None:
            return
        self._timer.start()

    def _view_for_size(self, width):
        scale = float(width) / float(max(1, self._capture_width))
        return replace(self._view, pixels_per_angstrom=self._view.pixels_per_angstrom * scale)

    def _style_for_size(self, width):
        return scale_style_for_output(self._current_style(), width, self._capture_width)

    def _start_preview_render(self):
        if self._scene is None or self._view is None:
            return
        self._generation += 1
        generation = self._generation
        scene = self._scene
        width = self.preview_size.value()
        height = width
        view = self._view_for_size(width)
        style = self._style_for_size(width)
        self._preview_future = self._executor.submit(render, scene, view, style, width, height)
        self._preview_future.add_done_callback(
            lambda future: self._deliver_render(generation, future, None)
        )

    def _deliver_render(self, generation, future, save_args):
        try:
            image = future.result()
            error = None
        except Exception as caught:
            image = None
            error = caught
        try:
            self.session.ui.thread_safe(self._finish_render, generation, image, error, save_args)
        except Exception:
            # This fallback is useful for lightweight test doubles; ChimeraX's
            # real UI always provides thread_safe().
            self._finish_render(generation, image, error, save_args)

    def _finish_render(self, generation, image, error, save_args=None):
        if generation != self._generation:
            return
        if error is not None:
            self._set_status("渲染失败: %s" % error)
            return
        if save_args is not None:
            path, transparent = save_args
            try:
                save_png(path, image, transparent=transparent)
            except Exception as caught:
                self._set_status("保存失败: %s" % caught)
                return
            self._set_status("已保存 %s" % path)
            return
        self._show_image(image)
        self._set_status("预览已更新")

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
        if self._scene is None:
            raise UserError("Please capture a ChimeraX scene before exporting")
        path, _selected_filter = QFileDialog.getSaveFileName(
            self.tool_window.ui_area, "导出 Illustrate PNG", "illustrate.png", "PNG (*.png)"
        )
        if path:
            self.save_image(path, transparent=self.transparent_checkbox.isChecked())

    def save_image(self, path, transparent=True, width=None, height=None):
        if self._scene is None or self._view is None or not self._scene.atoms:
            raise UserError(
                "没有可导出的场景；请显示 atom、cartoon 或 surface 后重新捕获"
            )
        width = int(width or self.output_width.value())
        height = int(height or self.output_height.value())
        if width < 2 or height < 2:
            raise UserError("PNG dimensions must be at least 2 pixels")
        if width > MAX_OUTPUT_SIZE or height > MAX_OUTPUT_SIZE:
            raise UserError("PNG dimensions must not exceed %d pixels" % MAX_OUTPUT_SIZE)
        self._generation += 1
        generation = self._generation
        scene = self._scene
        view = self._view_for_size(width)
        style = self._style_for_size(width)
        future = self._executor.submit(render, scene, view, style, width, height)
        future.add_done_callback(lambda f: self._deliver_render(
            generation, f, (path, bool(transparent))
        ))
        self._set_status("正在渲染 %dx%d PNG" % (width, height))

    def delete(self):
        self._generation += 1
        try:
            self._timer.stop()
        except Exception:
            pass
        self._executor.shutdown(wait=False)
        super().delete()
