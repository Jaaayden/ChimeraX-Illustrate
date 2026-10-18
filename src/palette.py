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
    # glycerophospholipids (only names that are unambiguous in the PDB: short
    # codes such as PC, PE, PS or SPM are also used for other molecules, e.g.
    # SPM is spermine in many ribosome structures)
    "POPC", "POPE", "POPS", "POPG", "POPA", "POPI", "DPPC", "DPPE", "DPPS",
    "DPPG", "DOPC", "DOPE", "DOPS", "DOPG", "DLPC", "DLPE", "DMPC", "DMPE",
    "DSPC", "DSPE", "DAPC", "DYPC", "PEE", "PGT", "PCW", "LPE", "LPC", "6PL",
    "3PE", "3PC", "PTY", "PLC", "CDL", "CL4", "PGW",
    # thylakoid and bacterial glycolipids
    "LMG", "DGD", "LHG", "SQD",
    # sphingolipids
    "SPH", "CER", "PSM",
    # fatty acids and glycerides
    "OLA", "OLB", "OLC", "PLM", "MYR", "STE", "PAM", "LNL", "MC3", "TGL", "DGA",
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


class _StructurePlan:
    """What to color in one structure (independent of how it is applied)."""

    def __init__(self, structure, chains, nucleic_chains, components):
        self.structure = structure
        self.chains = chains                  # [(chain_id, hex color)]
        self.nucleic_chains = nucleic_chains  # chain ids that get pale nucleobases
        self.components = components          # [(label, residue names, hex color)]


def _plan_colors(structures, preset, residue_type):
    """Decide every color once: chain colors, nucleobases, ligands/lipids/sugars."""

    palette = CHAIN_PALETTES["classic" if preset == "ribosome" else preset]
    use_known_sets = preset in ("classic", "ribosome")
    palette_index = 0
    plans = []
    for structure, components in zip(
            structures, _collect_components(structures, residue_type)):
        chain_ids = _polymer_chain_ids(structure, residue_type)
        known = (
            KNOWN_CHAIN_SETS.get(frozenset(chain_ids), {}) if use_known_sets else {}
        )
        if known:
            palette_index += len(known)
        nucleic_chains = set()
        if preset == "ribosome":
            for residue in structure.residues:
                if _residue_category(residue, residue_type) == "nucleic":
                    nucleic_chains.add(residue.chain_id)
        chains = []
        for chain_id in chain_ids:
            if chain_id in known:
                color = known[chain_id]
            else:
                color = palette[palette_index % len(palette)]
                palette_index += 1
            chains.append((chain_id, color))
        plans.append(_StructurePlan(structure, chains, nucleic_chains, components))
    return plans


def _describe_plans(plans):
    """Human-readable lines for the log (one per chain, then per component)."""

    lines = []
    for plan in plans:
        model_spec = "#" + plan.structure.id_string
        for chain_id, color in plan.chains:
            shown_id = chain_id if chain_id else "<blank>"
            if chain_id in plan.nucleic_chains:
                lines.append("{} /{} backbone = {}; bases = {}".format(
                    model_spec, shown_id, color, NUCLEIC_BASE_COLOR))
            else:
                lines.append("{} /{} = {}".format(model_spec, shown_id, color))
    for plan in plans:
        model_spec = "#" + plan.structure.id_string
        for label, names, color in plan.components:
            lines.append("{} {} ({}) = {}".format(
                model_spec, label, ",".join(names), color))
    return lines


def _apply_plans_with_commands(session, command_runner, plans, residue_type):
    """Apply a plan with ``color`` commands (slow on big structures)."""

    for plan in plans:
        structure = plan.structure
        residues_by_chain = {}
        if plan.nucleic_chains:
            for residue in structure.residues:
                residues_by_chain.setdefault(residue.chain_id, []).append(residue)
        for chain_id, color in plan.chains:
            chain_spec = _chain_spec(structure, chain_id)
            _color_selection(session, command_runner, chain_spec, color)
            if chain_id not in plan.nucleic_chains:
                continue
            nucleic = [
                residue for residue in residues_by_chain.get(chain_id, ())
                if _residue_category(residue, residue_type) == "nucleic"
            ]
            residue_names = sorted({
                str(getattr(residue, "name", "")).strip() for residue in nucleic
                if str(getattr(residue, "name", "")).strip()
            })
            atom_names = _nucleic_base_atom_names(nucleic)
            if residue_names and atom_names:
                command_runner(
                    session,
                    "color ({} & :{} & @{}) {} target as halfbond true".format(
                        chain_spec, ",".join(residue_names), ",".join(atom_names),
                        NUCLEIC_BASE_COLOR,
                    ),
                )
    for plan in plans:
        for _label, names, color in plan.components:
            _color_selection(
                session, command_runner,
                _residue_names_spec(plan.structure, names), color,
            )


# Elements that get their own shade of the base color (see _element_colors).
_SHADED_ELEMENTS = ("C", "N", "O", "S", "P", "H")
_SHADED_NUMBERS = (6, 7, 8, 16, 15, 1)


def _hex_to_u8(value):
    return tuple(int(round(channel * 255.0)) for channel in _hex_to_rgb(value))


