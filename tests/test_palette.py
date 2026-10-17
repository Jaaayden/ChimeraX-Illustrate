import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.palette import (
    CHAIN_PALETTES,
    apply_chain_palette,
    available_palette_presets,
    preset_prefers_atom_colors,
)


class FakeElement:
    def __init__(self, name="C", number=6):
        self.name = name
        self.number = number


class FakeAtom:
    def __init__(self, name, element=None):
        self.name = name
        self.element = element or FakeElement()


class FakeResidue:
    def __init__(self, chain_id, name="ALA", atom_names=()):
        self.chain_id = chain_id
        self.name = name
        self.polymer_type = None
        self.atoms = tuple(FakeAtom(atom_name) for atom_name in atom_names)


class FakeStructure:
    def __init__(self, model_id, chain_ids):
        self.id_string = model_id
        self.residues = [
            FakeResidue(*entry) if isinstance(entry, tuple) else FakeResidue(entry)
            for entry in chain_ids
        ]


class FakeModels:
    def __init__(self, structures):
        self.structures = structures

    def list(self, type=None):
        return self.structures


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)


class FakeSession:
    def __init__(self, structures):
        self.models = FakeModels(structures)
        self.logger = FakeLogger()


class PaletteTests(unittest.TestCase):
    def test_palette_colors_each_unique_chain_and_sets_presentation(self):
        session = FakeSession([FakeStructure("1", ["A", "A", "B"])])
        commands = []

        assignments = apply_chain_palette(
            session,
            command_runner=lambda _session, command: commands.append(command),
            structure_type=FakeStructure,
        )

        self.assertEqual(len(assignments), 2)
        self.assertIn(
            'color #1 & ::chain_id=="A" & (protein | nucleic) #70A5F5 target acs halfbond true',
            commands,
        )
        self.assertIn(
            'color #1 & ::chain_id=="B" & (protein | nucleic) #F78C90 target acs halfbond true',
            commands,
        )
        self.assertEqual(
            commands[-4:],
            [
                "hide H atoms",
                "set bgColor white",
                "lighting soft",
                "graphics silhouettes true",
            ],
        )
        self.assertTrue(session.logger.infos)

    def test_palette_reports_when_no_atomic_model_is_open(self):
        session = FakeSession([])
        commands = []
        assignments = apply_chain_palette(
            session,
            command_runner=lambda _session, command: commands.append(command),
            structure_type=FakeStructure,
        )
        self.assertEqual(assignments, ())
        self.assertEqual(commands, [])
        self.assertTrue(session.logger.warnings)

    def test_all_documented_presets_are_available(self):
        self.assertEqual(
            available_palette_presets(),
            ("classic", "cool_warm", "ribosome", "functional", "monochrome"),
        )

    def test_cool_warm_preset_uses_its_chain_palette(self):
        session = FakeSession([FakeStructure("1", ["A", "B"])])
        commands = []
        assignments = apply_chain_palette(
            session,
            command_runner=lambda _session, command: commands.append(command),
            structure_type=FakeStructure,
            preset="cool_warm",
        )
        self.assertEqual(len(assignments), 2)
        self.assertIn(
            'color #1 & ::chain_id=="A" & (protein | nucleic) #6599E8 target acs halfbond true',
            commands,
        )

    def test_ribosome_preset_varies_chains_and_contrasts_nucleobases(self):
        session = FakeSession([
            FakeStructure("1", [
                ("A", "ALA"),
                ("B", "GLY"),
                ("I", "DA", ("P", "C1'", "N9", "C8")),
                ("J", "DC", ("P", "C1'", "N1", "C2", "O2")),
            ])
        ])
        commands = []
        assignments = apply_chain_palette(
            session,
            command_runner=lambda _session, command: commands.append(command),
            structure_type=FakeStructure,
            preset="ribosome",
        )
        self.assertEqual(len(assignments), 4)
        self.assertIn(
            'color #1 & ::chain_id=="A" & (protein | nucleic) #70A5F5 target acs halfbond true',
            commands,
        )
        self.assertIn(
            'color #1 & ::chain_id=="B" & (protein | nucleic) #F78C90 target acs halfbond true',
            commands,
        )
        self.assertIn(
            'color #1 & ::chain_id=="I" & (protein | nucleic) #F4B3C1 target acs halfbond true',
            commands,
        )
        self.assertIn(
            'color #1 & ::chain_id=="J" & (protein | nucleic) #F3AE73 target acs halfbond true',
            commands,
        )
        base_commands = [
            command for command in commands if "#F2EFE8 target as" in command
        ]
        self.assertEqual(len(base_commands), 2)
        self.assertIn(
            'color (#1 & ::chain_id=="I" & (protein | nucleic) & :DA & @C8,N9) '
            '#F2EFE8 target as halfbond true',
            base_commands,
        )
        self.assertIn(
            'color (#1 & ::chain_id=="J" & (protein | nucleic) & :DC & @C2,N1,O2) '
            '#F2EFE8 target as halfbond true',
            base_commands,
        )
        self.assertNotIn("C1'", "\n".join(base_commands))
        self.assertNotIn("@P", "\n".join(base_commands))

    def test_only_the_nucleic_preset_prefers_atom_colors(self):
        for preset in available_palette_presets():
            self.assertEqual(
                preset_prefers_atom_colors(preset), preset == "ribosome"
            )

    def test_palette_leaves_scene_settings_alone_when_not_adjusting(self):
        session = FakeSession([FakeStructure("1", ["A", "B"])])
        commands = []
        apply_chain_palette(
            session,
            command_runner=lambda _session, command: commands.append(command),
            structure_type=FakeStructure,
            adjust_scene=False,
        )
        self.assertTrue(commands)
        self.assertTrue(all(command.startswith("color ") for command in commands))

    def test_palette_does_not_attach_state_to_the_session(self):
        session = FakeSession([FakeStructure("1", ["A"])])
        apply_chain_palette(
            session,
            command_runner=lambda *_args: None,
            structure_type=FakeStructure,
            preset="ribosome",
        )
        self.assertFalse(hasattr(session, "_illustrate_prefer_atom_colors"))

    def test_unknown_preset_is_rejected(self):
        session = FakeSession([FakeStructure("1", ["A"])])
        with self.assertRaises(ValueError):
            apply_chain_palette(
                session,
                command_runner=lambda *_args: None,
                structure_type=FakeStructure,
                preset="missing",
            )


