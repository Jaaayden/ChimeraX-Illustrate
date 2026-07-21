# Illustrate for ChimeraX

中文说明 | [English](README.en.md)

## 项目简介

Illustrate for ChimeraX 是一个 ChimeraX bundle，将当前 ChimeraX 场景转换为具有 Illustrate 风格的非真实感分子插图。

它不要求用户手动编写或反复修改 `.inp` 文件。用户在 ChimeraX 中调整显示内容和视角后，捕获当前场景，再通过插件参数实时调整轮廓、边界、阴影和雾化效果，最后导出 PNG。

本仓库只包含插件软件、文档、测试和许可文件，不包含任何结构数据或结构结果。

## 主要功能

- 捕获当前可见的原子球体、颜色、半径和分组信息。
- 捕获当前 ChimeraX 相机和视角；渲染器使用 Illustrate 风格的正交投影模型。
- 低分辨率预览和参数修改后的防抖更新。
- 轮廓、亚基边界、残基边界、软阴影和雾化控制。
- 透明或不透明 PNG 导出。
- 支持 2–8000 像素的导出宽度和高度；大尺寸导出使用分块处理。
- 提供参数说明、实用范围和默认参数恢复功能。

首版只支持原子球体。Cartoon、surface 和其他复杂模型暂不转换为原子球体。

## 安装

### ChimeraX 图形界面

1. 下载或构建本项目的 `.whl` 文件。
2. 在 ChimeraX 中打开 `Tools → More Tools... → Install from file`。
3. 选择 wheel 文件并重启 ChimeraX。
4. 在命令行输入 `illustrate` 打开工具窗口。

### 从源码安装

在 ChimeraX 命令行执行：

```text
devel install /absolute/path/to/this/repository editable true
```

构建 wheel：

```text
devel build /absolute/path/to/this/repository
```

不要求安装 Fortran 或 gfortran。NumPy、Qt 和 ChimeraX API 由 ChimeraX 提供。

## 使用

1. 在 ChimeraX 中打开结构并显示需要绘制的原子球体。
2. 调整 ChimeraX 中的颜色、显示状态和视角。
3. 执行 `illustrate`，点击“捕获当前场景”。
4. 在工具窗口中调整参数并查看预览。
5. 设置输出尺寸并导出 PNG。

改变 ChimeraX 视角后，需要再次捕获场景。参数修改会作用于已捕获的快照，不会修改 ChimeraX 原始模型。

## 快速分配链颜色

仓库还提供了一个可独立运行的 ChimeraX 脚本 [`chimerax-chain-palette.py`](chimerax-chain-palette.py)，用于按链自动分配一组适合 Illustrate 风格的颜色。它会对当前打开的原子模型依次处理各条链，并对常见元素使用同一链颜色的明暗变化；同时可设置白色背景、柔和光照、轮廓线并隐藏氢原子。

在 ChimeraX 中打开结构后运行：

```text
runscript /absolute/path/to/chimerax-chain-palette.py
```

脚本只修改 ChimeraX 的显示颜色和相关显示设置，不修改坐标，也不会覆盖输入结构文件。完成颜色分配后，可以运行 `illustrate` 并点击“捕获当前场景”，将当前颜色带入 Illustrate 渲染。该脚本不需要手动编辑 `.inp` 文件，也可以不安装 Illustrate bundle 单独使用。

## 命令

```text
illustrate
illustrate capture
illustrate save /absolute/path/to/illustrate.png transparent true
illustrate reset
```

## 开发与测试

渲染核心是纯 Python，并提供 NumPy 加速路径和标准库后备路径。运行测试：

```text
python3 -m unittest discover -s tests -v
```

当前 bundle 面向 ChimeraX 1.10 及兼容的稳定版 API。超大图像会增加内存占用和渲染时间。

## 许可

本项目使用 Apache License 2.0。非真实感渲染风格和算法参考来自 [ccsb-scripps/Illustrate](https://github.com/ccsb-scripps/Illustrate)。
