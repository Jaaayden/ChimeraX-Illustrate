# Illustrate for ChimeraX

中文说明 | [English](README.en.md)

## 项目简介

Illustrate for ChimeraX 是一个 ChimeraX bundle，将当前 ChimeraX 场景转换为具有 Illustrate 风格的非真实感分子插图。

它不要求用户手动编写或反复修改 `.inp` 文件。用户在 ChimeraX 中调整显示内容和视角后，捕获当前场景，再通过插件参数实时调整轮廓、边界、阴影和雾化效果，最后导出 PNG。

本仓库只包含插件软件、文档、测试和许可文件，不包含任何结构数据或结构结果。

## 主要功能

- 捕获当前显示为 atom、cartoon 或 molecular surface 的分子内容，并读取对应颜色、原子半径和分组信息。
- 内置五套插图配色方案，可直接为当前原子模型按链着色，并可区分核酸骨架与碱基。
- 捕获当前 ChimeraX 相机和视角；渲染器使用 Illustrate 风格的正交投影模型。
- 默认 512 像素预览和参数修改后的防抖更新。
- 轮廓、亚基边界、残基边界、软阴影和雾化控制。
- 默认英文界面，可在工具窗口中一键切换为中文。
- 参数按轮廓、边界、原子/阴影/雾化分为三列，减少滚动并提高空间利用率。
- 透明或不透明 PNG 导出。
- 支持 2–8000 像素的导出宽度和高度；大尺寸导出使用分块处理。
- 使用栅格/阴影缓存、有效区域裁剪、NumPy 向量化和多核阴影计算加速预览及高分辨率导出；PNG 在后台分块合成、压缩和写盘，不阻塞 ChimeraX 界面。
- 提供参数说明、实用范围和默认参数恢复功能。

渲染结果仍由原子球体组成。Cartoon 和 molecular surface 的几何网格不会被直接栅格化；插件会读取当前可见 cartoon 残基或 surface patch 所关联的原子，再转换为 Illustrate 风格球体。隐藏的整个模型不会被捕获。

## 安装

### 推荐：从源码安装（macOS / Linux）

首先打开系统终端，将仓库克隆到用户主目录：

```bash
cd ~
git clone https://github.com/Jaaayden/ChimeraX-Illustrate.git
```

然后打开 ChimeraX，在 ChimeraX 命令行中执行：

```text
devel install ~/ChimeraX-Illustrate
```

安装完成后重启 ChimeraX，再输入 `illustrate` 打开工具窗口。

本项目使用 `bundle_info.xml` 构建格式。请勿添加 `editable true`；在 ChimeraX 1.12 中，这可能导致工具信息已注册，但重启后无法导入 `illustrate` 模块，并出现 `No module named 'illustrate'`。

更新到最新版时，在系统终端执行：

```bash
cd ~/ChimeraX-Illustrate
git pull
```

然后回到 ChimeraX，重新执行 `devel install ~/ChimeraX-Illustrate` 并重启。

构建 wheel：

```text
devel build ~/ChimeraX-Illustrate
```

### 安装 wheel 文件

如果已经下载或构建了 `.whl` 文件，可在 ChimeraX 命令行中使用 `toolshed install` 安装。例如，将 wheel 放在 `~/Downloads` 后执行：

```text
toolshed install ~/Downloads/ChimeraX_Illustrate-0.1.20-py3-none-any.whl
```

安装后重启 ChimeraX，再输入 `illustrate`。

不要求安装 Fortran 或 gfortran。NumPy、Qt 和 ChimeraX API 由 ChimeraX 提供。

## 使用

1. 在 ChimeraX 中打开结构，并用 atom、cartoon 或 molecular surface 显示需要绘制的部分。
2. 调整 ChimeraX 中的颜色、显示状态和视角。
3. 如需自动配色，在工具窗口中选择配色方案并点击“应用配色”。
4. 点击“捕获当前场景”。
5. 在工具窗口中调整参数并查看预览。
6. 设置输出尺寸并导出 PNG。

改变 ChimeraX 视角后，需要再次捕获场景。参数修改会作用于已捕获的快照，不会修改 ChimeraX 原始模型。

## 配色方案

工具窗口提供以下方案：

- **经典链配色**：原有的 Illustrate 柔和链配色，兼容已有工作流。
- **冷暖复合物**：冷色与暖色交替，适合受体/伴侣或多亚基复合物。
- **核酸碱基对比**：蛋白链和核酸链分别使用不同的柔和颜色；核酸糖-磷酸骨架保留链色，碱基统一使用浅暖灰白色，以突出内部配对区域。无论当前显示为 atom、cartoon 还是 surface，捕获时都会保留这种逐原子对比。
- **月度分子光谱**：蓝、绿、紫、洋红和暖色依次分配给链。
- **单色蓝系列**：使用多级蓝色表现重复链或对称装配体。

这些方案借鉴了 RCSB PDB-101 *Molecule of the Month* 中介绍的[扁平颜色与黑色轮廓](https://pdb101.rcsb.org/motm/motm-goodsell)，以及[核糖体](https://pdb101.rcsb.org/motm/10)和 [Expressome](https://pdb101.rcsb.org/motm/253) 插图中的分子组分对比方法，但不是对某一幅作品的逐色复制。配色方案按链顺序分配颜色，不会猜测功能域；“核酸碱基对比”会额外根据标准 DNA/RNA 原子名称区分糖-磷酸骨架和碱基。应用配色还会设置白色背景、柔和光照、ChimeraX 轮廓并隐藏氢原子；随后点击“捕获当前场景”更新预览。

仓库仍保留兼容脚本 [`chimerax-chain-palette.py`](chimerax-chain-palette.py)，它使用“经典链配色”。需要从命令行使用时，在 ChimeraX 中运行：

在 ChimeraX 中打开结构后运行：

```text
runscript /absolute/path/to/chimerax-chain-palette.py
```

配色按钮和脚本只修改 ChimeraX 的显示颜色及相关显示设置，不修改坐标，也不会覆盖输入结构文件。

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
