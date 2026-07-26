"""Compatibility entry point for the Illustrate chain-palette button.

Run inside ChimeraX with:

    runscript /absolute/path/to/chimerax-chain-palette.py
"""

try:
    from illustrate.palette import apply_chain_palette
except ImportError:
    import importlib.util
    from pathlib import Path

    palette_path = Path(__file__).resolve().parent / "src" / "palette.py"
    spec = importlib.util.spec_from_file_location(
        "_illustrate_chain_palette", palette_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    apply_chain_palette = module.apply_chain_palette


apply_chain_palette(session)
