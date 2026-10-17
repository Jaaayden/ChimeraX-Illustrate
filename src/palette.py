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

# Non-polymer components.  Residues are grouped by *name*, so every copy of the
# same molecule gets the same color, and the number of colors stays small:
#   * each distinct small molecule (drug, cofactor, ...) has its own color;
#   * all sterols share one color and all other lipids share another;
#   * all sugars (glycans) share one color;
#   * water, ions, crystallization additives and detergents are left alone.
_STEROLS = frozenset((
    "CLR", "CHL", "CHL1", "CHOL", "CH1", "ERG", "SIT", "STI",
))
_LIPIDS = frozenset((
    # glycerophospholipids
    "POPC", "POPE", "POPS", "POPG", "POPA", "POPI", "PC", "PE", "PS", "PG", "PA",
    "PI", "DPPC", "DPPE", "DPPS", "DPPG", "DOPC", "DOPE", "DOPS", "DOPG", "DLPC",
    "DLPE", "DMPC", "DMPE", "DSPC", "DSPE", "DAPC", "DYPC", "PEE", "PGT", "PCW",
    "LPE", "LPC", "6PL", "3PE", "3PC", "PTY", "PLC", "CDL", "CL4", "PGW",
    # sphingolipids
    "SPH", "CER", "SM", "PSM", "SPM",
    # fatty acids and glycerides
    "OLA", "OLB", "OLC", "PLM", "MYR", "STE", "PAM", "LNL", "ARA", "OCT",
    "MC3", "TGL", "DGA", "MAG",
))
_GLYCANS = frozenset((
    "NAG", "NDG", "BMA", "MAN", "FUC", "FUL", "GAL", "GLC", "BGC", "SIA", "NGA",
    "A2G", "XYS", "BGC", "GLA", "RAM", "ARA", "NAA",
))
_ADDITIVES = frozenset((
    "SO4", "PO4", "GOL", "EDO", "PEG", "PGE", "PG4", "PE4", "1PE", "P6G", "ACT",
    "ACE", "DMS", "MPD", "TRS", "EPE", "MES", "FMT", "NO3", "CIT", "TLA", "BME",
    "IPA", "MLI", "CAC", "IMD", "UNL", "UNX",
    # detergents
    "LMT", "BOG", "OGA", "LDA", "DDM", "UDM", "BNG", "C8E", "DMU", "B3P",
))

# Colors for the non-polymer groups.  They are deliberately different from the
# soft pastel chain colors: lipids stay quiet (neutral tones) so the membrane
# does not overpower the protein, while ligands get strong, distinct colors.
COMPONENT_COLORS = {
    "sterol": "#B08968",
    "lipid": "#CFC6B8",
    "glycan": "#8FB8C9",
}
LIGAND_PALETTE = (
    "#E63946", "#7B2CBF", "#FFB703", "#06A77D", "#1D6FA5", "#F72585",
)


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


def _polymer_chain_ids(structure, residue_type=None):
    """Chain ids, in file order, that contain protein or nucleic residues.

    Chains made only of ligands or water do not get a chain color (and do not
    use up a palette entry).
    """

    seen = set()
    chain_ids = []
    for residue in structure.residues:
        chain_id = residue.chain_id
        if chain_id in seen:
            continue
        if _residue_category(residue, residue_type) in ("protein", "nucleic"):
            seen.add(chain_id)
            chain_ids.append(chain_id)
    return chain_ids


def _quoted(value):
    return '"{}"'.format(value.replace("\\", "\\\\").replace('"', '\\"'))


def _chain_spec(structure, chain_id):
    """Atoms of the *polymer* in one chain (ligands sharing the chain id are excluded)."""

    model_spec = "#" + structure.id_string
    return "{} & ::chain_id=={} & (protein | nucleic)".format(
        model_spec, _quoted(chain_id)
    )


