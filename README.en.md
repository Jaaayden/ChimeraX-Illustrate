# Illustrate for ChimeraX

[中文说明](README.md) | English

## Overview

Illustrate for ChimeraX is a ChimeraX bundle that converts the current ChimeraX scene into a non-photorealistic molecular illustration inspired by the style of Illustrate.

It removes the need to manually write and repeatedly edit `.inp` files. Adjust the representation and camera in ChimeraX, capture the current scene, tune the illustration parameters with the live preview, and export a PNG.

This repository contains only the plugin software, documentation, tests, and license files. It does not include structure data or structure-specific results.

## Features

- Captures molecular content represented by visible atoms, cartoons, or molecular surfaces, including the corresponding colors, atomic radii, and grouping metadata.
- Provides five illustration-oriented presets that color current atomic models by chain, including a nucleic backbone/base contrast mode.
- Captures the current ChimeraX camera and view; the renderer uses an Illustrate-style orthographic model.
- A 512-pixel default preview with debounced updates after parameter changes.
- Controls for contours, subunit boundaries, residue boundaries, soft shadows, and fog.
- English is the default interface language, with one-click switching to Chinese.
- Parameters are grouped into three columns for contours, boundaries, and atoms/shadows/fog.
- Transparent or opaque PNG export.
- Preview edge up to 2048 pixels and output width and height from 2 to 16000 pixels; images above 2048 pixels use tiled processing. Very large exports are heavy (about 8000 × 8000: 2 GB and under a minute; 16000 × 16000: about 6–8 GB and several minutes for a 20,000-atom scene), so a notice is shown before they start. Every size keeps the look of the 1200-pixel render: images narrower than 1200 pixels are rendered at 1200 pixels and shrunk by area averaging, and the preview works the same way. Out-of-range size entries are clamped with a status message.
- Raster/shadow caches, active-region cropping, vectorized NumPy rasterization, and multicore shadow processing accelerate previews and high-resolution exports; PNG compositing, compression, and writing are streamed off the ChimeraX UI thread.
- Built-in parameter explanations, practical ranges, and a reset-to-default action.

The rendered output still consists of atomic spheres. Cartoon and molecular-surface meshes are not rasterized directly; the plugin collects the atoms associated with visible cartoon residues or surface patches and converts them to Illustrate-style spheres. Entirely hidden models remain excluded.

## Installation

### Recommended: install from source (macOS / Linux)

First open a system terminal and clone the repository into your home directory:

```bash
cd ~
git clone https://github.com/Jaaayden/ChimeraX-Illustrate.git
```

Then open ChimeraX and run this in the ChimeraX command line:

```text
devel install ~/ChimeraX-Illustrate
```

Restart ChimeraX after installation, then run `illustrate` to open the tool window.

This project uses the `bundle_info.xml` build format. Do not append `editable true`; with ChimeraX 1.12, that may register the tool metadata while leaving the `illustrate` module unavailable after restart, resulting in `No module named 'illustrate'`.

