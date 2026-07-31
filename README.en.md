# Illustrate for ChimeraX

[中文说明](README.md) | English

## Overview

Illustrate for ChimeraX is a ChimeraX bundle that converts the current ChimeraX scene into a non-photorealistic molecular illustration inspired by the style of Illustrate.

It removes the need to manually write and repeatedly edit `.inp` files. Adjust the representation and camera in ChimeraX, capture the current scene, tune the illustration parameters with the live preview, and export a PNG.

This repository contains only the plugin software, documentation, tests, and license files. It does not include structure data or structure-specific results.

## Features

- Captures molecular content represented by visible atoms, cartoons, or molecular surfaces, including the corresponding colors, atomic radii, and grouping metadata.
- Provides five illustration-oriented presets that color current atomic models by chain or molecule type and prepare the display environment.
- Captures the current ChimeraX camera and view; the renderer uses an Illustrate-style orthographic model.
- A 512-pixel default preview with debounced updates after parameter changes.
- Controls for contours, subunit boundaries, residue boundaries, soft shadows, and fog.
- English is the default interface language, with one-click switching to Chinese.
- Parameters are grouped into three columns for contours, boundaries, and atoms/shadows/fog.
- Transparent or opaque PNG export.
- Output width and height from 2 to 8000 pixels; large exports use tiled processing.
- Raster/shadow caches, active-region cropping, vectorized NumPy rasterization, and multicore shadow processing accelerate previews and high-resolution exports; PNG compositing, compression, and writing are streamed off the ChimeraX UI thread.
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
3. Run `illustrate`, optionally choose a color preset, and click **Apply Colors**.
4. Click **Capture Current Scene**.
5. Adjust the parameters and inspect the preview.
6. Set the output dimensions and export a PNG.

Capture the scene again after changing the ChimeraX camera. Parameter changes affect the captured snapshot and do not modify the original ChimeraX model.

## Color presets

The tool provides five presets:

- **Classic Chains** preserves the original soft chain palette.
- **Cool / Warm Complex** alternates cool and warm colors for receptor/partner and multisubunit assemblies.
- **Protein Blue / Nucleic Orange** distinguishes proteins, nucleic acids, ligands, ions, and solvent by molecule type.
- **MotM Spectrum** assigns blue, green, purple, magenta, and warm colors in chain order.
- **Monochrome Blues** uses related blue shades for repeated chains or symmetric assemblies.

The presets are inspired by the [flat colors and black outlines](https://pdb101.rcsb.org/motm/motm-goodsell) described by RCSB PDB-101 and by component contrasts in its [Ribosomal Subunits](https://pdb101.rcsb.org/motm/10) and [Expressome](https://pdb101.rcsb.org/motm/253) illustrations; they are not exact color copies of any individual artwork. A PDB file generally lacks enough functional semantics for reliable automatic domain assignment, so all presets except **Protein Blue / Nucleic Orange** assign colors in chain order. Applying a preset also sets a white background, soft lighting, ChimeraX silhouettes, and hidden hydrogens. Capture the scene again afterward.

The repository retains [`chimerax-chain-palette.py`](chimerax-chain-palette.py) as a command-line compatibility entry point for **Classic Chains**. To use it, run:

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