def _residue_names_spec(structure, names):
    model_spec = "#" + structure.id_string
    tests = " | ".join("::name=={}".format(_quoted(name)) for name in names)
    return "{} & ({})".format(model_spec, tests)


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
    """Classify a residue: protein, nucleic, solvent, ions, sterol, lipid, glycan, additive or ligand."""

    polymer_type = getattr(residue, "polymer_type", None)
    name = str(getattr(residue, "name", "")).strip().upper()
    if residue_type is not None and polymer_type is not None:
        if polymer_type == getattr(residue_type, "PT_AMINO", object()):
            return "protein"
        if polymer_type == getattr(residue_type, "PT_NUCLEIC", object()):
            return "nucleic"
        # Known to be a non-polymer residue: its name cannot make it a chain.
    else:
        if name in _AMINO_ACIDS:
            return "protein"
        if name in _NUCLEIC_ACIDS:
            return "nucleic"
    if name in _SOLVENTS:
        return "solvent"
    if name in _IONS:
        return "ions"
    if name in _STEROLS:
        return "sterol"
    if name in _LIPIDS:
        return "lipid"
    if name in _GLYCANS:
        return "glycan"
    if name in _ADDITIVES:
        return "additive"
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
        chain_ids = _polymer_chain_ids(structure, residue_type)
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


def _apply_chain_colors(session, structures, command_runner, preset,
                        residue_type=None):
    palette = CHAIN_PALETTES[preset]
    palette_index = 0
    assignments = []
    for structure in structures:
        model_spec = "#" + structure.id_string
        chain_ids = _polymer_chain_ids(structure, residue_type)
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


def _collect_components(structures, residue_type):
    """Group the non-polymer residues of each structure into colored components.

    Returns one list per structure of ``(label, residue_names, color)``.  A
    ligand's color depends only on its residue name, so the same molecule has
    the same color in every structure.
    """

    ligand_colors = {}
    result = []
    for structure in structures:
        groups = {}
        for residue in structure.residues:
            category = _residue_category(residue, residue_type)
            name = str(getattr(residue, "name", "")).strip()
            if category in COMPONENT_COLORS:
                key = category
            elif category == "ligand" and name:
                key = "ligand " + name
                if name not in ligand_colors:
                    ligand_colors[name] = LIGAND_PALETTE[
                        len(ligand_colors) % len(LIGAND_PALETTE)
                    ]
            else:
                continue  # polymer, water, ions, additives: not colored here
            names = groups.setdefault(key, [])
            if name not in names:
                names.append(name)
        components = []
        for key, names in groups.items():
            if key in COMPONENT_COLORS:
                color = COMPONENT_COLORS[key]
            else:
                color = ligand_colors[names[0]]
            components.append((key, names, color))
        result.append(components)
    return result


def _apply_component_colors(session, structures, command_runner, residue_type):
    """Color ligands, lipids and sugars (not water or ions) by molecule type."""

    assignments = []
    collected = _collect_components(structures, residue_type)
    for structure, components in zip(structures, collected):
        model_spec = "#" + structure.id_string
        for label, names, color in components:
            spec = _residue_names_spec(structure, names)
            _color_selection(session, command_runner, spec, color)
            assignments.append("{} {} ({}) = {}".format(
                model_spec, label, ",".join(names), color
            ))
    return assignments


def preset_prefers_atom_colors(preset):
    """Whether captures should keep per-atom colors after applying ``preset``.

    The nucleic-base preset colors backbone and nucleobase atoms differently,
    which cartoon/surface colors would otherwise hide.
    """

    return preset == "ribosome"


def apply_chain_palette(session, command_runner=None, structure_type=None,
                        preset="classic", residue_type=None,
                        adjust_scene=True):
    """Apply a coloring preset and return assignment descriptions.

    With ``adjust_scene`` the scene is also prepared for illustration: hydrogens
    are hidden, the background is set to white, and soft lighting and
    silhouettes are enabled.  Pass ``adjust_scene=False`` to change colors only.
    """

    if preset not in PALETTE_PRESETS:
        raise ValueError("Unknown Illustrate palette preset: {}".format(preset))
    if structure_type is None:
        from chimerax.atomic import AtomicStructure, Residue
        structure_type = AtomicStructure
        residue_type = Residue
    if command_runner is None:
        from chimerax.core.commands import run
        command_runner = run

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
            session, structures, command_runner, preset, residue_type
        )
    assignments = list(assignments) + _apply_component_colors(
        session, structures, command_runner, residue_type
    )

    if adjust_scene:
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