Already have an older version installed? See [Updating to a new version](#updating-to-a-new-version) below.

Build a wheel with:

```text
devel build ~/ChimeraX-Illustrate
```

### Install a wheel file

If you have downloaded or built a `.whl` file, install it from the ChimeraX command line with `toolshed install`. For example, after placing the wheel in `~/Downloads`, run:

```text
toolshed install ~/Downloads/chimerax_illustrate-0.1.22-py3-none-any.whl
```

Restart ChimeraX after installation, then run `illustrate`.

Fortran and gfortran are not required. NumPy, Qt, and the ChimeraX APIs are supplied by ChimeraX.

## Updating to a new version

If you already have an older version installed, follow these steps. Updating only replaces the plugin; your structure files and other ChimeraX settings are untouched.

**Step 1: check the installed version.** Run this in the ChimeraX command line:

```text
toolshed list installed
```

Look for a line such as `Illustrate (0.1.21)`; the number in parentheses is the installed version. The newest version is on the [Releases page](https://github.com/Jaaayden/ChimeraX-Illustrate/releases/latest).

**Step 2: update, depending on how you installed it.**

- **Installed from a wheel file**: download the newest `.whl` from the [Releases page](https://github.com/Jaaayden/ChimeraX-Illustrate/releases/latest), then run this in ChimeraX (use the version and path of the file you downloaded):

  ```text
  toolshed install ~/Downloads/chimerax_illustrate-0.1.22-py3-none-any.whl
  ```

  The new version replaces the old one; you do not need to uninstall first.

- **Installed from source**: pull the latest code in a system terminal:

  ```bash
  cd ~/ChimeraX-Illustrate
  git pull
  ```

  Then, in ChimeraX, run `devel install ~/ChimeraX-Illustrate` again.

**Step 3: restart ChimeraX.** A running ChimeraX does not reload the plugin, so the new version is only used after a restart. Afterwards you can run `toolshed list installed` again to confirm the version.

**Still the old version, or the plugin will not open?** Force a reinstall of the wheel:

```text
toolshed install ~/Downloads/chimerax_illustrate-0.1.22-py3-none-any.whl reinstall true
```

If that does not help, uninstall and install again, then restart ChimeraX:

```text
toolshed uninstall ChimeraX-Illustrate
toolshed install ~/Downloads/chimerax_illustrate-0.1.22-py3-none-any.whl
```

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
- **Nucleic Base Contrast** gives every protein and nucleic-acid chain a different soft color, retains each chain color on the nucleic sugar-phosphate backbone, and uses pale warm gray for the nucleobases to emphasize the paired interior. The atom-level contrast is retained when capturing atom, cartoon, or surface representations.
- **MotM Spectrum** assigns blue, green, purple, magenta, and warm colors in chain order.
- **Monochrome Blues** uses related blue shades for repeated chains or symmetric assemblies.

The presets are inspired by the [flat colors and black outlines](https://pdb101.rcsb.org/motm/motm-goodsell) described by RCSB PDB-101 and by component contrasts in its [Ribosomal Subunits](https://pdb101.rcsb.org/motm/10) and [Expressome](https://pdb101.rcsb.org/motm/253) illustrations; they are not exact color copies of any individual artwork. Presets assign colors in chain order instead of guessing functional domains. **Nucleic Base Contrast** additionally distinguishes sugar-phosphate backbone atoms from nucleobase atoms using standard DNA/RNA atom names. By default, applying a preset also sets a white background, soft lighting, ChimeraX silhouettes, and hidden hydrogens; clear **Also adjust scene** to change colors only. Capture the scene again afterward.

The repository retains [`chimerax-chain-palette.py`](chimerax-chain-palette.py) as a command-line compatibility entry point for **Classic Chains**. To use it, run:

```text
runscript /absolute/path/to/chimerax-chain-palette.py
```

The button and script change ChimeraX display colors and related display settings only. They do not change coordinates or overwrite input structure files.

## Commands

```text
illustrate
illustrate capture [preferAtomColors true|false]
illustrate save /absolute/path/to/illustrate.png [transparent true|false] [width 1200] [height 1200] [preferAtomColors true|false]
illustrate reset
```

`illustrate save` is synchronous: the PNG is complete when the command returns. If the tool window holds a captured snapshot, that snapshot (with its tuned parameters) is exported; otherwise the current scene is captured directly with default parameters. Because of this, `illustrate save` also works without the graphical interface (`ChimeraX --nogui`), where it is the only supported action. `show`, `capture`, and `reset` need the tool window. `preferAtomColors true` keeps each atom's own color for atoms shown only as cartoon or surface; it only affects a fresh capture.
## Development and testing

The rendering core uses NumPy, which ships with ChimeraX. `tests/reference_render.py` keeps a slow pure-Python implementation of the same pipeline that the NumPy backend must match pixel for pixel. Run the tests with:

```text
python3 -m unittest discover -s tests -t . -v
```

The bundle targets ChimeraX 1.10 and compatible stable APIs. Very large images require more memory and render time.

## Changelog

Release downloads and notes are on the [Releases page](https://github.com/Jaaayden/ChimeraX-Illustrate/releases).

### 0.1.22

- Preview edge up to 2048 pixels (was 1024) and export up to 16000 × 16000 pixels (was 8000).
- Very large exports (above 36 megapixels) show a memory and time estimate before rendering starts.
- Images above 2048 pixels are tiled and the full-frame copies at the end of the pipeline are gone, which lowers peak memory (for a 20,000-atom scene: 4096 px from 3.7 to 1.1 GiB).

### 0.1.21

- Every export size keeps the look of the 1200-pixel render. Images narrower than 1200 pixels used to get thicker, blacker outlines; they are now rendered at 1200 pixels and shrunk by area averaging. The live preview uses the same path, so it matches the exported PNG.
- `illustrate save` is synchronous and works without the graphical interface (`ChimeraX --nogui`). New keywords: `width`, `height`, `preferAtomColors`.
- The size fields show their valid range, and out-of-range entries are clamped with a status message instead of being silently refused.
- Fixed export results (success or failure) being lost when the preview re-rendered during an export; exports no longer block the live preview.
- Color presets no longer store hidden state on the session. The extra scene changes (hide hydrogens, white background, soft lighting, silhouettes) can be turned off with **Also adjust scene**, and **Keep Atom Colors** is an explicit option.
- NumPy-only renderer (the pure-Python implementation is kept as a test oracle), vectorized sphere tables, user-visible strings moved to `i18n.py`, 71 unit tests, and a GitHub Actions workflow (pyflakes and tests).

### 0.1.20

- Improved the nucleic-acid color contrast of the **Nucleic Base Contrast** preset.
- Fixed the installation instructions.

### 0.1.19

- First public release.

## License

This project is released under the Apache License 2.0. The non-photorealistic rendering style and algorithm reference are based on [ccsb-scripps/Illustrate](https://github.com/ccsb-scripps/Illustrate).