def _atom_colors_from_bases(base_rgb, element_numbers):
    """Per-atom RGB: the base color, shaded by element (as ``_color_selection`` does)."""

    import numpy as np

    result = base_rgb.copy()
    if not len(base_rgb):
        return result
    unique, inverse = np.unique(base_rgb, axis=0, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    table = np.empty((len(unique), len(_SHADED_ELEMENTS), 3), dtype=np.uint8)
    for row, rgb in enumerate(unique):
        variants = _element_colors(_rgb_to_hex([channel / 255.0 for channel in rgb]))
        for column, symbol in enumerate(_SHADED_ELEMENTS):
            table[row, column] = _hex_to_u8(variants[symbol])
    lookup = np.full(256, -1, dtype=np.int16)
    for column, number in enumerate(_SHADED_NUMBERS):
        lookup[number] = column
    column = lookup[np.clip(element_numbers, 0, 255)]
    shaded = column >= 0
    result[shaded] = table[inverse[shaded], column[shaded]]
    return result


def _apply_plans_with_api(session, plans, residue_type):
    """Apply a plan by assigning color arrays directly (fast).

    Produces the same colors as :func:`_apply_plans_with_commands`, but one
    vectorized assignment per structure instead of hundreds of ``color``
    commands, each of which has to evaluate an atom spec over every atom.
    """

    import numpy as np
    from chimerax.atomic import MolecularSurface

    for plan in plans:
        structure = plan.structure
        atoms, residues = structure.atoms, structure.residues
        residue_order = np.argsort(residues.pointers)
        atom_residue = residue_order[np.searchsorted(
            residues.pointers[residue_order], atoms.residues.pointers)]
        chain_ids, names = residues.chain_ids, residues.names
        types = residues.polymer_types
        is_nucleic = types == residue_type.PT_NUCLEIC
        is_polymer = is_nucleic | (types == residue_type.PT_AMINO)

        residue_rgb = np.zeros((len(residues), 3), dtype=np.uint8)
        residue_set = np.zeros(len(residues), dtype=bool)
        for chain_id, color in plan.chains:
            mask = is_polymer & (chain_ids == chain_id)
            residue_rgb[mask] = _hex_to_u8(color)
            residue_set |= mask
        for _label, component_names, color in plan.components:
            mask = np.isin(names, list(component_names))
            residue_rgb[mask] = _hex_to_u8(color)
            residue_set |= mask

        atom_set = residue_set[atom_residue]
        base_rgb = residue_rgb[atom_residue]
        element_numbers = atoms.element_numbers
        pale = np.zeros(len(atoms), dtype=bool)
        if plan.nucleic_chains:
            atom_names = np.char.upper(np.asarray(atoms.names).astype(str))
            backbone = np.isin(atom_names, list(_NUCLEIC_BACKBONE_ATOMS))
            pale = is_nucleic[atom_residue] & atom_set & (element_numbers != 1) & ~backbone

        selected = np.flatnonzero(atom_set)
        atom_rgb = _atom_colors_from_bases(base_rgb[selected], element_numbers[selected])
        colors = atoms.colors.copy()
        colors[selected, :3] = atom_rgb
        colors[selected, 3] = 255
        colors[pale, :3] = _hex_to_u8(NUCLEIC_BASE_COLOR)
        atoms.colors = colors

        ribbon = residues.ribbon_colors.copy()
        ribbon[residue_set, :3] = residue_rgb[residue_set]
        ribbon[residue_set, 3] = 255
        residues.ribbon_colors = ribbon

        bonds = structure.bonds
        if len(bonds) and not bonds.halfbonds.all():
            bonds.halfbonds = True

        # Molecular surfaces take the chain/component color (nucleobases pale).
        surface_rgb = base_rgb.copy()
        surface_rgb[pale] = _hex_to_u8(NUCLEIC_BASE_COLOR)
        atom_order = np.argsort(atoms.pointers)
        for surface in structure.child_models():
            if not isinstance(surface, MolecularSurface):
                continue
            surface_atoms = surface.atoms
            index = atom_order[np.searchsorted(
                atoms.pointers[atom_order], surface_atoms.pointers)]
            keep = np.flatnonzero(atom_set[index])
            if not len(keep):
                continue
            # One call per distinct color, as the ``color`` command does.
            unique, inverse = np.unique(
                surface_rgb[index[keep]], axis=0, return_inverse=True)
            inverse = np.asarray(inverse).reshape(-1)
            for number, rgb in enumerate(unique):
                members = surface_atoms[keep[inverse == number]]
                surface.color_atom_patches(members, color=np.append(rgb, 255).astype(np.uint8))


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
    # Without an explicit runner (the normal case) colors are assigned through
    # the Python API, which is much faster than running ``color`` commands.
    use_api = command_runner is None
    if use_api:
        from chimerax.core.commands import run
        scene_runner = run
    else:
        scene_runner = command_runner

    structures = session.models.list(type=structure_type)
    if not structures:
        session.logger.warning("Illustrate palette: no atomic model is open.")
        return ()

    plans = _plan_colors(structures, preset, residue_type)
    assignments = _describe_plans(plans)
    if use_api:
        _apply_plans_with_api(session, plans, residue_type)
    else:
        _apply_plans_with_commands(session, command_runner, plans, residue_type)

    if adjust_scene:
        scene_runner(session, "hide H atoms")
        scene_runner(session, "set bgColor white")
        scene_runner(session, "lighting soft")
        scene_runner(session, "graphics silhouettes true")

    session.logger.info(
        "Illustrate palette '{}' applied to {} component(s):\n{}".format(
            preset, len(assignments), "\n".join(assignments)
        )
    )
    return tuple(assignments)
