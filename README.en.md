# Illustrate for ChimeraX

[中文说明](README.md) | English

## Overview

Illustrate for ChimeraX is a ChimeraX bundle that converts the current ChimeraX scene into a non-photorealistic molecular illustration inspired by the style of Illustrate.

It removes the need to manually write and repeatedly edit `.inp` files. Adjust the representation and camera in ChimeraX, capture the current scene, tune the illustration parameters with the live preview, and export a PNG.

This repository contains only the plugin software, documentation, tests, and license files. It does not include structure data or structure-specific results.

## Features

- Captures molecular content represented by visible atoms, cartoons, or molecular surfaces, including the corresponding colors, atomic radii, and grouping metadata.
- Provides a one-click chain-palette button that colors current atomic models and prepares an illustration-oriented display environment.
- Captures the current ChimeraX camera and view; the renderer uses an Illustrate-style orthographic model.
- Low-resolution preview with debounced updates after parameter changes.
- Controls for contours, subunit boundaries, residue boundaries, soft shadows, and fog.
- Transparent or opaque PNG export.
- Output width and height from 2 to 8000 pixels; large exports use tiled processing.
- Built-in parameter explanations, practical ranges, and a reset-to-default action.

The rendered output still consists of atomic spheres. Cartoon and molecular-surface meshes are not rasterized directly; the plugin collects the atoms associated with visible cartoon residues or surface patches and converts them to Illustrate-style spheres. Entirely hidden models remain excluded.

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

1. Open a structure in ChimeraX and display the desired parts as atoms, cartoons, or molecular surfaces.
2. Adjust colors, visibility, and the ChimeraX camera.
3. Run `illustrate` and optionally click **一键链配色** to apply the built-in chain palette.
4. Click **捕获当前场景**.
5. Adjust the parameters and inspect the preview.
6. Set the output dimensions and export a PNG.

Capture the scene again after changing the ChimeraX camera. Parameter changes affect the captured snapshot and do not modify the original ChimeraX model.

## Quick chain coloring

The **一键链配色** button in the Illustrate tool assigns a consistent palette across the chains in the currently open atomic models. Common elements receive lightness variations of the chain color, and the action also sets a white background, soft lighting, silhouettes, and hidden hydrogens. Click **捕获当前场景** afterward to refresh the preview.

The repository retains [`chimerax-chain-palette.py`](chimerax-chain-palette.py) as a command-line compatibility entry point. To use it, run:

```text
runscript /absolute/path/to/chimerax-chain-palette.py
```

The button and script change ChimeraX display colors and related display settings only. They do not change coordinates or overwrite input structure files.

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
