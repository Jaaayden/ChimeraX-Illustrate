import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.palette import apply_chain_palette, available_palette_presets


class FakeResidue:
    def __init__(self, chain_id, name="ALA"):
        self.chain_id = chain_id
        self.name = name
        self.polymer_type = None


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
            'color #1 & ::chain_id=="A" #70A5F5 target acs halfbond true',
            commands,
        )
        self.assertIn(
            'color #1 & ::chain_id=="B" #F78C90 target acs halfbond true',
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
            'color #1 & ::chain_id=="A" #6599E8 target acs halfbond true',
            commands,
        )

    def test_ribosome_preset_colors_detected_molecule_types(self):
        session = FakeSession([
            FakeStructure("1", [("A", "ALA"), ("R", "A"), ("L", "ATP")])
        ])
        commands = []
        assignments = apply_chain_palette(
            session,
            command_runner=lambda _session, command: commands.append(command),
            structure_type=FakeStructure,
            preset="ribosome",
        )
        self.assertEqual(len(assignments), 3)
        self.assertIn(
            "color (#1 & :ALA) #70A5F5 target acs halfbond true",
            commands,
        )
        self.assertIn(
            "color (#1 & :A) #F3AE73 target acs halfbond true",
            commands,
        )
        self.assertIn(
            "color (#1 & :ATP) #E7C66A target acs halfbond true",
            commands,
        )

    def test_unknown_preset_is_rejected(self):
        session = FakeSession([FakeStructure("1", ["A"])])
        with self.assertRaises(ValueError):
            apply_chain_palette(
                session,
                command_runner=lambda *_args: None,
                structure_type=FakeStructure,
                preset="missing",
            )


if __name__ == "__main__":
    unittest.main()
