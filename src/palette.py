"""Illustrate-oriented coloring presets for ChimeraX atomic models."""

from colorsys import rgb_to_hls, hls_to_rgb


PALETTE_PRESETS = (
    "classic",
    "cool_warm",
    "ribosome",
    "functional",
    "monochrome",
)

CHAIN_PALETTES = {
    "classic": (
        "#70A5F5", "#F78C90", "#F4B3C1", "#F3AE73",
        "#62D96B", "#E7C66A", "#64C7C0", "#E6C65C",
        "#6F8FB8", "#D98DA6", "#72C6E8", "#9BCB70",
    ),
    # Contrasting cool and warm groups work well for receptor/partner and
    # multi-subunit complexes while retaining Goodsell-like pastel colors.
    "cool_warm": (
        "#6599E8", "#F47F87", "#79B8D8", "#F3A45F",
        "#557EBB", "#E7C66A", "#76C4B6", "#D58BA5",
        "#8EB5EF", "#E69778", "#78A99B", "#C99ACC",
    ),
    # Functional-component colors inspired by the blue/green/purple/magenta
    # grouping commonly used in PDB-101 Molecule of the Month illustrations.
    "functional": (
        "#5F98DF", "#65B98B", "#9A78C7", "#D37AA6",
        "#F0B45F", "#E77970", "#73BFC4", "#B7A567",
        "#758AC5", "#8DBB6E", "#C68DA8", "#E29B69",
    ),
    # A quiet blue family for symmetric assemblies and repeated chains.
    "monochrome": (
        "#4F78B8", "#6592D1", "#79A8E7", "#91BCEC",
        "#5C86C5", "#70A0DC", "#86B3E8", "#A1C8EF",
        "#496FA8", "#608BC4", "#76A1D8", "#8CB6E6",
    ),
}

NUCLEIC_BASE_COLOR = "#F2EFE8"

# Sugar-phosphate atoms retain the color assigned to their chain.  Every
# other non-hydrogen atom in a nucleic residue belongs to the nucleobase and
# receives the shared pale color above.  Star aliases cover older PDB atom
# naming conventions.
_NUCLEIC_BACKBONE_ATOMS = frozenset((
    "P", "OP1", "OP2", "OP3", "O1P", "O2P", "O3P",
    "O5'", "C5'", "C4'", "O4'", "C3'", "O3'", "C2'", "O2'", "C1'",
    "O5*", "C5*", "C4*", "O4*", "C3*", "O3*", "C2*", "O2*", "C1*",
))
_STANDARD_NUCLEIC_BASE_ATOMS = frozenset((
    "C2", "C4", "C5", "C6", "C7", "C8",
    "N1", "N2", "N3", "N4", "N6", "N7", "N9",
    "O2", "O4", "O6",
))

KNOWN_CHAIN_SETS = {
    frozenset(("A", "B", "G", "R")): {
        "R": "#70A5F5",
        "A": "#F78C90",
        "B": "#F4B3C1",
        "G": "#F3AE73",
    }
}

_AMINO_ACIDS = frozenset((
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "ASX", "GLX", "MSE", "SEC", "PYL",
))
_NUCLEIC_ACIDS = frozenset((
    "A", "C", "G", "I", "T", "U", "DA", "DC", "DG", "DI", "DT", "DU",
    "ADE", "CYT", "GUA", "THY", "URA",
))
_SOLVENTS = frozenset(("HOH", "WAT", "DOD"))
_IONS = frozenset((
    "CA", "CD", "CL", "CO", "CU", "FE", "K", "MG", "MN", "NA", "NI", "ZN",
))


def available_palette_presets():
    return PALETTE_PRESETS


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


def _color_selection(session, command_runner, spec, base):
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


def _residue_category(residue, residue_type=None):
    polymer_type = getattr(residue, "polymer_type", None)
    if residue_type is not None:
        if polymer_type == getattr(residue_type, "PT_AMINO", object()):
            return "protein"
        if polymer_type == getattr(residue_type, "PT_NUCLEIC", object()):
            return "nucleic"
    name = str(getattr(residue, "name", "")).upper()
    if name in _AMINO_ACIDS:
        return "protein"
    if name in _NUCLEIC_ACIDS:
        return "nucleic"
    if name in _SOLVENTS:
        return "solvent"
    if name in _IONS:
        return "ions"
    return "ligand"


def _atom_is_hydrogen(atom):
    element = getattr(atom, "element", None)
    try:
        if int(getattr(element, "number", 0)) == 1:
            return True
    except (TypeError, ValueError):
        pass
    return str(getattr(element, "name", "")).upper() == "H"


def _nucleic_base_atom_names(residues):
    names = set()
    found_atoms = False
    for residue in residues:
        for atom in getattr(residue, "atoms", ()):
            found_atoms = True
            name = str(getattr(atom, "name", "")).strip()
            if (
                name
                and name.upper() not in _NUCLEIC_BACKBONE_ATOMS
                and not _atom_is_hydrogen(atom)
            ):
                names.add(name)
    if not found_atoms:
        names.update(_STANDARD_NUCLEIC_BASE_ATOMS)
    return tuple(sorted(names))


