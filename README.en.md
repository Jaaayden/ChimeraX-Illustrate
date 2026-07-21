# Illustrate for ChimeraX

[中文说明](README.md) | English

## Overview

Illustrate for ChimeraX is a ChimeraX bundle that converts the current ChimeraX scene into a non-photorealistic molecular illustration inspired by the style of Illustrate.

It removes the need to manually write and repeatedly edit `.inp` files. Adjust the representation and camera in ChimeraX, capture the current scene, tune the illustration parameters with the live preview, and export a PNG.

This repository contains only the plugin software, documentation, tests, and license files. It does not include structure data or structure-specific results.

## Features

- Captures visible atomic spheres, colors, radii, and grouping metadata.
- Captures the current ChimeraX camera and view; the renderer uses an Illustrate-style orthographic model.
- Low-resolution preview with debounced updates after parameter changes.
- Controls for contours, subunit boundaries, residue boundaries, soft shadows, and fog.
- Transparent or opaque PNG export.
- Output width and height from 2 to 8000 pixels; large exports use tiled processing.
- Built-in parameter explanations, practical ranges, and a reset-to-default action.

The first release supports atomic spheres only. Cartoon, surface, and other complex representations are not converted into atomic spheres.

## Installation

### ChimeraX graphical interface

1. Download or build the project wheel.
2. In ChimeraX, open `Tools → More Tools... → Install from file`.
3. Select the wheel file and restart ChimeraX.
4. Run `illustrate` to open the tool window.

### From source

Run this in the ChimeraX command line:

```text
devel install /absolute/path/to/this/repository editable true
```

Build a wheel with:

```text
devel build /absolute/path/to/this/repository
```

Fortran and gfortran are not required. NumPy, Qt, and the ChimeraX APIs are supplied by ChimeraX.

## Usage

1. Open a structure in ChimeraX and display the atomic spheres to illustrate.
2. Adjust colors, visibility, and the ChimeraX camera.
3. Run `illustrate` and click **捕获当前场景**.
4. Adjust the parameters and inspect the preview.
5. Set the output dimensions and export a PNG.

Capture the scene again after changing the ChimeraX camera. Parameter changes affect the captured snapshot and do not modify the original ChimeraX model.

## Quick chain coloring

The repository also includes the standalone ChimeraX script [`chimerax-chain-palette.py`](chimerax-chain-palette.py). It assigns a consistent palette across the chains in the currently open atomic models. Common elements receive lightness variations of the chain color, and the script can also set a white background, soft lighting, silhouettes, and hidden hydrogens to prepare a scene for Illustrate-style rendering.

After opening a structure in ChimeraX, run:

```text
runscript /absolute/path/to/chimerax-chain-palette.py
```

The script changes ChimeraX display colors and related display settings only. It does not change coordinates or overwrite input structure files. After the palette is applied, run `illustrate` and click **捕获当前场景** to capture those colors in the Illustrate renderer. The script does not require manual `.inp` editing and can be used independently of the Illustrate bundle.

## Commands

```text
illustrate
illustrate capture
illustrate save /absolute/path/to/illustrate.png transparent true
illustrate reset
```

## Development and testing

The rendering core is pure Python with a NumPy acceleration path and a standard-library fallback. Run the tests with:

```text
python3 -m unittest discover -s tests -v
```

The bundle targets ChimeraX 1.10 and compatible stable APIs. Very large images require more memory and render time.

## License

This project is released under the Apache License 2.0. The non-photorealistic rendering style and algorithm reference are based on [ccsb-scripps/Illustrate](https://github.com/ccsb-scripps/Illustrate).
