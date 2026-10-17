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
- 预览边长最大 2048 像素，导出宽度和高度支持 2–16000 像素；超过 2048 像素的图像使用分块处理。超大导出很吃资源（约 8000×8000：2 GB、不到 1 分钟；16000×16000：约 6–8 GB、数分钟），开始前会在状态栏提示。任何尺寸都保持 1200 像素渲染时的样式：宽度小于 1200 的图像先按 1200 像素渲染，再用面积平均缩小，预览同理；尺寸输入超出范围时会自动限幅并在状态栏提示。
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

已经安装过旧版本？见下文 [更新到新版本](#更新到新版本)。

构建 wheel：

```text
devel build ~/ChimeraX-Illustrate
```

### 安装 wheel 文件

如果已经下载或构建了 `.whl` 文件，可在 ChimeraX 命令行中使用 `toolshed install` 安装。例如，将 wheel 放在 `~/Downloads` 后执行：

```text
toolshed install ~/Downloads/chimerax_illustrate-0.1.22-py3-none-any.whl
```

安装后重启 ChimeraX，再输入 `illustrate`。

不要求安装 Fortran 或 gfortran。NumPy、Qt 和 ChimeraX API 由 ChimeraX 提供。

## 更新到新版本

已经安装过旧版本的用户，按下面的步骤更新。更新只替换插件本身，不会影响你的结构文件和 ChimeraX 的其他设置。

**第一步：查看当前版本。** 在 ChimeraX 命令行中执行：

```text
toolshed list installed
```

找到形如 `Illustrate (0.1.21)` 的一行，括号里就是已安装的版本；最新版本见 [Releases 页面](https://github.com/Jaaayden/ChimeraX-Illustrate/releases/latest)。

**第二步：按你的安装方式更新。**

- **用 wheel 文件安装的**：从 [Releases 页面](https://github.com/Jaaayden/ChimeraX-Illustrate/releases/latest)下载最新的 `.whl` 文件，然后在 ChimeraX 命令行中执行（把版本号和路径换成实际下载的文件）：

  ```text
  toolshed install ~/Downloads/chimerax_illustrate-0.1.22-py3-none-any.whl
  ```

  新版本会直接替换旧版本，不需要先卸载。

- **从源码安装的**：先在系统终端中拉取最新代码：

  ```bash
  cd ~/ChimeraX-Illustrate
  git pull
  ```

  然后回到 ChimeraX，重新执行 `devel install ~/ChimeraX-Illustrate`。

**第三步：重启 ChimeraX。** 已经打开的 ChimeraX 不会重新加载插件，必须重启后才会使用新版本。重启后可再次执行 `toolshed list installed` 确认版本号。

**更新后仍是旧版本，或者插件无法打开？** 可以强制重新安装当前 wheel：

```text
toolshed install ~/Downloads/chimerax_illustrate-0.1.22-py3-none-any.whl reinstall true
```

仍不行时，先卸载再安装，然后重启 ChimeraX：

```text
toolshed uninstall ChimeraX-Illustrate
toolshed install ~/Downloads/chimerax_illustrate-0.1.22-py3-none-any.whl
```

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

这些方案借鉴了 RCSB PDB-101 *Molecule of the Month* 中介绍的[扁平颜色与黑色轮廓](https://pdb101.rcsb.org/motm/motm-goodsell)，以及[核糖体](https://pdb101.rcsb.org/motm/10)和 [Expressome](https://pdb101.rcsb.org/motm/253) 插图中的分子组分对比方法，但不是对某一幅作品的逐色复制。配色方案按链顺序分配颜色，不会猜测功能域；“核酸碱基对比”会额外根据标准 DNA/RNA 原子名称区分糖-磷酸骨架和碱基。默认情况下，应用配色还会设置白色背景、柔和光照、ChimeraX 轮廓并隐藏氢原子；取消勾选“同时调整场景”可只改颜色。随后点击“捕获当前场景”更新预览。

仓库仍保留兼容脚本 [`chimerax-chain-palette.py`](chimerax-chain-palette.py)，它使用“经典链配色”。需要从命令行使用时，在 ChimeraX 中运行：

在 ChimeraX 中打开结构后运行：

```text
runscript /absolute/path/to/chimerax-chain-palette.py
```

配色按钮和脚本只修改 ChimeraX 的显示颜色及相关显示设置，不修改坐标，也不会覆盖输入结构文件。

## 命令

```text
illustrate
illustrate capture [preferAtomColors true|false]
illustrate save /absolute/path/to/illustrate.png [transparent true|false] [width 1200] [height 1200] [preferAtomColors true|false]
illustrate reset
```

`illustrate save` 是同步命令：命令返回时 PNG 已写完。如果工具窗口中已有捕获的快照，则导出该快照（含已调整的参数）；否则直接捕获当前场景并使用默认参数。因此 `illustrate save` 也可用于无界面模式（`ChimeraX --nogui`），且这是该模式下唯一支持的动作；`show`、`capture`、`reset` 需要工具窗口。`preferAtomColors true` 会对仅以 cartoon 或 surface 显示的原子保留其自身颜色，只影响重新捕获。
## 开发与测试

渲染核心使用 ChimeraX 自带的 NumPy。`tests/reference_render.py` 保留了同一管线的纯 Python 慢速参考实现，NumPy 后端必须与之逐像素一致。运行测试：

```text
python3 -m unittest discover -s tests -t . -v
```

当前 bundle 面向 ChimeraX 1.10 及兼容的稳定版 API。超大图像会增加内存占用和渲染时间。

## 许可

本项目使用 Apache License 2.0。非真实感渲染风格和算法参考来自 [ccsb-scripps/Illustrate](https://github.com/ccsb-scripps/Illustrate)。