def _apply_nucleic_base_palette(session, structures, command_runner,
                                 residue_type):
    """Color every polymer by chain and give nucleobases a pale contrast."""

    palette = CHAIN_PALETTES["classic"]
    palette_index = 0
    assignments = []
    for structure in structures:
        model_spec = "#" + structure.id_string
        chain_ids = _chain_ids_in_file_order(structure)
        known_colors = KNOWN_CHAIN_SETS.get(frozenset(chain_ids), {})
        if known_colors:
            palette_index += len(known_colors)
        residues_by_chain = {chain_id: [] for chain_id in chain_ids}
        for residue in structure.residues:
            residues_by_chain.setdefault(residue.chain_id, []).append(residue)
        for chain_id in chain_ids:
            if chain_id in known_colors:
                chain_color = known_colors[chain_id]
            else:
                chain_color = palette[palette_index % len(palette)]
                palette_index += 1
            chain_spec = _chain_spec(structure, chain_id)
            _color_selection(session, command_runner, chain_spec, chain_color)

            nucleic_residues = [
                residue for residue in residues_by_chain.get(chain_id, ())
                if _residue_category(residue, residue_type) == "nucleic"
            ]
            if nucleic_residues:
                residue_names = sorted({
                    str(getattr(residue, "name", "")).strip()
                    for residue in nucleic_residues
                    if str(getattr(residue, "name", "")).strip()
                })
                atom_names = _nucleic_base_atom_names(nucleic_residues)
                if residue_names and atom_names:
                    base_spec = "({} & :{} & @{})".format(
                        chain_spec,
                        ",".join(residue_names),
                        ",".join(atom_names),
                    )
                    command_runner(
                        session,
                        "color {} {} target as halfbond true".format(
                            base_spec, NUCLEIC_BASE_COLOR
                        ),
                    )
                    shown_id = chain_id if chain_id else "<blank>"
                    assignments.append(
                        "{} /{} backbone = {}; bases = {}".format(
                            model_spec, shown_id, chain_color,
                            NUCLEIC_BASE_COLOR,
                        )
                    )
                    continue

            shown_id = chain_id if chain_id else "<blank>"
            assignments.append("{} /{} = {}".format(
                model_spec, shown_id, chain_color
            ))
    return assignments


def _apply_chain_colors(session, structures, command_runner, preset):
    palette = CHAIN_PALETTES[preset]
    palette_index = 0
    assignments = []
    for structure in structures:
        model_spec = "#" + structure.id_string
        chain_ids = _chain_ids_in_file_order(structure)
        known_colors = (
            KNOWN_CHAIN_SETS.get(frozenset(chain_ids), {})
            if preset == "classic"
            else {}
        )
        if known_colors:
            palette_index += len(known_colors)
        for chain_id in chain_ids:
            if chain_id in known_colors:
                base = known_colors[chain_id]
            else:
                base = palette[palette_index % len(palette)]
                palette_index += 1
            spec = _chain_spec(structure, chain_id)
            _color_selection(session, command_runner, spec, base)
            shown_id = chain_id if chain_id else "<blank>"
            assignments.append("{} /{} = {}".format(
                model_spec, shown_id, base
            ))
    return assignments


def apply_chain_palette(session, command_runner=None, structure_type=None,
                        preset="classic", residue_type=None):
    """Apply a coloring preset and return assignment descriptions."""

    if preset not in PALETTE_PRESETS:
        raise ValueError("Unknown Illustrate palette preset: {}".format(preset))
    if structure_type is None:
        from chimerax.atomic import AtomicStructure, Residue
        structure_type = AtomicStructure
        residue_type = Residue
    if command_runner is None:
        from chimerax.core.commands import run
        command_runner = run

    session._illustrate_prefer_atom_colors = preset == "ribosome"
    structures = session.models.list(type=structure_type)
    if not structures:
        session.logger.warning("Illustrate palette: no atomic model is open.")
        return ()

    if preset == "ribosome":
        assignments = _apply_nucleic_base_palette(
            session, structures, command_runner, residue_type
        )
    else:
        assignments = _apply_chain_colors(
            session, structures, command_runner, preset
        )

    # Cartoon and surface capture normally follows the representation's
    # overall color.  This preset intentionally contains atom-level color
    # information (chain-colored backbone versus pale nucleobases), so retain
    # those atom colors when converting any representation to spheres.
    command_runner(session, "hide H atoms")
    command_runner(session, "set bgColor white")
    command_runner(session, "lighting soft")
    command_runner(session, "graphics silhouettes true")

    session.logger.info(
        "Illustrate palette '{}' applied to {} component(s):\n{}".format(
            preset, len(assignments), "\n".join(assignments)
        )
    )
    return tuple(assignments)
