"""Illustrate-oriented chain coloring for ChimeraX atomic models."""

from colorsys import rgb_to_hls, hls_to_rgb


CHAIN_PALETTE = [
    "#70A5F5",
    "#F78C90",
    "#F4B3C1",
    "#F3AE73",
    "#62D96B",
    "#E7C66A",
    "#64C7C0",
    "#E6C65C",
    "#6F8FB8",
    "#D98DA6",
    "#72C6E8",
    "#9BCB70",
]

KNOWN_CHAIN_SETS = {
    frozenset(("A", "B", "G", "R")): {
        "R": "#70A5F5",
        "A": "#F78C90",
        "B": "#F4B3C1",
        "G": "#F3AE73",
    }
}


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
    model_spec = "#" + structure.id_string
    return "{} & ::chain_id=={}".format(model_spec, _quoted(chain_id))


def apply_chain_palette(session, command_runner=None, structure_type=None):
    """Color all open atomic structures and return assignment descriptions."""

    if structure_type is None:
        from chimerax.atomic import AtomicStructure
        structure_type = AtomicStructure
    if command_runner is None:
        from chimerax.core.commands import run
        command_runner = run

    structures = session.models.list(type=structure_type)
    if not structures:
        session.logger.warning("Chain palette: no atomic model is open.")
        return ()

    palette_index = 0
    assignments = []
    for structure in structures:
        model_spec = "#" + structure.id_string
        chain_ids = _chain_ids_in_file_order(structure)
        known_colors = KNOWN_CHAIN_SETS.get(frozenset(chain_ids), {})
        if known_colors:
            palette_index += len(known_colors)
        for chain_id in chain_ids:
            if chain_id in known_colors:
                base = known_colors[chain_id]
            else:
                base = CHAIN_PALETTE[palette_index % len(CHAIN_PALETTE)]
                palette_index += 1
            spec = _chain_spec(structure, chain_id)
            command_runner(
                session,
                "color {} {} target acs halfbond true".format(spec, base),
            )
            for element, color in _element_colors(base).items():
                command_runner(
                    session,
                    "color ({} & {}) {} target a halfbond true".format(
                        spec, element, color
                    ),
                )
            shown_id = chain_id if chain_id else "<blank>"
            assignments.append("{} /{} = {}".format(model_spec, shown_id, base))

    command_runner(session, "hide H atoms")
    command_runner(session, "set bgColor white")
    command_runner(session, "lighting soft")
    command_runner(session, "graphics silhouettes true")

    session.logger.info(
        "Chain palette applied to {} chain(s):\n{}".format(
            len(assignments), "\n".join(assignments)
        )
    )
    return tuple(assignments)