def residues_of(chain_id, *entries):
    """Fake residues: ``entries`` are residue names in chain ``chain_id``."""

    return [(chain_id, name) for name in entries]


class ComponentColorTests(unittest.TestCase):
    def _run(self, structures, preset="classic"):
        session = FakeSession(structures)
        commands = []
        assignments = apply_chain_palette(
            session,
            command_runner=lambda _session, command: commands.append(command),
            structure_type=FakeStructure,
            preset=preset,
            adjust_scene=False,
        )
        return commands, assignments

    @staticmethod
    def _base_color(commands, spec_fragment):
        """Hex color given to the whole selection that contains ``spec_fragment``."""

        for command in commands:
            if spec_fragment in command and command.endswith("target acs halfbond true"):
                return command.split(" ")[-5]  # "... #RRGGBB target acs halfbond true"
        raise AssertionError("no whole-selection color for %r in %r" % (spec_fragment, commands))

    def test_ligand_in_the_receptor_chain_gets_its_own_color(self):
        structure = FakeStructure("1", residues_of("A", "ALA", "ALA", "LIG", "LIG"))
        commands, assignments = self._run([structure])
        chain = self._base_color(commands, '::chain_id=="A" & (protein | nucleic)')
        ligand = self._base_color(commands, '::name=="LIG"')
        self.assertNotEqual(chain, ligand)
        self.assertEqual(len(assignments), 2)  # one chain, one ligand type
        # The chain color is applied to the polymer only, never to the ligand.
        self.assertTrue(all(
            "LIG" not in command
            for command in commands if '(protein | nucleic)' in command
        ))

    def test_every_copy_of_a_molecule_shares_one_color(self):
        structure = FakeStructure("1", residues_of("A", "ALA", "LIG", "LIG", "LIG"))
        commands, _ = self._run([structure])
        whole = [c for c in commands if '::name=="LIG"' in c and c.endswith("target acs halfbond true")]
        self.assertEqual(len(whole), 1)  # a single color command covers all copies

    def test_different_ligands_get_different_colors(self):
        structure = FakeStructure("1", residues_of("A", "ALA", "AAA", "BBB", "CCC"))
        commands, _ = self._run([structure])
        colors = {
            self._base_color(commands, '::name=="%s"' % name) for name in ("AAA", "BBB", "CCC")
        }
        self.assertEqual(len(colors), 3)

    def test_ligand_color_is_the_same_in_every_structure(self):
        first = FakeStructure("1", residues_of("A", "ALA", "AAA"))
        second = FakeStructure("2", residues_of("A", "ALA", "BBB", "AAA"))
        commands, _ = self._run([first, second])
        in_first = self._base_color(commands, '#1 & (::name=="AAA")')
        in_second = self._base_color(commands, '#2 & (::name=="AAA")')
        self.assertEqual(in_first, in_second)

    def test_lipids_share_one_color_and_sterols_have_another(self):
        structure = FakeStructure("1", residues_of("A", "ALA") + residues_of("L", "PEE", "OLA", "CLR", "CLR"))
        commands, assignments = self._run([structure])
        lipid = self._base_color(commands, '::name=="PEE" | ::name=="OLA"')
        sterol = self._base_color(commands, '::name=="CLR"')
        self.assertNotEqual(lipid, sterol)
        self.assertEqual(len(assignments), 3)  # chain, lipids, sterols

    def test_ambiguous_short_codes_are_ordinary_ligands(self):
        # SPM is spermine (not sphingomyelin) in ribosome structures.
        structure = FakeStructure("1", residues_of("A", "ALA", "SPM", "PC"))
        _, assignments = self._run([structure])
        self.assertTrue(any("ligand SPM" in a for a in assignments))
        self.assertTrue(any("ligand PC" in a for a in assignments))
        self.assertFalse(any(a.split()[1] == "lipid" for a in assignments[1:]))

    def test_thylakoid_lipids_count_as_lipids(self):
        structure = FakeStructure("1", residues_of("A", "ALA", "LMG", "DGD", "LHG", "SQD"))
        _, assignments = self._run([structure])
        self.assertEqual(len([a for a in assignments if " lipid " in a]), 1)

    def test_sugars_share_one_color(self):
        structure = FakeStructure("1", residues_of("A", "ALA", "NAG", "BMA", "MAN"))
        _, assignments = self._run([structure])
        self.assertEqual(len([a for a in assignments if "glycan" in a]), 1)

    def test_water_ions_and_additives_are_left_alone(self):
        structure = FakeStructure(
            "1", residues_of("A", "ALA", "HOH", "NA", "SO4", "GOL", "LMT")
        )
        commands, assignments = self._run([structure])
        self.assertEqual(len(assignments), 1)  # only the chain
        for name in ("HOH", "NA", "SO4", "GOL", "LMT"):
            self.assertFalse(any(name in command for command in commands))

    def test_chain_without_polymer_does_not_use_a_chain_color(self):
        structure = FakeStructure("1", residues_of("A", "ALA") + residues_of("Z", "AAA", "AAA"))
        commands, assignments = self._run([structure])
        self.assertFalse(any('::chain_id=="Z"' in command for command in commands))
        # ... and the next real chain still gets the second palette color.
        other = FakeStructure("2", residues_of("A", "ALA"))
        commands, _ = self._run([structure, other])
        self.assertEqual(
            self._base_color(commands, '#2 & ::chain_id=="A"'), CHAIN_PALETTES["classic"][1]
        )

    def test_component_colors_differ_from_every_chain_palette_color(self):
        from src.palette import COMPONENT_COLORS, LIGAND_PALETTE

        chain_colors = {c for colors in CHAIN_PALETTES.values() for c in colors}
        for color in list(COMPONENT_COLORS.values()) + list(LIGAND_PALETTE):
            self.assertNotIn(color, chain_colors)

    def test_nucleic_preset_also_colors_ligands(self):
        structure = FakeStructure("1", residues_of("A", "ALA", "AAA"))
        commands, assignments = self._run([structure], preset="ribosome")
        self.assertTrue(any('::name=="AAA"' in command for command in commands))
        self.assertTrue(any("ligand AAA" in a for a in assignments))


if __name__ == "__main__":
    unittest.main()
