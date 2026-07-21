"""Illustrate-inspired automatic chain coloring for UCSF ChimeraX.

Run inside ChimeraX after opening one or more atomic models:

    runscript /absolute/path/to/chimerax-chain-palette.py

The script does not modify coordinates or save over input structures.
"""

from colorsys import rgb_to_hls, hls_to_rgb

from chimerax.atomic import AtomicStructure
from chimerax.core.commands import run


# Colors are assigned in model order and first chain-appearance order.
# The first four reproduce the 5-HT1A example: blue, coral, blush, orange.
CHAIN_PALETTE = [
    "#70A5F5",  # blue
    "#F78C90",  # coral pink
    "#F4B3C1",  # light pink
    "#F3AE73",  # orange
    "#62D96B",  # green
    "#E7C66A",  # warm yellow
    "#64C7C0",  # teal
    "#E6C65C",  # ochre
    "#6F8FB8",  # muted blue
    "#D98DA6",  # dusty rose
    "#72C6E8",  # cyan
    "#9BCB70",  # leaf green
]

# Preserve the already-approved 5-HT1A/G-protein mapping when that exact chain
# combination is detected. Other structures use the automatic palette order.
KNOWN_CHAIN_SETS = {
    frozenset(("A", "B", "G", "R")): {
        "R": "#70A5F5",
        "A": "#F78C90",
        "B": "#F4B3C1",
        "G": "#F3AE73",
    }
}

# Presentation switches. Existing molecular surfaces are colored, but no new
# surfaces are created unless MAKE_SURFACES is changed to True.
MAKE_SURFACES = False
HIDE_HYDROGENS = True
SET_WHITE_BACKGROUND = True
SET_SOFT_LIGHTING = True
SET_SILHOUETTES = True


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    channels = [max(0, min(255, round(channel * 255))) for channel in rgb]
    return "#{:02X}{:02X}{:02X}".format(*channels)


def _lighten(color, amount):
    r, g, b = _hex_to_rgb(color)
    h, lightness, saturation = rgb_to_hls(r, g, b)
    lightness = lightness + (1.0 - lightness) * amount
    return _rgb_to_hex(hls_to_rgb(h, lightness, saturation))


def _darken(color, amount):
    r, g, b = _hex_to_rgb(color)
    h, lightness, saturation = rgb_to_hls(r, g, b)
    lightness = lightness * (1.0 - amount)
    return _rgb_to_hex(hls_to_rgb(h, lightness, saturation))


def _element_colors(base):
    """Use one hue per chain and distinguish elements only by lightness."""
    return {
        "C": base,
        "N": _darken(base, 0.08),
        "O": _lighten(base, 0.10),
        "S": _darken(base, 0.16),
        "P": _lighten(base, 0.18),
        "H": _lighten(base, 0.42),
    }


def _chain_ids_in_file_order(structure):
    seen = set()
    chain_ids = []
    for residue in structure.residues:
        chain_id = residue.chain_id
        if chain_id not in seen:
            seen.add(chain_id)
            chain_ids.append(chain_id)
    return chain_ids


def _quoted(value):
    return '"{}"'.format(value.replace("\\", "\\\\").replace('"', '\\"'))


def _chain_spec(structure, chain_id):
    # Select by the residue chain_id instead of the polymer Chain object. This
    # includes ligands, cofactors, and other non-polymer residues carrying the
    # same chain ID, and also handles blank or multi-character IDs.
    model_spec = "#" + structure.id_string
    return "{} & ::chain_id=={}".format(model_spec, _quoted(chain_id))


def apply_chain_palette(session):
    structures = session.models.list(type=AtomicStructure)
    if not structures:
        session.logger.warning("Chain palette: no atomic model is open.")
        return

    palette_index = 0
    assignments = []

    for structure in structures:
        model_spec = "#" + structure.id_string
        chain_ids = _chain_ids_in_file_order(structure)
        known_colors = KNOWN_CHAIN_SETS.get(frozenset(chain_ids), {})
        if known_colors:
            # Reserve these first palette slots so additional open models start
            # at green instead of reusing the four example colors immediately.
            palette_index += len(known_colors)
        for chain_id in chain_ids:
            if chain_id in known_colors:
                base = known_colors[chain_id]
            else:
                base = CHAIN_PALETTE[palette_index % len(CHAIN_PALETTE)]
                palette_index += 1
            spec = _chain_spec(structure, chain_id)

            # Base color controls cartoons and molecular surfaces. It is also
            # applied to atoms first so uncommon elements inherit chain color.
            run(session, "color {} {} target acs halfbond true".format(spec, base))

            # Common elements receive chain-relative variations. Surfaces stay
            # clean and chain-colored; atom/bond representations show details.
            for element, color in _element_colors(base).items():
                run(
                    session,
                    "color ({} & {}) {} target a halfbond true".format(
                        spec, element, color
                    ),
                )

            shown_id = chain_id if chain_id else "<blank>"
            assignments.append("{} /{} = {}".format(model_spec, shown_id, base))

        if MAKE_SURFACES:
            run(session, "surface {}".format(model_spec))

    if HIDE_HYDROGENS:
        run(session, "hide H atoms")
    if SET_WHITE_BACKGROUND:
        run(session, "set bgColor white")
    if SET_SOFT_LIGHTING:
        run(session, "lighting soft")
    if SET_SILHOUETTES:
        run(session, "graphics silhouettes true")

    session.logger.info(
        "Chain palette applied to {} chain(s):\n{}".format(
            len(assignments), "\n".join(assignments)
        )
    )


apply_chain_palette(session)
