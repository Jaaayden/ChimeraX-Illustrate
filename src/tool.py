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
DEFAULT_PREVIEW_SIZE = 512
DEFAULT_OUTPUT_WIDTH = 1200
DEFAULT_OUTPUT_HEIGHT = 1200
MAX_OUTPUT_SIZE = 8000

PARAMETER_TOOLTIPS_ZH = {
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

PARAMETER_HELP_HTML_ZH = """
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

UI_TEXT = {
    "en": {
        "capture": "Capture Current Scene",
        "save": "Export PNG",
        "reset": "Reset Defaults",
        "help": "Parameter Help",
        "language": "中文",
        "palette_label": "Color preset",
        "apply_palette": "Apply Colors",
        "lock": "Lock Snapshot",
        "transparent": "Transparent Background",
        "preview_empty": "Capture a ChimeraX scene to begin",
        "size_group": "Output Size",
        "preview_size": "Preview",
        "output_width": "Width",
        "output_height": "Height",
        "contour_group": "Contours",
        "boundary_group": "Boundaries",
        "shading_group": "Atoms, Shadows and Fog",
        "shadow_enabled": "Enable Soft Shadows",
        "status_waiting": "Waiting for scene capture",
        "status_locked": "Snapshot locked",
        "status_unlocked": "Snapshot unlocked",
        "status_reset": "Default parameters restored",
        "status_language": "Interface language: English",
        "capture_failed": "Capture failed: {error}",
        "capture_empty": "No visible atoms, cartoons, or molecular surfaces were captured",
        "captured": "Captured {count} atoms from atom/cartoon/surface",
        "perspective_warning": "Perspective camera detected; the Illustrate preview is orthographic",
        "palette_failed": "Color preset failed: {error}",
        "palette_empty": "No atomic model is available for coloring",
        "palette_done": "Applied “{preset}” to {count} components; capture the scene again",
        "snapshot_empty": "Capture a ChimeraX scene to begin",
        "snapshot_cleared": "Snapshot cleared",
        "render_failed": "Render failed: {error}",
        "save_failed": "Save failed: {error}",
        "saved": "Saved {path}",
        "preview_updated": "Preview updated",
        "save_dialog": "Export Illustrate PNG",
        "rendering": "Rendering {width}×{height} PNG in the background",
        "help_title": "Illustrate Parameter Help",
        "close": "Close",
        "need_capture": "Capture a ChimeraX scene before exporting",
        "invalid_scene": "No exportable scene; show atoms, cartoons, or surfaces and capture again",
        "minimum_size": "PNG dimensions must be at least 2 pixels",
        "maximum_size": "PNG dimensions must not exceed {maximum} pixels",
        "palette_tooltip": "Choose an illustration-oriented preset, apply it to open atomic models, then capture the scene again.",
        "preview_tooltip": "Preview edge length, 64–1024. The 512-pixel default balances clarity and interactive speed.",
        "width_tooltip": "PNG width, 2–8000. Larger images require more rendering time and memory.",
        "height_tooltip": "PNG height, 2–8000. Larger images require more rendering time and memory.",
    },
    "zh": {
        "capture": "捕获当前场景",
        "save": "导出 PNG",
        "reset": "恢复默认参数",
        "help": "参数说明",
        "language": "English",
        "palette_label": "配色方案",
        "apply_palette": "应用配色",
        "lock": "锁定快照",
        "transparent": "透明背景",
        "preview_empty": "请先捕获一个 ChimeraX 场景",
        "size_group": "输出尺寸",
        "preview_size": "预览边长",
        "output_width": "导出宽度",
        "output_height": "导出高度",
        "contour_group": "轮廓",
        "boundary_group": "亚基与残基边界",
        "shading_group": "原子、阴影与雾化",
        "shadow_enabled": "启用软阴影",
        "status_waiting": "等待捕获场景",
        "status_locked": "快照已锁定",
        "status_unlocked": "快照已解锁",
        "status_reset": "已恢复默认参数",
        "status_language": "界面语言：中文",
        "capture_failed": "捕获失败：{error}",
        "capture_empty": "没有捕获到可见原子、cartoon 或 molecular surface",
        "captured": "已捕获 {count} 个原子（来自 atom/cartoon/surface）",
        "perspective_warning": "当前相机为透视投影；Illustrate 预览使用正交投影",
        "palette_failed": "配色失败：{error}",
        "palette_empty": "没有可配色的原子模型",
        "palette_done": "已将“{preset}”应用到 {count} 个组分；请重新捕获场景",
        "snapshot_empty": "请先捕获一个 ChimeraX 场景",
        "snapshot_cleared": "已清除快照",
        "render_failed": "渲染失败：{error}",
        "save_failed": "保存失败：{error}",
        "saved": "已保存 {path}",
        "preview_updated": "预览已更新",
        "save_dialog": "导出 Illustrate PNG",
        "rendering": "正在后台渲染 {width}×{height} PNG",
        "help_title": "Illustrate 参数说明",
        "close": "关闭",
        "need_capture": "导出前请先捕获 ChimeraX 场景",
        "invalid_scene": "没有可导出的场景；请显示 atom、cartoon 或 surface 后重新捕获",
        "minimum_size": "PNG 尺寸不能小于 2 像素",
        "maximum_size": "PNG 尺寸不能超过 {maximum} 像素",
        "palette_tooltip": "选择适合插图的配色方案，应用到当前原子模型，然后重新捕获场景。",
        "preview_tooltip": "预览边长范围 64–1024。默认 512，在清晰度和交互速度之间取得平衡。",
        "width_tooltip": "导出 PNG 的宽度，范围 2–8000。尺寸越大，渲染越慢、占用内存越多。",
        "height_tooltip": "导出 PNG 的高度，范围 2–8000。尺寸越大，渲染越慢、占用内存越多。",
    },
}

PARAMETER_LABELS = {
    "en": {
        "contour_low": "Low threshold",
        "contour_high": "High threshold",
        "contour_kernel": "Contour level",
        "contour_depth_min": "Minimum depth",
        "contour_depth_max": "Maximum depth",
        "subunit_low": "Subunit low",
        "subunit_high": "Subunit high",
        "residue_low": "Residue low",
        "residue_high": "Residue high",
        "residue_difference": "Residue difference",
        "radius_scale": "Atom radius scale",
        "shadow_contribution": "Shadow contribution",
        "shadow_cone_angle": "Shadow cone angle",
        "shadow_depth": "Shadow depth",
        "shadow_maximum": "Shadow floor",
        "fog_front": "Front fog fraction",
        "fog_back": "Back fog fraction",
    },
    "zh": {
        "contour_low": "轮廓低阈值",
        "contour_high": "轮廓高阈值",
        "contour_kernel": "轮廓等级",
        "contour_depth_min": "轮廓深度最小差",
        "contour_depth_max": "轮廓深度最大差",
        "subunit_low": "亚基低阈值",
        "subunit_high": "亚基高阈值",
        "residue_low": "残基低阈值",
        "residue_high": "残基高阈值",
        "residue_difference": "残基编号差",
        "radius_scale": "原子半径倍率",
        "shadow_contribution": "阴影贡献",
        "shadow_cone_angle": "阴影锥角",
        "shadow_depth": "阴影深度",
        "shadow_maximum": "阴影下限",
        "fog_front": "前景雾比例",
        "fog_back": "背景雾比例",
    },
}

PARAMETER_TOOLTIPS_EN = {
    "contour_low": "Contour onset. Typical 1–10; lower values reveal more outlines.",
    "contour_high": "Full contour strength. Typical 5–20; higher values make contours lighter or less frequent.",
    "contour_kernel": "Contour level 1–4. Level 4 is the smooth reference-style default.",
    "contour_depth_min": "Smallest depth difference used for contours. Typical 0–1.",
    "contour_depth_max": "Depth-difference cap. Typical 0–5 for atom-level contours.",
    "subunit_low": "Subunit-boundary onset. Typical 3–20; lower values reveal more boundaries.",
    "subunit_high": "Full subunit-boundary strength. Typical 8–20.",
    "residue_low": "Residue-boundary onset. Typical 3–20.",
    "residue_high": "Full residue-boundary strength. Typical 8–20.",
    "residue_difference": "Residue-number gap needed to trigger a boundary.",
    "radius_scale": "Atomic sphere radius multiplier. 1.0 uses the captured ChimeraX radius.",
    "shadow_contribution": "Contribution of each occluding shadow sample. Typical 0–0.05.",
    "shadow_cone_angle": "Shadow cone spread. Larger values usually produce narrower shadows.",
    "shadow_depth": "Minimum depth difference needed to cast a shadow.",
    "shadow_maximum": "Minimum brightness under shadow, 0–1. Lower is darker.",
    "fog_front": "Front color fraction, 0–1. Lower values move toward the fog color.",
    "fog_back": "Back color fraction, 0–1. Lower values fade distant atoms.",
}

PARAMETER_HELP_HTML_EN = """
<h2>Illustrate Parameter Guide</h2>
<p>Parameter changes affect only the captured snapshot and do not modify the
original ChimeraX model, colors, or camera.</p>
<h3>Contours and boundaries</h3>
<ul>
<li><b>Low/high threshold</b>: control when contours begin and reach full
strength. Lower low-threshold values reveal more lines; larger high-threshold
values usually make them lighter.</li>
<li><b>Contour level</b>: 1–4. Levels 1/2 are sharper; levels 3/4 use
normalized neighborhood depth differences. Level 4 is the reference default.</li>
<li><b>Minimum/maximum depth</b>: depth-difference interval used by contour
detection. A practical atom-level range is 0–5.</li>
<li><b>Subunit and residue thresholds</b>: control internal group boundaries.
The residue difference sets the sequence-number gap needed to trigger one.</li>
</ul>
<h3>Atoms, shadows, and fog</h3>
<ul>
<li><b>Atom radius scale</b>: 1.0 uses the captured ChimeraX radius.</li>
<li><b>Shadow contribution, cone angle, depth, and floor</b>: control soft
occlusion strength, spread, depth sensitivity, and minimum brightness.</li>
<li><b>Front/back fog fraction</b>: 1 retains the original color; lower values
blend toward the fog color.</li>
</ul>
<h3>Output</h3>
<p>The preview range is 64–1024 pixels; 512 is the default balance of clarity
and speed. PNG dimensions range from 2–8000 pixels. Pixel-based neighborhoods
are scaled from the 1200-pixel reference, so changing output size does not
substantially change the illustration style.</p>
"""

PALETTE_LABELS = {
    "en": {
        "classic": "Classic Chains",
        "cool_warm": "Cool / Warm Complex",
        "ribosome": "Nucleic Base Contrast",
        "functional": "MotM Spectrum",
        "monochrome": "Monochrome Blues",
    },
    "zh": {
        "classic": "经典链配色",
        "cool_warm": "冷暖复合物",
        "ribosome": "核酸碱基对比",
        "functional": "月度分子光谱",
        "monochrome": "单色蓝系列",
    },
}


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
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="illustrate")
        self._preview_future: Optional[Future] = None
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
        for preset in PALETTE_LABELS["en"]:
            self.palette_combo.addItem("", preset)
        palette_row.addWidget(self.palette_combo, 1)
        self.palette_button = QPushButton()
        self.palette_button.clicked.connect(self.apply_chain_palette)
        palette_row.addWidget(self.palette_button)
        outer.addLayout(palette_row)

        options = QHBoxLayout()
        self.lock_checkbox = QCheckBox()
        self.lock_checkbox.toggled.connect(self._set_locked)
        options.addWidget(self.lock_checkbox)
        self.transparent_checkbox = QCheckBox()
        self.transparent_checkbox.setChecked(True)
        options.addWidget(self.transparent_checkbox)
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
        self.preview_size = self._new_int(DEFAULT_PREVIEW_SIZE, 64, 1024)
        size_layout.addWidget(self.preview_size, 0, 1)
        self.output_width_label = QLabel()
        size_layout.addWidget(self.output_width_label, 0, 2)
        self.output_width = self._new_int(DEFAULT_OUTPUT_WIDTH, 2, MAX_OUTPUT_SIZE)
        size_layout.addWidget(self.output_width, 0, 3)
        self.output_height_label = QLabel()
        size_layout.addWidget(self.output_height_label, 0, 4)
        self.output_height = self._new_int(DEFAULT_OUTPUT_HEIGHT, 2, MAX_OUTPUT_SIZE)
        size_layout.addWidget(self.output_height, 0, 5)
        for column in (1, 3, 5):
            size_layout.setColumnStretch(column, 1)
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
        return UI_TEXT[self._language][key].format(**values)

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
        self.size_box.setTitle(self._tr("size_group"))
        self.preview_size_label.setText(self._tr("preview_size"))
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
            PARAMETER_HELP_HTML_EN
            if self._language == "en"
            else PARAMETER_HELP_HTML_ZH
        )
        layout.addWidget(browser)
        close_button = QPushButton(self._tr("close"))
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
            self._invalidate_snapshot(
                self._tr("capture_failed", error=error)
            )
            return
        if not scene.atoms:
            self._invalidate_snapshot(self._tr("capture_empty"))
            return
        self._scene = scene
        self._view = view
        self._style_state = style
        self._capture_width = self.preview_size.value()
        self._capture_height = self.preview_size.value()
        self.save_button.setEnabled(True)
        message = self._tr("captured", count=len(scene.atoms))
        if warning:
            message += " — " + self._tr("perspective_warning")
        self._set_status(message)
        self._schedule_render()

    def apply_chain_palette(self):
        preset = self.palette_combo.currentData()
        try:
            assignments = color_chains(self.session, preset=preset)
        except Exception as error:
            self._set_status(self._tr("palette_failed", error=error))
            return
        if not assignments:
            self._set_status(self._tr("palette_empty"))
            return
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
        self.save_button.setEnabled(False)
        self.preview.setPixmap(QPixmap())
        self.preview.setText(message)
        self._set_status(message)

    def clear_scene(self):
        self._invalidate_snapshot(self._tr("snapshot_empty"))
        self._set_status(self._tr("snapshot_cleared"))

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
        if self._preview_future is not None and not self._preview_future.done():
            # A queued stale preview can be cancelled; a currently running
            # NumPy render finishes normally and its generation is discarded.
            # This keeps rapid parameter edits from building a long work queue.
            self._preview_future.cancel()
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
            self._set_status(self._tr("render_failed", error=error))
            return
        if save_args is not None:
            path, transparent = save_args
            try:
                save_png(path, image, transparent=transparent)
            except Exception as caught:
                self._set_status(self._tr("save_failed", error=caught))
                return
            self._set_status(self._tr("saved", path=path))
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
        if self._scene is None:
            raise UserError(self._tr("need_capture"))
        path, _selected_filter = QFileDialog.getSaveFileName(
            self.tool_window.ui_area,
            self._tr("save_dialog"),
            "illustrate.png",
            "PNG (*.png)",
        )
        if path:
            self.save_image(path, transparent=self.transparent_checkbox.isChecked())

    @staticmethod
    def _render_and_save(scene, view, style, width, height, path, transparent):
        image = render(scene, view, style, width, height)
        save_png(path, image, transparent=transparent)
        return path

    def _deliver_save(self, generation, future):
        try:
            path = future.result()
            error = None
        except Exception as caught:
            path = None
            error = caught
        try:
            self.session.ui.thread_safe(
                self._finish_save, generation, path, error
            )
        except Exception:
            self._finish_save(generation, path, error)

    def _finish_save(self, generation, path, error):
        if generation != self._generation:
            return
        if error is not None:
            self._set_status(self._tr("save_failed", error=error))
            return
        self._set_status(self._tr("saved", path=path))

    def save_image(self, path, transparent=True, width=None, height=None):
        if self._scene is None or self._view is None or not self._scene.atoms:
            raise UserError(self._tr("invalid_scene"))
        width = int(width or self.output_width.value())
        height = int(height or self.output_height.value())
        if width < 2 or height < 2:
            raise UserError(self._tr("minimum_size"))
        if width > MAX_OUTPUT_SIZE or height > MAX_OUTPUT_SIZE:
            raise UserError(
                self._tr("maximum_size", maximum=MAX_OUTPUT_SIZE)
            )
        self._generation += 1
        generation = self._generation
        scene = self._scene
        view = self._view_for_size(width)
        style = self._style_for_size(width)
        self._timer.stop()
        if self._preview_future is not None and not self._preview_future.done():
            self._preview_future.cancel()
        future = self._executor.submit(
            self._render_and_save,
            scene, view, style, width, height, path, bool(transparent),
        )
        future.add_done_callback(
            lambda completed: self._deliver_save(generation, completed)
        )
        self._set_status(
            self._tr("rendering", width=width, height=height)
        )

    def delete(self):
        self._generation += 1
        try:
            self._timer.stop()
        except Exception:
            pass
        self._executor.shutdown(wait=False)
        super().delete()
