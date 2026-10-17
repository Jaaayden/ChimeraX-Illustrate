<p align="center"><img src="docs/images/icon.png" width="120" alt="Illustrate for ChimeraX"></p>

# Illustrate for ChimeraX

English | [简体中文](README.zh-CN.md)

Turn the current [ChimeraX](https://www.cgl.ucsf.edu/chimerax/) scene into a flat-colored, black-outlined molecular illustration in the style of [Illustrate](https://github.com/ccsb-scripps/Illustrate). No more writing and editing `.inp` files: set up the view in ChimeraX, capture it, and export a PNG.

## Gallery

<p align="center"><a href="docs/images/gallery/7K00.png"><img src="docs/images/gallery/7K00.png" width="560" alt="7K00"></a><br><sub><b>7K00</b> · E. coli 70S ribosome · Nucleic Base Contrast</sub></p>

<table>
<tr><td align="center"><a href="docs/images/gallery/5T0C.png"><img src="docs/images/gallery/5T0C.png" width="280" alt="5T0C"></a><br><sub><b>5T0C</b> · human 26S proteasome<br>MotM Spectrum</sub></td><td align="center"><a href="docs/images/gallery/1LP3.png"><img src="docs/images/gallery/1LP3.png" width="280" alt="1LP3"></a><br><sub><b>1LP3</b> · AAV-2 capsid<br>Monochrome Blues</sub></td><td align="center"><a href="docs/images/gallery/1AON.png"><img src="docs/images/gallery/1AON.png" width="280" alt="1AON"></a><br><sub><b>1AON</b> · GroEL/GroES chaperonin<br>Monochrome Blues</sub></td></tr>
<tr><td align="center"><a href="docs/images/gallery/7DF4.png"><img src="docs/images/gallery/7DF4.png" width="280" alt="7DF4"></a><br><sub><b>7DF4</b> · SARS-CoV-2 spike + ACE2<br>Classic Chains</sub></td><td align="center"><a href="docs/images/gallery/3SN6.png"><img src="docs/images/gallery/3SN6.png" width="280" alt="3SN6"></a><br><sub><b>3SN6</b> · β2 adrenergic receptor–Gs complex<br>Cool / Warm Complex</sub></td><td align="center"><a href="docs/images/gallery/8F7Q.png"><img src="docs/images/gallery/8F7Q.png" width="280" alt="8F7Q"></a><br><sub><b>8F7Q</b> · μ-opioid receptor–Gi complex<br>Classic Chains</sub></td></tr>
</table>

Made with this plugin from [RCSB PDB](https://www.rcsb.org/) structures (click an image for the full size).

## Highlights

- **One click from your scene.** Captures atoms, cartoons or molecular surfaces with your current camera and colors.
- **Smart coloring.** Five presets color chains, and *separately* ligands, lipids and sugars, so a ligand never blends into its receptor.
- **Simple by default.** Capture, pick an export size, export. Contours, boundaries, shadows and fog sit in collapsible Advanced settings.
- **Same look at any size.** Transparent PNG from 300 up to 16000 px, with a live preview that matches the export.
- **Scriptable.** `illustrate save out.png` works in scripts and in `ChimeraX --nogui`.
- English and Chinese interface.

## Installation

Download the latest `.whl` from the [Releases page](https://github.com/Jaaayden/ChimeraX-Illustrate/releases/latest), then run in ChimeraX:

```text
toolshed install ~/Downloads/chimerax_illustrate-0.1.28-py3-none-any.whl
```

Restart ChimeraX and run `illustrate`. Requires ChimeraX 1.10 or later.

<details>
<summary>Install from source instead</summary>

```bash
cd ~
git clone https://github.com/Jaaayden/ChimeraX-Illustrate.git
```

Then in ChimeraX: `devel install ~/ChimeraX-Illustrate`, and restart. Do not add `editable true`; with ChimeraX 1.12 it can leave the `illustrate` module unavailable after a restart.
</details>

## Updating

1. Check your version with `toolshed list installed` (look for `Illustrate (x.y.z)`).
2. Wheel install: download the newer `.whl` and run the same `toolshed install` command; it replaces the old version. Source install: `git pull` in `~/ChimeraX-Illustrate`, then `devel install ~/ChimeraX-Illustrate`.
3. Restart ChimeraX.

If the old version sticks, add `reinstall true` to the `toolshed install` command, or run `toolshed uninstall ChimeraX-Illustrate` first.

## Quick start

1. Open a structure in ChimeraX and show it as atoms, cartoons or a surface.
2. Run `illustrate`. Optionally pick a color preset and click **Apply Colors**.
3. Click **Capture Current Scene**, then adjust the ChimeraX view if you like and capture again.
4. Choose an **Export size** and click **Export PNG**.

Need to fine-tune? Open **Advanced settings** (Contour, Borders, Shading, General) and watch the preview update.

## Color presets

| Preset | Good for |
| --- | --- |
| **Classic Chains** | Everyday use: soft pastel colors, one per chain |
| **Cool / Warm Complex** | Receptor and partner, multi-subunit complexes |
| **Nucleic Base Contrast** | Ribosomes and DNA/RNA complexes: chain-colored backbone, pale nucleobases |
| **MotM Spectrum** | Large machines: blue, green, purple, magenta, warm in chain order |
| **Monochrome Blues** | Symmetric assemblies and capsids |

Proteins and nucleic acids are colored by chain. Other molecules are colored by type: each small molecule gets its own strong color (all copies share it), sterols share one brown, other lipids one beige, sugars one light blue. Water, ions, crystallization additives and detergents are left alone, which keeps the palette small.

By default a preset also hides hydrogens and sets a white background, soft lighting and silhouettes; clear **Adjust scene when applying colors** (Advanced settings, General) to change colors only.

## Commands

```text
illustrate                                   open the tool window
illustrate capture                           capture the current scene
illustrate save out.png [width 1200] [height 1200] [transparent true|false]
illustrate reset                             discard the captured scene
```

`illustrate save` writes the file before it returns, and exports the tool's captured scene if there is one, otherwise the current scene.

## Development

```bash
python3 -m unittest discover -s tests -t .
```

The renderer is pure NumPy; `tests/reference_render.py` is a slow reference implementation the tests compare it against.

## License

Apache License 2.0. The rendering style and algorithm are based on [ccsb-scripps/Illustrate](https://github.com/ccsb-scripps/Illustrate).
