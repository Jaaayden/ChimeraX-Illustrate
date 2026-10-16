"""User-visible strings for the Illustrate tool (English and Chinese)."""

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
        "prefer_atom_colors": "Keep Atom Colors",
        "prefer_atom_colors_tooltip": "Use each atom's own color for atoms shown only as cartoon or surface. Enabled automatically by the Nucleic Base Contrast preset.",
        "adjust_scene": "Also adjust scene",
        "adjust_scene_tooltip": "Also hide hydrogens, set a white background, soft lighting, and ChimeraX silhouettes when applying a color preset.",
        "capture_locked": "Snapshot is locked; unlock it to capture again",
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
        "prefer_atom_colors": "保留原子颜色",
        "prefer_atom_colors_tooltip": "对仅以 cartoon 或 surface 显示的原子使用其自身颜色。“核酸碱基对比”配色会自动启用。",
        "adjust_scene": "同时调整场景",
        "adjust_scene_tooltip": "应用配色时同时隐藏氢原子，并设置白色背景、柔和光照和 ChimeraX 轮廓线。",
        "capture_locked": "快照已锁定；请先解锁再捕获",
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
