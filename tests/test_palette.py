import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.palette import apply_chain_palette


class FakeResidue:
    def __init__(self, chain_id):
        self.chain_id = chain_id


class FakeStructure:
    def __init__(self, model_id, chain_ids):
        self.id_string = model_id
        self.residues = [FakeResidue(chain_id) for chain_id in chain_ids]


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


if __name__ == "__main__":
    unittest.main()
